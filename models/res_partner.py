# -*- coding: utf-8 -*-
import logging
from datetime import date, timedelta
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

EFATURA_TYPE_SELECTION = [
    ('efatura', 'e-Fatura (GİB Kayıtlı)'),
    ('earsiv', 'e-Arşiv (GİB Kayıtsız)'),
]

SCENARIO_SELECTION = [
    ('TICARIFATURA', 'TİCARİFATURA'),
    ('TEMELFATURA', 'TEMELFATURA'),
    ('EARSIVFATURA', 'e-Arşiv Fatura'),
]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_efatura_type = fields.Selection(
        selection=EFATURA_TYPE_SELECTION,
        string='e-Fatura Türü',
        help='Boş: otomatik sorgulanır. Dolu: önce cache\'den okunur.',
    )
    x_default_scenario = fields.Selection(
        selection=SCENARIO_SELECTION,
        string='Varsayılan Senaryo',
        default='TICARIFATURA',
    )
    x_vergi_dairesi = fields.Char(
        string='Vergi Dairesi',
        size=50,
    )
    x_efatura_alias = fields.Char(
        string='e-Fatura GB Kodu (alias)',
        size=50,
        help='Boş bırakılırsa VKN kullanılır.',
    )
    x_efatura_type_updated = fields.Date(
        string='e-Fatura Tip Güncelleme Tarihi',
    )

    def efatura_type_needs_refresh(self):
        """30 günden eski veya boş ise güncelleme gerekir."""
        self.ensure_one()
        if not self.x_efatura_type:
            return True
        if not self.x_efatura_type_updated:
            return True
        age = (date.today() - self.x_efatura_type_updated).days
        return age > 30

    def refresh_efatura_type(self, company):
        """Sovos GetUserList ile VKN'i sorgular, cache günceller."""
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
                'x_efatura_type': new_type,
                'x_efatura_type_updated': date.today(),
            })
            _logger.info('VKN cache güncellendi: %s → %s', vat, new_type)
        except Exception as e:
            _logger.warning('VKN sorgusu başarısız (%s): %s', vat, e)
            # Mevcut değeri koru — iş durma
