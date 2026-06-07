# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class KurFarkiWizard(models.TransientModel):
    _name = 'sovos.kur.farki.wizard'
    _description = 'Kur Farkı Faturası Sihirbazı'

    original_invoice_id = fields.Many2one(
        'account.move', string='Orijinal Fatura', required=True,
    )
    kur_farki_amount = fields.Float(string='Kur Farkı Tutarı (TRY)', required=True)
    kur_farki_date = fields.Date(string='Kur Farkı Tarihi', required=True, default=fields.Date.today)
    description = fields.Text(
        string='Açıklama',
        default='Kur farkı faturası',
    )

    def action_create_kur_farki(self):
        self.ensure_one()
        original = self.original_invoice_id

        if original.x_efatura_status not in ('accepted', 'sent'):
            raise UserError(_('Kur farkı faturası sadece gönderilmiş/kabul edilmiş faturalar için oluşturulabilir.'))

        # Yeni fatura oluştur
        new_invoice = original.copy({
            'invoice_date': self.kur_farki_date,
            'x_kur_farki': True,
            'x_efatura_status': 'draft',
            'x_sovos_uuid': False,
            'x_sovos_envelope_uuid': False,
            'x_reserved_number': False,
            'x_number_status': False,
            'invoice_line_ids': [(5, 0, 0)],  # Satırları temizle
        })

        # Kur farkı satırı ekle
        new_invoice.write({
            'invoice_line_ids': [(0, 0, {
                'name': self.description or 'Kur Farkı — %s' % original.name,
                'quantity': 1,
                'price_unit': self.kur_farki_amount,
                'account_id': new_invoice.journal_id.default_account_id.id,
            })]
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Kur Farkı Faturası'),
            'res_model': 'account.move',
            'res_id': new_invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }
