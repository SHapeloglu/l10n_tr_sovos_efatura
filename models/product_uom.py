# -*- coding: utf-8 -*-
from odoo import models, fields


class ProductUoM(models.Model):
    _inherit = 'uom.uom'

    x_ubl_code = fields.Char(
        string='UBL Birim Kodu',
        size=10,
        help='GİB UBL-TR birim kodu (örn: C62=Adet, KGM=Kilogram, MTR=Metre)',
    )
