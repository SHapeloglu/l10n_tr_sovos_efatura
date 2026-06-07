# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    # ── e-Fatura (InvoiceService) ──────────────────────────────────────────
    x_sovos_invoice_user = fields.Char(
        string='e-Fatura Kullanıcı Adı',
        groups='base.group_system',
    )
    x_sovos_invoice_pass = fields.Char(
        string='e-Fatura Şifresi',
        groups='base.group_system',
    )
    x_sovos_sender_vkn = fields.Char(
        string='Gönderici VKN',
        size=11,
    )
    x_sovos_identifier = fields.Char(
        string='Gönderici Posta Kutusu (GB Kodu)',
    )
    x_invoice_sequence_id = fields.Many2one(
        'ir.sequence',
        string='e-Fatura Numara Serisi',
    )

    # ── e-Arşiv (ArchiveService) ───────────────────────────────────────────
    x_sovos_archive_user = fields.Char(
        string='e-Arşiv Kullanıcı Adı',
        groups='base.group_system',
    )
    x_sovos_archive_pass = fields.Char(
        string='e-Arşiv Şifresi',
        groups='base.group_system',
    )
    x_sovos_template_id = fields.Char(
        string='Sovos Şablon ID',
    )

    # ── Genel ─────────────────────────────────────────────────────────────
    x_sovos_test_mode = fields.Boolean(
        string='Test Modu (GİB\'e İletilmez)',
        default=True,
    )
    x_sovos_admin_email = fields.Char(
        string='Hata Bildirim E-postası',
    )

    # ── Bağlantı Testi ────────────────────────────────────────────────────
    def action_test_invoice_connection(self):
        """InvoiceService bağlantı testi."""
        self.ensure_one()
        from ..services.sovos_invoice_service import SovosInvoiceService
        svc = SovosInvoiceService(self)
        ok, msg = svc.test_connection()
        if ok:
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
        raise UserError(_('e-Fatura bağlantı hatası: %s') % msg)

    def action_test_archive_connection(self):
        """ArchiveService bağlantı testi."""
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
