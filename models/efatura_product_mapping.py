# -*- coding: utf-8 -*-
"""
efatura_product_mapping.py — Öğrenen Ürün Eşleme Tablosu
=========================================================
Gelen e-Fatura'daki ürün açıklaması ile Odoo ürün kaydı arasındaki
eşlemeyi kalıcı olarak saklar.

Eşleme Hiyerarşisi:
  1. Bu tablo → kesin eşleme, kullanıcı onayı yok (confidence=1.0)
  2. UBL tedarikçi kodu (SellersItemIdentification) → %95 güven
  3. difflib benzerlik skoru >= 0.85 → otomatik öneri, onay gerekli
  4. difflib skoru 0.60-0.84 → liste öneri, kullanıcı seçsin
  5. < 0.60 → manuel eşleme, bekletme kuyruğu

Öğrenme:
  Kullanıcı bir kez "bu açıklama = bu ürün" derse buraya eklenir.
  Aynı tedarikçiden aynı açıklama gelince bir daha sorulmaz.
"""
from odoo import models, fields, api


class EFaturaProductMapping(models.Model):
    _name = 'efatura.product.mapping'
    _description = 'e-Fatura Ürün Eşleme Tablosu'
    _order = 'supplier_id, usage_count desc'
    _rec_name = 'efatura_description'

    # ── Anahtar: Tedarikçi + Açıklama ───────────────────────────────────
    supplier_id = fields.Many2one(
        'res.partner', string='Tedarikçi',
        required=True, ondelete='cascade', index=True,
    )
    efatura_description = fields.Char(
        string='e-Fatura Ürün Açıklaması', required=True,
        help='Gelen faturadaki ham ürün adı. Büyük/küçük harf duyarsız eşleştirilir.',
    )
    efatura_ubl_code = fields.Char(
        string='Tedarikçi Ürün Kodu', size=50,
        help='UBL SellersItemIdentification — tedarikçinin kendi ürün kodu.',
    )

    # ── Odoo Eşlemeleri ──────────────────────────────────────────────────
    product_id = fields.Many2one(
        'product.product', string='Odoo Ürünü', ondelete='set null',
        help='Boş = genel gider satırı oluşturulur.',
    )
    account_id = fields.Many2one(
        'account.account', string='Muhasebe Hesabı', ondelete='set null',
        help='Ürün eşlenemezse bu hesaba yazılır.',
    )
    tax_ids = fields.Many2many(
        'account.tax', string='Vergi',
        help='Boş = UBL\'deki orana göre otomatik bulunur.',
    )
    uom_id = fields.Many2one(
        'uom.uom', string='Birim', ondelete='set null',
        help='Boş = ürünün varsayılan birimi kullanılır.',
    )

    # ── İstatistik ve Güven ──────────────────────────────────────────────
    usage_count = fields.Integer(
        string='Kullanım Sayısı', default=0, readonly=True,
    )
    last_used = fields.Date(string='Son Kullanım', readonly=True)
    confidence = fields.Float(
        string='Güven Skoru (%)', default=100.0, readonly=True,
        help='100=manuel, 95=UBL kodu, 85-99=otomatik yüksek, 60-84=öneri.',
    )

    _sql_constraints = [
        (
            'unique_supplier_description',
            'UNIQUE(supplier_id, efatura_description)',
            'Bu tedarikçi için bu açıklama zaten eşlenmiş.',
        ),
    ]

    def increment_usage(self):
        self.write({'usage_count': self.usage_count + 1, 'last_used': fields.Date.today()})

    @api.model
    def find_mapping(self, supplier_id, description):
        """Tedarikçi + açıklama ile eşleme ara. Returns: kayıt veya False"""
        return self.search([
            ('supplier_id', '=', supplier_id),
            ('efatura_description', '=ilike', description),
        ], limit=1)
