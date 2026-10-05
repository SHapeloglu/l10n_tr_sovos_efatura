# -*- coding: utf-8 -*-
"""
res_partner.py — Müşteri/Tedarikçi Kart Genişletmesi
======================================================
Odoo'nun res.partner modeline e-Fatura spesifik alanlar ekler.

VKN Cache Mekanizması:
    Partner kartında e-Fatura tipi (efatura/earsiv) 30 gün cache'lenir.
    Sovos erişilemiyorsa cache değeri kullanılır (iş devam eder).
    Cache tamamen boşsa ve Sovos erişilemiyorsa → UserError.

DÜZELTME — Madde 2 + 9: VKN/TCKN format ve benzersizlik kontrolü.
    - VKN: tam 10 hane sayısal
    - TCKN: tam 11 hane sayısal
    - Ana cariler (parent_id = False): VKN benzersiz olmalı
    - Alt cariler (şube/adres, parent_id dolu): aynı VKN'i taşıyabilir
    - Birden fazla ana cari aynı VKN ile kayıtlıysa açık hata verir
      (limit=1 ile sessizce ilki almak yerine — Madde 6)
"""
import logging
import re
from datetime import date
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

EFATURA_TYPE_SELECTION = [
    ('efatura', 'e-Fatura (GİB Kayıtlı)'),
    ('earsiv',  'e-Arşiv (GİB Kayıtsız)'),
]

SCENARIO_SELECTION = [
    ('TICARIFATURA', 'TİCARİFATURA'),
    ('TEMELFATURA',  'TEMELFATURA'),
    ('EARSIVFATURA', 'e-Arşiv Fatura'),
]

# VKN: 10 hane sayısal | TCKN: 11 hane sayısal
_VKN_RE  = re.compile(r'^\d{10}$')
_TCKN_RE = re.compile(r'^\d{11}$')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_efatura_type = fields.Selection(
        selection=EFATURA_TYPE_SELECTION,
        string='e-Fatura Türü',
        help=(
            'Boş: Fatura gönderiminde Sovos\'tan otomatik sorgulanır, sonuç cache\'lenir.\n'
            'Dolu: Önce bu değer kullanılır; 30 günden eskiyse otomatik yenilenir.\n'
            'Manuel override için doğrudan değiştirilebilir.'
        ),
    )
    x_default_scenario = fields.Selection(
        selection=SCENARIO_SELECTION,
        string='Varsayılan Senaryo',
        default='TICARIFATURA',
        # Fatura oluşturulurken bu değer varsayılan olarak kullanılır.
    )
    x_vergi_dairesi = fields.Char(
        string='Vergi Dairesi',
        size=50,
        # UBL-TR XML'inde TaxScheme/Name alanına yazılır.
    )
    x_efatura_alias = fields.Char(
        string='e-Fatura GB Kodu (alias)',
        size=50,
        help=(
            'Müşterinin GİB posta kutusu adresi (alias).\n'
            'Boş bırakılırsa VKN kullanılır.\n'
            'Örnek: urn:mail:defaultpk@musteri.com.tr'
        ),
    )
    x_efatura_type_updated = fields.Date(
        string='e-Fatura Tip Güncelleme Tarihi',
        # Cache'in son güncellendiği tarihi tutar.
    )

    # ── VKN/TCKN Format ve Benzersizlik Kontrolü ──────────────────────────

    @api.constrains('vat', 'parent_id')
    def _check_vat_format(self):
        """
        DÜZELTME Madde 2 + 9: VKN/TCKN format ve benzersizlik doğrulaması.

        Kurallar:
          1. VKN: tam 10 hane sayısal (örn: 1234567890)
          2. TCKN: tam 11 hane sayısal (örn: 12345678901)
          3. Ana cariler (parent_id = False): VKN benzersiz olmalı
          4. Alt cariler (şube/adres, parent_id dolu): aynı VKN taşıyabilir

        Madde 6 notu:
          Birden fazla ana cari aynı VKN ile kayıtlıysa tüm eşleşenler
          hata mesajında gösterilir. Eski kod limit=1 ile sessizce
          ilk bulunanı alıyordu; bu artık açık ValidationError olarak yönetilir.

        Neden @api.constrains (DB unique constraint değil)?
          Odoo'nun vat alanı zaten birçok modelde kullanılıyor.
          DB constraint koyarsak standart Odoo işlevleri bozulabilir.
          @api.constrains daha esnek ve Odoo-uyumlu bir yaklaşımdır.
        """
        for partner in self:
            vat = partner.vat
            if not vat:
                continue  # Boş VKN/TCKN kabul edilir — zorunlu değil

            # Kural 1+2: Format kontrolü
            if not (_VKN_RE.match(vat) or _TCKN_RE.match(vat)):
                raise ValidationError(_(
                    '"%s" geçersiz VKN/TCKN formatı.\n\n'
                    '• VKN (Vergi Kimlik No): tam 10 hane sayısal (örn: 1234567890)\n'
                    '• TCKN (TC Kimlik No): tam 11 hane sayısal (örn: 12345678901)\n\n'
                    'Harf, boşluk veya özel karakter kabul edilmez.'
                ) % vat)

            # Kural 3: Ana cari benzersizliği
            # Alt cariler (parent_id dolu olan şube/adres kartları) aynı VKN'i taşıyabilir.
            if not partner.parent_id:
                duplicates = self.search([
                    ('vat', '=', vat),
                    ('parent_id', '=', False),
                    ('id', '!=', partner.id),
                ])
                if duplicates:
                    dup_names = ', '.join(duplicates.mapped('name'))
                    raise ValidationError(_(
                        'VKN/TCKN "%s" zaten başka bir ana cariye kayıtlı:\n%s\n\n'
                        'Her ana carinin VKN/TCKN\'si benzersiz olmalıdır.\n'
                        'Şube veya adres için önce ana cariyi bulun, '
                        'ardından alt cari olarak (child) ekleyin.'
                    ) % (vat, dup_names))

    # ── Cache Kontrol Metodları ────────────────────────────────────────────

    def efatura_type_needs_refresh(self):
        """
        VKN cache'inin yenilenmesi gerekip gerekmediğini kontrol eder.

        Yenileme GEREKİR eğer:
          - x_efatura_type alanı hiç doldurulmamışsa (ilk kez sorgulanacak)
          - x_efatura_type_updated tarihi yoksa
          - Son sorgudan bu yana 30+ gün geçmişse

        Returns: True → yenilenmeli | False → cache geçerli, kullan
        """
        self.ensure_one()
        if not self.x_efatura_type:
            return True
        if not self.x_efatura_type_updated:
            return True
        age = (date.today() - self.x_efatura_type_updated).days
        return age > 30  # 30 günden eskiyse yenile

    def refresh_efatura_type(self, company):
        """
        Sovos GetUserList API'sini çağırarak VKN'in GİB'te kayıtlı olup
        olmadığını sorgular ve partner kartına kaydeder (cache günceller).

        Hata davranışı:
            Sovos erişilemiyorsa WARNING loglanır, exception fırlatılmaz.
            Mevcut cache değeri korunur (iş devam eder).
            Cache boşsa ve bu metod da başarısız olursa: account_move.py
            _resolve_efatura_type() içinde 'earsiv' fallback uygulanır.
        """
        self.ensure_one()
        vat = self.vat or ''
        if not vat:
            return

        from ..services.sovos_invoice_service import SovosInvoiceService
        try:
            svc = SovosInvoiceService(company)
            is_registered = svc.check_vkn_registered(vat)
            new_type = 'efatura' if is_registered else 'earsiv'
            self.write({
                'x_efatura_type':         new_type,
                'x_efatura_type_updated': date.today(),
            })
            _logger.info('VKN cache güncellendi: %s → %s', vat, new_type)
        except Exception as e:
            _logger.warning('VKN sorgusu başarısız (%s): %s', vat, e)
            # Exception yukarıya fırlatılmaz; caller mevcut değeri kullanır
