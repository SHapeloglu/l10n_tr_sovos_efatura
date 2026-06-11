# -*- coding: utf-8 -*-
"""
res_company.py — Şirket Ayarları Genişletmesi
===============================================
Odoo'nun yerleşik res.company modeline Sovos e-Fatura / e-Arşiv entegrasyonu
için gerekli konfigürasyon alanlarını ekler.

Neden burada?
    Odoo'da her şirket kendi bağlantı bilgisini tutabilir. Böylece tek bir
    Odoo kurulumunda birden fazla şirket (farklı VKN'ler) olabilir ve her biri
    kendi Sovos hesabını kullanır.

Güvenlik:
    Kullanıcı adı/şifre alanları groups='base.group_system' ile korunmuştur.
    Yani sadece sistem yöneticileri bu alanları görebilir.
"""
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    # _inherit: Mevcut modeli DEĞİŞTİRİR (yeni tablo oluşturmaz).
    # res.company tablosuna yeni sütunlar eklenir.
    _inherit = 'res.company'

    # ── e-Fatura (InvoiceService) Alanları ────────────────────────────────
    # Bu alanlar Sovos'un GİB e-Fatura web servisine bağlanmak için kullanılır.

    x_sovos_invoice_user = fields.Char(
        string='e-Fatura Kullanıcı Adı',
        # groups: Yalnızca sistem yöneticileri (base.group_system) görebilir.
        # Ekranlardan ve raporlardan gizlenir.
        groups='base.group_system',
    )
    x_sovos_invoice_pass = fields.Char(
        string='e-Fatura Şifresi',
        groups='base.group_system',
        # NOT: Gerçek üretimde bu alan şifrelenmiş saklanmalıdır.
        # Odoo Community'de encrypt özelliği yoktur; Enterprise'da Vault kullanılabilir.
    )
    x_sovos_sender_vkn = fields.Char(
        string='Gönderici VKN',
        size=11,  # TC VKN 10 hane, TCKN 11 hane; en geniş 11 seçildi
    )
    x_sovos_identifier = fields.Char(
        string='Gönderici Posta Kutusu (GB Kodu)',
        # GB Kodu: GİB'in e-Fatura sisteminde şirkete atadığı posta kutusu adresi.
        # Örnek: urn:mail:defaultpk@firmaadi.com.tr
    )
    x_invoice_sequence_id = fields.Many2one(
        'ir.sequence',
        string='e-Fatura Numara Serisi',
        # ir.sequence: Odoo'nun sıralı numara üreten modeli.
        # Bu seri GİB'in istediği formatta (ör: ABC2024000000001) numara üretir.
        # Ayarlar → Teknik → Seriler menüsünden tanımlanır.
    )

    # ── e-Arşiv (ArchiveService) Alanları ─────────────────────────────────
    # e-Arşiv, e-Fatura'ya kayıtsız müşterilere (TCKN sahipleri dahil) fatura
    # kesmek için kullanılır. Tamamen ayrı bir Sovos web servisidir.

    x_sovos_archive_user = fields.Char(
        string='e-Arşiv Kullanıcı Adı',
        groups='base.group_system',
        # e-Fatura kullanıcısından farklı olabilir; Sovos hesabınıza bağlı.
    )
    x_sovos_archive_pass = fields.Char(
        string='e-Arşiv Şifresi',
        groups='base.group_system',
    )
    x_sovos_template_id = fields.Char(
        string='Sovos Şablon ID',
        # e-Arşiv faturasının görsel şablonunu belirler (PDF görünümü).
        # Sovos portalından alınan şablon kodu buraya girilir.
    )

    # ── Genel Ayarlar ─────────────────────────────────────────────────────

    x_sovos_test_mode = fields.Boolean(
        string='Test Modu (GİB\'e İletilmez)',
        default=True,
        # UYARI: Test modu True iken faturalar GİB'e GÖNDERİLMEZ.
        # Geliştirme/test ortamında True, üretimde mutlaka False yapılmalıdır.
        # Sovos'un test endpoint'ine gider: efatura-test.fitbulut.com
    )
    x_sovos_admin_email = fields.Char(
        string='Hata Bildirim E-postası',
        # Cron görevleri başarısız olduğunda (ör: GİB erişim sorunu) bu adrese
        # e-posta gönderilir. Boş bırakılırsa sadece Odoo içi bildirim yapılır.
    )

    # ── Bağlantı Test Metodları ────────────────────────────────────────────
    # Bu metodlar şirket ayarları formundaki "Bağlantıyı Test Et" butonlarına bağlıdır.
    # XML view'da type="object" butonu bu metodları çağırır.

    def action_test_invoice_connection(self):
        """
        e-Fatura (InvoiceService) bağlantı testi yapar.
        Gerçek fatura göndermez; sadece kimlik doğrulama yapar.

        Çağrılma yeri: res_company_views.xml — "e-Fatura Bağlantısını Test Et" butonu
        Dönüş: Başarı bildirimi (display_notification) veya UserError
        """
        # ensure_one(): Bu metod tek kayıt (tek şirket) için tasarlanmıştır.
        # Birden fazla kayıt ile çağrılırsa hata verir.
        self.ensure_one()

        # Lazy import: Modül yüklenirken değil, metod çağrılınca import edilir.
        # Döngüsel import riskini azaltır; Odoo'da yaygın kullanılan pattern.
        from ..services.sovos_invoice_service import SovosInvoiceService
        svc = SovosInvoiceService(self)
        ok, msg = svc.test_connection()

        if ok:
            # Odoo'nun standart bildirim mekanizması (sticky=False → otomatik kapanır)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('e-Fatura Bağlantısı'),
                    'message': _('Bağlantı başarılı: %s') % msg,
                    'type': 'success',
                    'sticky': False,
                },
            }
        # Bağlantı başarısız → kullanıcıya hata mesajı göster (popup)
        raise UserError(_('e-Fatura bağlantı hatası: %s') % msg)

    def action_test_archive_connection(self):
        """
        e-Arşiv (ArchiveService) bağlantı testi yapar.
        e-Fatura'dan tamamen bağımsız bir servistir.

        Çağrılma yeri: res_company_views.xml — "e-Arşiv Bağlantısını Test Et" butonu
        """
        self.ensure_one()
        from ..services.sovos_archive_service import SovosArchiveService
        svc = SovosArchiveService(self)
        ok, msg = svc.test_connection()
        if ok:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('e-Arşiv Bağlantısı'),
                    'message': _('Bağlantı başarılı: %s') % msg,
                    'type': 'success',
                    'sticky': False,
                },
            }
        raise UserError(_('e-Arşiv bağlantı hatası: %s') % msg)
