# -*- coding: utf-8 -*-
"""
incoming_invoice_match_wizard.py — Toplu Onay Ekranı (Faz 3)
=============================================================
Bekletme kuyruğundaki eşleşemeyen gelen faturaları listeler.
Kullanıcı her fatura için:
  - Partner seçer (öneri varsa gösterilir)
  - Ürün satırlarını eşler
  - Onaylar → fatura oluşturulur + öğrenen tabloya eklenir

Bu wizard "Bekleyen Gelen Faturalar" menüsünden açılır.
"""
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class IncomingInvoiceMatchWizard(models.TransientModel):
    _name = 'sovos.incoming.match.wizard'
    _description = 'Gelen Fatura Eşleme Toplu Onay'

    invoice_id = fields.Many2one(
        'account.move',
        string='Fatura',
        required=True,
        domain=[('move_type', '=', 'in_invoice'), ('x_efatura_match_status', '=', 'pending')],
    )
    # Partner
    partner_id = fields.Many2one('res.partner', string='Tedarikçi', required=True)
    partner_confidence = fields.Float(string='Partner Güveni (%)', readonly=True)
    partner_source = fields.Char(string='Partner Kaynak', readonly=True)

    # Satırlar
    line_ids = fields.One2many(
        'sovos.incoming.match.wizard.line',
        'wizard_id',
        string='Fatura Kalemleri',
    )

    # Kaydet ve öğren
    save_mappings = fields.Boolean(
        string='Eşlemeleri Öğrenen Tabloya Kaydet',
        default=True,
        help='İşaretliyse bir sonraki aynı tedarikçi faturasında otomatik eşlenir.',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        invoice_id = self.env.context.get('default_invoice_id') or \
                     self.env.context.get('active_id')
        if invoice_id:
            invoice = self.env['account.move'].browse(invoice_id)
            res['invoice_id'] = invoice.id
            res['partner_id'] = invoice.partner_id.id if invoice.partner_id else False
            if 'line_ids' in fields_list:
                res['line_ids'] = self._prepare_line_vals(invoice)
        return res

    @api.model
    def _prepare_line_vals(self, invoice):
        """
        Faturanın ürün satırlarından wizard satırlarını üretir.
        Satırda ürün varsa onu gösterir; yoksa IncomingMatcher önerisini ön doldurur.
        """
        from ..services.incoming_matcher import IncomingMatcher
        matcher = IncomingMatcher(self.env)
        supplier_id = invoice.partner_id.id if invoice.partner_id else False

        commands = []
        for line in invoice.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
            # Cron, düşük güvenli satırların adına "\n[e-Fatura: ...]" notu ekliyor;
            # öğrenen tabloya ham açıklama yazılmalı.
            description = (line.name or '').split('\n[', 1)[0].strip()

            if line.product_id:
                match = {
                    'product': line.product_id,
                    'account': line.account_id,
                    'tax_ids': line.tax_ids,
                    'uom':     line.product_uom_id,
                    'confidence': 1.0,
                    'source':  'invoice_line',
                }
            else:
                match = matcher.find_product(supplier_id, description)

            product = match.get('product')
            account = match.get('account') or line.account_id
            taxes   = match.get('tax_ids') or line.tax_ids
            uom     = match.get('uom') or line.product_uom_id

            commands.append((0, 0, {
                'move_line_id':        line.id,
                'efatura_description': description,
                'efatura_quantity':    line.quantity,
                'efatura_uom_code':    line.product_uom_id.x_ubl_code or '',
                'efatura_unit_price':  line.price_unit,
                'efatura_tax_percent': sum(line.tax_ids.mapped('amount')),
                'confidence':          match.get('confidence', 0.0) * 100,
                'match_source':        match.get('source', 'none'),
                'product_id':          product.id if product else False,
                'account_id':          account.id if account else False,
                'tax_ids':             [(6, 0, taxes.ids)] if taxes else [],
                'uom_id':              uom.id if uom else False,
            }))
        return commands

    def action_confirm(self):
        """
        Eşlemeleri uygula:
          1. Partner ata
          2. Satırları güncelle
          3. Öğrenen tabloya kaydet (işaretliyse)
          4. Fatura durumunu 'matched' yap
        """
        self.ensure_one()
        invoice = self.invoice_id

        # 1. Partner ata
        invoice.write({
            'partner_id': self.partner_id.id,
            'x_efatura_match_status': 'matched',
        })

        # 2. Satırları güncelle
        for wline in self.line_ids:
            if wline.move_line_id:
                vals = {}
                if wline.product_id:
                    vals['product_id'] = wline.product_id.id
                if wline.account_id:
                    vals['account_id'] = wline.account_id.id
                if wline.tax_ids:
                    vals['tax_ids'] = [(6, 0, wline.tax_ids.ids)]
                if wline.uom_id:
                    vals['product_uom_id'] = wline.uom_id.id
                if vals:
                    wline.move_line_id.write(vals)

            # 3. Öğrenen tabloya kaydet
            if self.save_mappings and wline.product_id and wline.efatura_description:
                self._save_mapping(wline)

        return {'type': 'ir.actions.act_window_close'}

    def _save_mapping(self, wline):
        """Kullanıcının onayladığı eşlemeyi öğrenen tabloya ekle."""
        Mapping = self.env['efatura.product.mapping']
        existing = Mapping.find_mapping(
            self.partner_id.id, wline.efatura_description
        )
        if existing:
            existing.write({
                'product_id': wline.product_id.id,
                'account_id': wline.account_id.id if wline.account_id else False,
            })
            existing.increment_usage()
        else:
            Mapping.create({
                'supplier_id':          self.partner_id.id,
                'efatura_description':  wline.efatura_description,
                'product_id':           wline.product_id.id,
                'account_id':           wline.account_id.id if wline.account_id else False,
                'tax_ids':              [(6, 0, wline.tax_ids.ids)] if wline.tax_ids else [],
                'uom_id':               wline.uom_id.id if wline.uom_id else False,
                'confidence':           100.0,
                'usage_count':          1,
                'last_used':            fields.Date.today(),
            })
            _logger.info(
                'Yeni eşleme kaydedildi: "%s" → %s (%s)',
                wline.efatura_description, wline.product_id.name, self.partner_id.name,
            )

    def action_skip(self):
        """Bu faturayı şimdilik atla — kuyruğa bırak."""
        return {'type': 'ir.actions.act_window_close'}


class IncomingInvoiceMatchWizardLine(models.TransientModel):
    _name = 'sovos.incoming.match.wizard.line'
    _description = 'Gelen Fatura Eşleme Satırı'

    wizard_id = fields.Many2one('sovos.incoming.match.wizard', ondelete='cascade')
    move_line_id = fields.Many2one('account.move.line', string='Fatura Satırı', readonly=True)

    # e-Fatura'dan gelen ham veriler (salt okunur)
    efatura_description = fields.Char(string='e-Fatura Açıklaması', readonly=True)
    efatura_quantity    = fields.Float(string='Miktar', readonly=True)
    efatura_uom_code    = fields.Char(string='UBL Birim', readonly=True)
    efatura_unit_price  = fields.Float(string='Birim Fiyat', readonly=True)
    efatura_tax_percent = fields.Float(string='Vergi %', readonly=True)

    # Eşleme önerileri
    confidence = fields.Float(string='Güven (%)', readonly=True)
    match_source = fields.Char(string='Kaynak', readonly=True)

    # Kullanıcı seçimleri
    product_id = fields.Many2one('product.product', string='Odoo Ürünü')
    account_id = fields.Many2one('account.account', string='Muhasebe Hesabı')
    tax_ids    = fields.Many2many('account.tax', string='Vergi')
    uom_id     = fields.Many2one('uom.uom', string='Birim')
