# -*- coding: utf-8 -*-
"""
product_uom.py — Ölçü Birimi Genişletmesi
==========================================
Odoo'nun uom.uom (birim) modeline UBL-TR birim kodu alanı ekler.

Neden gerekli?
    GİB UBL-TR standardı, fatura kalemlerinin birimini UN/CEFACT kodlarıyla
    ifade etmesini zorunlu kılar. Odoo'da 'Adet', 'Kg', 'Metre' gibi Türkçe
    birimler tutulur; bunların GİB karşılıkları buraya girilir.

Yaygın GİB birim kodları:
    C62 → Adet (en yaygın)
    KGM → Kilogram
    MTR → Metre
    LTR → Litre
    HUR → Saat
    MIN → Dakika
    MON → Ay
    DAY → Gün

Kullanım:
    ubl_builder.py'de: line.product_uom_id.x_ubl_code or DEFAULT_UBL_UNIT ('C62')
    Boş bırakılırsa DEFAULT_UBL_UNIT ('C62' = Adet) kullanılır.
"""
from odoo import models, fields


class ProductUoM(models.Model):
    # uom.uom: Odoo'nun birim modeli (Ayarlar → Birimler)
    _inherit = 'uom.uom'

    x_ubl_code = fields.Char(
        string='UBL Birim Kodu',
        size=10,
        help=(
            'GİB UBL-TR standardındaki birim kodu (UN/CEFACT).\n'
            'Örnekler: C62=Adet, KGM=Kilogram, MTR=Metre, LTR=Litre, HUR=Saat\n'
            'Boş bırakılırsa fatura kalemlerinde varsayılan C62 (Adet) kullanılır.'
        ),
    )
