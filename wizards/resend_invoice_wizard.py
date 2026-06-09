# -*- coding: utf-8 -*-
"""
resend_invoice_wizard.py — Tekrar Gönderim Sihirbazı
======================================================
Teknik hata alan faturalarda (GIB_RETRY_SAME_UUID kodları) aynı UUID
ile UBL yeniden oluşturup Sovos'a gönderir.

İçerik değişikliği gereken durumlar (1104, 1163, RED) bu wizard'ın
kapsamı dışındadır — iptal + yeni fatura akışı kullanılmalıdır.
"""
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

# DÜZELTME #2: Tek kaynak — constants.py. Wizard ile account_move.py
# artık aynı set tanımını paylaşıyor; senkronizasyon riski sıfır.
from ..services.constants import GIB_RETRY_SAME_UUID

_logger = logging.getLogger(__name__)


class ResendInvoiceWizard(models.TransientModel):
    _name = 'sovos.resend.invoice.wizard'
    _description = 'e-Fatura Tekrar Gönderim Sihirbazı'

    invoice_id = fields.Many2one(
        'account.move', string='Fatura', required=True,
    )
    resend_type = fields.Selection(
        selection=[
            ('same_uuid',    'Teknik Hata — Aynı UUID ile Tekrar Gönder'),
            ('new_invoice',  'İçerik Değişikliği — İptal et ve Yeni Fatura Kes'),
        ],
        string='Tekrar Gönderim Türü',
        required=True,
        default='same_uuid',
    )
    gib_status_code = fields.Integer(
        string='GİB Hata Kodu',
        related='invoice_id.x_gib_status_code',
        readonly=True,
    )
    note = fields.Text(string='Not')

    @api.onchange('invoice_id')
    def _onchange_invoice(self):
        """GİB hata koduna göre önerilen tekrar gönderim türünü otomatik seç."""
        if self.invoice_id:
            code = self.invoice_id.x_gib_status_code
            self.resend_type = 'same_uuid' if code in GIB_RETRY_SAME_UUID else 'new_invoice'

    def action_resend(self):
        self.ensure_one()
        invoice = self.invoice_id

        if invoice.x_efatura_status not in ('error', 'rejected'):
            raise UserError(_(
                'Sadece hatalı (error) veya reddedilmiş faturalar tekrar gönderilebilir.'
            ))

        if self.resend_type == 'new_invoice':
            raise UserError(_(
                'İçerik değişikliği için önce faturayı iptal edin, '
                'ardından yeni fatura kesin. Bu wizard yalnızca teknik '
                'hata (aynı UUID) akışını destekler.'
            ))

        return self._resend_same_uuid(invoice)

    def _resend_same_uuid(self, invoice):
        """
        Mevcut UUID ile UBL yeniden oluşturur ve Sovos'a gönderir.
        Kullanım durumu: 1101, 1103, 1150 vb. teknik hatalar — XML veya
        altta yatan veri düzeltildi, aynı fatura numarası + UUID kullanılır.
        """
        company        = invoice.company_id
        partner        = invoice.partner_id
        uuid           = invoice.x_sovos_uuid
        invoice_number = invoice.name

        if not uuid:
            raise UserError(_('UUID bulunamadı. Yeni fatura kesin.'))

        from ..services.ubl_builder import UblBuilder
        from ..services.ubl_validator import UblValidator

        scenario = invoice.x_efatura_scenario or 'TICARIFATURA'

        # UBL yeniden üret (veri düzeltildikten sonra güncel kayıtlardan)
        try:
            xml_bytes = UblBuilder(company).build(invoice, uuid, invoice_number, scenario)
        except Exception as e:
            raise UserError(_('UBL üretim hatası: %s') % str(e))

        # Validasyon — hata varsa dur, Sovos'a gönderme
        valid, layer, errors = UblValidator().validate(xml_bytes)
        if not valid:
            invoice.write({'x_validation_errors': '\n'.join(errors)})
            raise UserError(
                _('UBL validasyon hatası [%s]: %s') % (layer, errors[0] if errors else '')
            )

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

            invoice.write({
                'x_sovos_envelope_uuid':  envelope_uuid,
                'x_efatura_status':       'sent',
                'x_efatura_error_msg':    False,
                'x_validation_errors':    False,
                'x_gib_status_code':      0,
                'x_gib_admin_notified':   False,
            })
            _logger.info('Tekrar gönderim başarılı: %s (aynı UUID: %s)', invoice_number, uuid)

        except Exception as e:
            invoice._set_error(_('Tekrar gönderim hatası: %s') % str(e))
            raise UserError(_('Tekrar gönderim hatası: %s') % str(e))

        return {'type': 'ir.actions.act_window_close'}
