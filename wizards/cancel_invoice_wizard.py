# -*- coding: utf-8 -*-
import logging
from datetime import date

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# TICARIFATURA iptal edilemez durumlar
TICARIFATURA_NO_CANCEL = {'accepted', 'rejected'}


class CancelInvoiceWizard(models.TransientModel):
    _name = 'sovos.cancel.invoice.wizard'
    _description = 'e-Fatura / e-Arşiv İptal Sihirbazı'

    invoice_id = fields.Many2one('account.move', string='Fatura', required=True)
    cancel_reason = fields.Text(string='İptal Gerekçesi', required=True)
    efatura_type = fields.Char(related='invoice_id.x_efatura_type', readonly=True)
    efatura_scenario = fields.Selection(related='invoice_id.x_efatura_scenario', readonly=True)

    # TEMELFATURA için GİB portal onayı
    gib_portal_confirmed = fields.Boolean(
        string='GİB Portalında iptali tamamladım',
        default=False,
    )
    show_gib_portal_link = fields.Boolean(compute='_compute_show_gib_portal')

    @api.depends('efatura_scenario')
    def _compute_show_gib_portal(self):
        for rec in self:
            rec.show_gib_portal_link = rec.efatura_scenario == 'TEMELFATURA'

    def action_cancel(self):
        self.ensure_one()
        invoice = self.invoice_id
        company = invoice.company_id

        # 8 gün kuralı kontrolü — TICARIFATURA
        if invoice.x_efatura_scenario == 'TICARIFATURA':
            self._check_ticarifatura_cancel_eligibility(invoice)

        # e-Arşiv → API iptal
        if invoice.x_efatura_type == 'earsiv':
            self._cancel_earsiv(invoice, company)

        # TEMELFATURA → GİB portal onayı zorunlu
        elif invoice.x_efatura_scenario == 'TEMELFATURA':
            if not self.gib_portal_confirmed:
                raise UserError(_('TEMELFATURA iptali için GİB portalında işlemi tamamlayıp onay kutucuğunu işaretleyin.'))
            invoice.write({'x_efatura_status': 'cancelled'})
            _logger.info('TEMELFATURA iptali onaylandı (portal): %s', invoice.name)

        # TICARIFATURA → statü matrisine göre
        elif invoice.x_efatura_scenario == 'TICARIFATURA':
            invoice.write({'x_efatura_status': 'cancelled'})

        else:
            invoice.write({'x_efatura_status': 'cancelled'})

        invoice.button_cancel()
        return {'type': 'ir.actions.act_window_close'}

    def _check_ticarifatura_cancel_eligibility(self, invoice):
        """TICARIFATURA iptal matrisi kontrolü."""
        status = invoice.x_efatura_status
        deadline = invoice.x_inv_response_deadline

        if status == 'accepted':
            raise UserError(_('Kabul edilmiş TICARIFATURA iptal edilemez.'))
        if status == 'rejected':
            raise UserError(_('Reddedilmiş fatura zaten iptal sürecindedir. Yeni fatura kesin.'))
        if deadline and date.today() > deadline:
            raise UserError(_(
                '⚠ Hukuki Uyarı: 8 günlük yanıt süresi dolmuştur. '
                'Bu fatura sistem tarafından bloke edilmiştir. '
                'Hukuki danışman ile iletişime geçin.'
            ))

    def _cancel_earsiv(self, invoice, company):
        """e-Arşiv CancelInvoice() API çağrısı."""
        from ..services.sovos_archive_service import SovosArchiveService
        svc = SovosArchiveService(company)
        try:
            success = svc.cancel_invoice(invoice.x_sovos_uuid, self.cancel_reason)
            if success:
                invoice.write({'x_efatura_status': 'cancelled'})
                _logger.info('e-Arşiv iptali başarılı: %s', invoice.x_sovos_uuid)
            else:
                raise UserError(_('e-Arşiv iptal isteği reddedildi. Sovos desteğine başvurun.'))
        except Exception as e:
            raise UserError(_('e-Arşiv iptal hatası: %s') % str(e))
