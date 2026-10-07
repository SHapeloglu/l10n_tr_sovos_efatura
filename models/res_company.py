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
import base64
import logging
import os

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ── Uygulama Katmanı Şifreleme (Madde 1) ──────────────────────────────────────
# Odoo Community'de built-in DB şifreleme yok. Enterprise Vault gerektirir.
# Çözüm: şifreler DB'ye yazılmadan önce AES-128 (Fernet) ile şifrelenir.
# Anahtar: SOVOS_CRYPT_KEY ortam değişkeninden okunur (32-byte, base64 URL-safe).
# Üretimde: export SOVOS_CRYPT_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
# Anahtar yoksa: şifreleme ATLANIR, yalnızca uyarı loglanır (mevcut davranış korunur).
# cryptography paketi Odoo kurulumunda zaten vardır (oidc, saml vb. bağımlılıkları).

_CRYPT_PREFIX = b'fernet1:'  # Şifreli değerleri düz metinden ayırt eder


def _get_fernet():
    """
    SOVOS_CRYPT_KEY env değişkeninden Fernet nesnesi döndürür.
    Anahtar yoksa veya geçersizse None döner (şifreleme devre dışı).
    """
    try:
        from cryptography.fernet import Fernet
        key = os.environ.get('SOVOS_CRYPT_KEY', '').encode()
        if not key:
            return None
        return Fernet(key)
    except Exception as e:
        _logger.warning('Sovos şifreleme: Fernet başlatılamadı — %s', e)
        return None


def _encrypt_password(plain_text):
    """
    Düz metin şifreyi Fernet ile şifreler.
    Fernet nesnesi yoksa düz metni döndürür (anahtar tanımlı değilse).
    Zaten şifreli ise (prefix kontrolü) tekrar şifrelemez.
    """
    if not plain_text:
        return plain_text
    f = _get_fernet()
    if f is None:
        return plain_text
    # Zaten şifreli mi?
    try:
        raw = plain_text.encode() if isinstance(plain_text, str) else plain_text
        if raw.startswith(_CRYPT_PREFIX):
            return plain_text  # çift şifrelemeyi önle
    except Exception:
        pass
    token = f.encrypt(plain_text.encode())
    return (_CRYPT_PREFIX + token).decode()


def _decrypt_password(cipher_text):
    """
    Fernet ile şifreli değeri çözer.
    Prefix yoksa düz metin gibi muamele edilir (migration öncesi eski kayıtlar).
    """
    if not cipher_text:
        return cipher_text
    try:
        raw = cipher_text.encode() if isinstance(cipher_text, str) else cipher_text
        if not raw.startswith(_CRYPT_PREFIX):
            return cipher_text  # prefix yok → eski düz metin kayıt
        f = _get_fernet()
        if f is None:
            return cipher_text
        token = raw[len(_CRYPT_PREFIX):]
        return f.decrypt(token).decode()
    except Exception as e:
        _logger.error('Sovos şifre çözme hatası: %s', e)
        return cipher_text  # hata durumunda mevcut değeri boz değil

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
    # Madde 1: Şifre alanları DB'ye Fernet (AES-128) ile şifreli yazılır.
    # Ham sütun _enc suffix'li; kullanıcıya/servise gösterilen alan compute/inverse ile çözülür.
    # Anahtar: SOVOS_CRYPT_KEY ortam değişkeni (bkz. dosya başı). Anahtar yoksa plain-text davranış korunur.
    x_sovos_invoice_pass_enc = fields.Char(
        string='e-Fatura Şifresi (Şifreli Ham)',
        groups='base.group_system',
        copy=False,
    )
    x_sovos_invoice_pass = fields.Char(
        string='e-Fatura Şifresi',
        groups='base.group_system',
        compute='_compute_invoice_pass',
        inverse='_inverse_invoice_pass',
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
    x_sovos_archive_pass_enc = fields.Char(
        string='e-Arşiv Şifresi (Şifreli Ham)',
        groups='base.group_system',
        copy=False,
    )
    x_sovos_archive_pass = fields.Char(
        string='e-Arşiv Şifresi',
        groups='base.group_system',
        compute='_compute_archive_pass',
        inverse='_inverse_archive_pass',
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
        # DÜZELTME Madde 11: Alan adı 'test_mode' yanıltıcı olabilir.
        # Doğru okuma: True = TEST ortamı (GİB'e GÖNDERİLMEZ)
        #              False = ÜRETİM ortamı (gerçek GİB iletimi)
        # x_sovos_live_mode veya x_sovos_production_ready daha net olurdu;
        # mevcut verilerle geriye dönük uyumluluk nedeniyle korundu.
        # Üretime geçerken bu alanı MUTLAKA False yapın.
        # Test endpoint:  efatura-test.fitbulut.com
        # Prod endpoint:  efatura.fitbulut.com
    )
    x_sovos_admin_email = fields.Char(
        string='Hata Bildirim E-postası',
        # Cron görevleri başarısız olduğunda (ör: GİB erişim sorunu) bu adrese
        # e-posta gönderilir. Boş bırakılırsa sadece Odoo içi bildirim yapılır.
    )
    x_sovos_last_fetch_date = fields.Date(
        string='Son Gelen Fatura Sorgu Tarihi',
        help=(
            'Gelen fatura cron\'unun bir sonraki çalışmada başlayacağı gün (dahil).\n'
            'SSS S3/S10: GetUblList max 1 günlük tarih aralığı destekler.\n'
            'Cron bu tarihten bugüne kadar günlük chunk\'larla sorgular.\n'
            'Boş → ilk çalışmada son 7 gün (VUK limiti) taranır.'
        ),
    )

    # ── Bağlantı Test Metodları ────────────────────────────────────────────
    # Bu metodlar şirket ayarları formundaki "Bağlantıyı Test Et" butonlarına bağlıdır.
    # XML view'da type="object" butonu bu metodları çağırır.

    # ── Şifre Compute / Inverse Metodları (Madde 1) ──────────────────────────

    @api.depends('x_sovos_invoice_pass_enc')
    def _compute_invoice_pass(self):
        """
        DB'deki şifreli değeri çözüp x_sovos_invoice_pass alanına yazar.
        SOVOS_CRYPT_KEY tanımlı değilse enc alanının değerini olduğu gibi döner
        (migration öncesi eski kayıtlarla geriye dönük uyumluluk).
        """
        for rec in self:
            rec.x_sovos_invoice_pass = _decrypt_password(rec.x_sovos_invoice_pass_enc)

    def _inverse_invoice_pass(self):
        """
        Kullanıcı x_sovos_invoice_pass'e yazdığında şifreleyip _enc sütununa kaydeder.
        """
        for rec in self:
            rec.x_sovos_invoice_pass_enc = _encrypt_password(rec.x_sovos_invoice_pass)

    @api.depends('x_sovos_archive_pass_enc')
    def _compute_archive_pass(self):
        """e-Arşiv şifresi için compute — _compute_invoice_pass ile aynı mantık."""
        for rec in self:
            rec.x_sovos_archive_pass = _decrypt_password(rec.x_sovos_archive_pass_enc)

    def _inverse_archive_pass(self):
        """e-Arşiv şifresi için inverse — _inverse_invoice_pass ile aynı mantık."""
        for rec in self:
            rec.x_sovos_archive_pass_enc = _encrypt_password(rec.x_sovos_archive_pass)

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
