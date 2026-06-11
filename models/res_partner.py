# -*- coding: utf-8 -*-
"""
res_partner.py — Müşteri/Tedarikçi Kart Genişletmesi
======================================================
Odoo'nun res.partner modeline e-Fatura spesifik alanlar ekler.

En kritik özellik: VKN Cache Mekanizması
    GİB e-Fatura sistemine kayıtlı olup olmadığını belirlemek için
    her fatura gönderiminde Sovos'a sorgu atmak yetersiz ve yavaştır.
    Bu yüzden partner kartında cache tutulur:
      - x_efatura_type: 'efatura' veya 'earsiv'
      - x_efatura_type_updated: son güncelleme tarihi

    30 günden eski cache otomatik yenilenir (efatura_type_needs_refresh).
    Sovos erişilemiyorsa cache'deki değer kullanılır (iş devam eder).
    Cache tamamen boşsa ve Sovos erişilemiyorsa → UserError (iş bloke).
"""
import logging
from datetime import date, timedelta
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

# Modül seviyesinde sabitleri tanımlamak daha temiz kod sağlar.
# Hem burada hem de XML view'larda kullanılabilir (related fields için).
EFATURA_TYPE_SELECTION = [
    ('efatura', 'e-Fatura (GİB Kayıtlı)'),   # VKN GİB sisteminde kayıtlı
    ('earsiv', 'e-Arşiv (GİB Kayıtsız)'),     # VKN kayıtsız veya bireysel müşteri
]

SCENARIO_SELECTION = [
    ('TICARIFATURA', 'TİCARİFATURA'),   # B2B ticari fatura; alıcı 8 gün içinde kabul/red
    ('TEMELFATURA', 'TEMELFATURA'),     # B2B basit fatura; yanıt beklenmez
    ('EARSIVFATURA', 'e-Arşiv Fatura'), # GİB'e kayıtsız alıcı veya bireysel
]


class ResPartner(models.Model):
    # _inherit: res.partner tablosuna yeni sütunlar ekliyoruz.
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
        # Fatura üzerinde de manuel değiştirilebilir.
    )
    x_vergi_dairesi = fields.Char(
        string='Vergi Dairesi',
        size=50,
        # UBL-TR XML'inde TaxScheme/Name alanına yazılır.
        # Zorunlu değil ama GİB validasyonunda uyarı verebilir.
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
        # efatura_type_needs_refresh() bu tarihe bakarak 30 gün kontrolü yapar.
    )

    # ── Cache Kontrol Metodları ────────────────────────────────────────────

    def efatura_type_needs_refresh(self):
        """
        VKN cache'inin yenilenmesi gerekip gerekmediğini kontrol eder.

        Yenileme GEREKİR eğer:
          - x_efatura_type alanı hiç doldurulmamışsa (ilk kez sorgulanacak)
          - x_efatura_type_updated tarihi yoksa (ne zaman sorgulandığı bilinmiyor)
          - Son sorgudan bu yana 30+ gün geçmişse (değişmiş olabilir)

        Neden 30 gün?
          Bir firma GİB'e kayıt yaptırabilir veya kaydını iptal ettirebilir.
          30 günde bir kontrol: fazla API çağrısı yapmadan güncel kalmak.

        Returns: True → yenilenmeli | False → cache geçerli, kullan
        """
        self.ensure_one()  # Bu metod tek bir partner için çalışır

        # Cache hiç doldurulmamış → mutlaka sorgula
        if not self.x_efatura_type:
            return True
        if not self.x_efatura_type_updated:
            return True

        # Cache kaç gün önce güncellendi?
        age = (date.today() - self.x_efatura_type_updated).days
        return age > 30  # 30 günden eskiyse yenile

    def refresh_efatura_type(self, company):
        """
        Sovos GetUserList API'sini çağırarak VKN'in GİB'te kayıtlı olup
        olmadığını sorgular ve sonucu partner kartına kaydeder (cache günceller).

        Parametreler:
            company (res.company): Hangi şirketin Sovos hesabı kullanılacak?
                                   Multi-company desteği için gerekli.

        Hata davranışı:
            Sovos erişilemiyorsa (network hatası, timeout) WARNING loglanır
            ama exception fırlatılmaz. Mevcut cache değeri korunur.
            account_move.py'de: cache boşsa UserError, doluysa devam eder.
        """
        self.ensure_one()
        vat = self.vat or ''
        if not vat:
            # VKN/TCKN girilmemiş → sorgulama yapılamaz
            return

        from ..services.sovos_invoice_service import SovosInvoiceService
        try:
            svc = SovosInvoiceService(company)
            is_registered = svc.check_vkn_registered(vat)

            # GİB'te kayıtlı mı? → efatura, değil mi? → earsiv
            new_type = 'efatura' if is_registered else 'earsiv'

            self.write({
                'x_efatura_type': new_type,
                'x_efatura_type_updated': date.today(),  # Cache tarihini güncelle
            })
            _logger.info('VKN cache güncellendi: %s → %s', vat, new_type)

        except Exception as e:
            # Sovos'a erişilemedi — mevcut cache değerini koru, iş durmasın
            _logger.warning('VKN sorgusu başarısız (%s): %s', vat, e)
            # Exception yukarıya fırlatılmaz; caller mevcut değeri kullanır
