# -*- coding: utf-8 -*-
"""
resend_invoice_wizard.py — Tekrar Gönderim Sihirbazı
======================================================
GİB'ten teknik hata kodu dönen faturalarda aynı UUID ile yeniden gönderim yapar.

Ne zaman kullanılır?
    GIB_RETRY_SAME_UUID setindeki kodlar (1101, 1103, 1150 vb.) alındığında.
    Kullanıcı fatura verisini/XML'i düzelttikten sonra bu wizard'ı açar.

Ne zaman KULLANILMAZ?
    1104, 1163 (içerik hatası) → İptal + yeni fatura (cancel_invoice_wizard)
    1310 (alıcı red) → İptal + yeni fatura

Neden aynı UUID?
    GİB teknik hatalarda aynı fatura UUID'siyle düzeltilmiş XML kabul eder.
    Yeni UUID göndermek yeni fatura anlamına gelir; GİB iki kez kayıt görür.

DÜZELTME #2:
    GIB_RETRY_SAME_UUID seti artık constants.py'den import edilir.
    Eskiden bu wizard'da ayrı tanım vardı; account_move.py ile senkronizasyon
    kayması riskini ortadan kaldırdı.
"""
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

# DÜZELTME #2: Tek kaynak — constants.py
# Bu import sayesinde wizard ve account_move aynı set tanımını kullanır.
from ..services.constants import GIB_RETRY_SAME_UUID

_logger = logging.getLogger(__name__)


class ResendInvoiceWizard(models.TransientModel):
    """
    TransientModel: Geçici model; wizard kapatılınca DB'den silinir.
    """
    _name = 'sovos.resend.invoice.wizard'
    _description = 'e-Fatura Tekrar Gönderim Sihirbazı'

    invoice_id = fields.Many2one(
        'account.move',
        string='Fatura',
        required=True,
        # action_open_resend_wizard context'inden otomatik dolar
    )
    resend_type = fields.Selection(
        selection=[
            ('same_uuid',   'Teknik Hata — Aynı UUID ile Tekrar Gönder'),
            ('new_invoice', 'İçerik Değişikliği — İptal et ve Yeni Fatura Kes'),
        ],
        string='Tekrar Gönderim Türü',
        required=True,
        default='same_uuid',
        # _onchange_invoice() bu alanı GİB koduna göre otomatik seçer
    )
    gib_status_code = fields.Integer(
        string='GİB Hata Kodu',
        related='invoice_id.x_gib_status_code',
        readonly=True,
        # Sadece bilgi amaçlı gösterim; wizard'ın üst bölümünde kullanıcıya gösterilir
    )
    note = fields.Text(string='Not')

    @api.onchange('invoice_id')
    def _onchange_invoice(self):
        """
        Fatura değiştiğinde GİB hata koduna göre önerilen tekrar gönderim türünü seçer.

        @api.onchange: Alan değeri değiştiğinde client-side (tarayıcıda) tetiklenir.
        DB'ye kayıt yapılmaz; sadece form görünümünü günceller.

        Mantık:
            Kod GIB_RETRY_SAME_UUID'de → 'same_uuid' öner (aynı UUID ile düzelt)
            Değilse → 'new_invoice' öner (iptal + yeni fatura)
        """
        if self.invoice_id:
            code = self.invoice_id.x_gib_status_code
            self.resend_type = 'same_uuid' if code in GIB_RETRY_SAME_UUID else 'new_invoice'

    def action_resend(self):
        """
        'Tekrar Gönder' butonuna bağlı ana aksiyon.

        Doğrulamalar:
          - Sadece 'error' veya 'rejected' faturalar işleme alınır
          - 'new_invoice' seçildiyse wizard bu akışı desteklemez; yönlendir

        Başarılı tekrar gönderim sonrası wizard kapanır.
        """
        self.ensure_one()
        invoice = self.invoice_id

        # Sadece hatalı veya reddedilmiş faturalar için geçerli
        if invoice.x_efatura_status not in ('error', 'rejected'):
            raise UserError(_(
                'Sadece hatalı (error) veya reddedilmiş faturalar tekrar gönderilebilir.'
            ))

        # new_invoice: Bu wizard desteklemez → kullanıcıyı yönlendir
        if self.resend_type == 'new_invoice':
            raise UserError(_(
                'İçerik değişikliği için önce faturayı iptal edin, '
                'ardından yeni fatura kesin. Bu wizard yalnızca teknik '
                'hata (aynı UUID) akışını destekler.'
            ))

        return self._resend_same_uuid(invoice)

    def _resend_same_uuid(self, invoice):
        """
        Mevcut UUID ve fatura numarasıyla UBL yeniden üretir ve Sovos'a gönderir.

        Kullanım senaryosu:
            1. GİB 1101/1103/1150 vb. hata döndürdü
            2. Kullanıcı/geliştirici fatura verisini düzeltti
            3. Bu metod güncel verilerle yeni UBL üretir
            4. Aynı UUID + numara ile Sovos'a gönderir

        Neden UBL yeniden üretiliyor?
            Fatura verisi (ör: adres, vergi dairesi) güncellenmiş olabilir.
            UblBuilder her çağrıda güncel Odoo verisinden XML üretir.

        UUID değişmez çünkü:
            GİB bu UUID'yi teknik hata statüsünde biliyor.
            Aynı UUID ile düzeltilmiş XML geliyor → GİB günceller.
            Yeni UUID göndersek yeni fatura kaydı açılır.
        """
        company        = invoice.company_id
        partner        = invoice.partner_id
        uuid           = invoice.x_sovos_uuid      # Değişmez
        invoice_number = invoice.name               # Değişmez

        if not uuid:
            raise UserError(_('UUID bulunamadı. Yeni fatura kesin.'))

        from ..services.ubl_builder import UblBuilder
        from ..services.ubl_validator import UblValidator

        scenario = invoice.x_efatura_scenario or 'TICARIFATURA'

        # Güncel Odoo verisinden UBL yeniden üret
        try:
            xml_bytes = UblBuilder(company).build(invoice, uuid, invoice_number, scenario)
        except Exception as e:
            raise UserError(_('UBL üretim hatası: %s') % str(e))

        # Tekrar göndermeden önce validasyon zorunlu
        # Hata varsa → dur, kullanıcıya göster; Sovos'a gönderme
        valid, layer, errors = UblValidator().validate(xml_bytes)
        if not valid:
            invoice.write({'x_validation_errors': '\n'.join(errors)})
            raise UserError(
                _('UBL validasyon hatası [%s]: %s') % (layer, errors[0] if errors else '')
            )

        # Sovos'a gönder
        invoice.write({'x_efatura_status': 'sending'})
        try:
            if invoice.x_efatura_type == 'efatura':
                from ..services.sovos_invoice_service import SovosInvoiceService
                svc = SovosInvoiceService(company)
                envelope_uuid = svc.send_ubl(xml_bytes, uuid, partner, scenario)
            else:
                from ..services.sovos_archive_service import SovosArchiveService
                svc = SovosArchiveService(company)
                envelope_uuid = svc.send_invoice(xml_bytes, uuid, partner)

            # Başarı: durum sıfırla
            invoice.write({
                'x_sovos_envelope_uuid': envelope_uuid,
                'x_efatura_status':      'sent',
                'x_efatura_error_msg':   False,   # False: alanı temizler
                'x_validation_errors':   False,
                'x_gib_status_code':     0,
                'x_gib_admin_notified':  False,
            })
            _logger.info('Tekrar gönderim başarılı: %s (aynı UUID: %s)', invoice_number, uuid)

        except Exception as e:
            # Hata: durumu 'error' yap, mesajı kaydet
            invoice._set_error(_('Tekrar gönderim hatası: %s') % str(e))
            raise UserError(_('Tekrar gönderim hatası: %s') % str(e))

        # Wizard kapat
        return {'type': 'ir.actions.act_window_close'}
