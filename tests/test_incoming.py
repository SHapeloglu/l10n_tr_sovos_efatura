# -*- coding: utf-8 -*-
"""
Gelen Fatura Testleri — v8
===========================
Test edilen kod:
    services/ubl_parser.py                  → UblParser
    services/incoming_matcher.py            → IncomingMatcher (Faz 1/2/3)
    models/efatura_product_mapping.py       → efatura.product.mapping (öğrenen tablo)
    models/sovos_sync.py                    → _sync_incoming_for_company (uçtan uca)
    wizards/incoming_invoice_match_wizard.py → sovos.incoming.match.wizard

AKIŞ:
    Sovos GetUblList → her UUID için GetUBL → UblParser.parse()
    → IncomingMatcher: partner (VKN → unvan benzerliği), ürün (öğrenen tablo →
      UBL kodu → kural motoru + difflib), vergi, birim, gider hesabı
    → in_invoice + satırlar + x_efatura_match_status (matched_auto / review / pending)
    → bekleyenler sihirbazla eşlenir, onaylanan eşleme öğrenen tabloya yazılır

Sovos çağrıları mock'lanır; UBL örnekleri bu dosyada üretilir (gerçek VKN yok).
"""
import os
import tempfile
from datetime import date
from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo.tools import mute_logger

from odoo.addons.l10n_tr_sovos_efatura.services.incoming_matcher import IncomingMatcher
from odoo.addons.l10n_tr_sovos_efatura.services.sovos_invoice_service import SovosInvoiceService
from odoo.addons.l10n_tr_sovos_efatura.services.ubl_parser import UblParser

from .common import SovosTestCommon

SUPPLIER_VKN = '1111111111'
UNIT_CODE = 'ZZU'   # testte uom.product_uom_unit'e atanan UBL birim kodu


def _ubl_line(line_id, description, qty=1.0, price=100.0, percent=20.0,
              code='', unit=UNIT_CODE, name=None):
    """Tek bir cac:InvoiceLine XML parçası."""
    total = qty * price
    seller_id = (
        '<cac:SellersItemIdentification><cbc:ID>%s</cbc:ID></cac:SellersItemIdentification>' % code
        if code else ''
    )
    desc = '<cbc:Description>%s</cbc:Description>' % description if description else ''
    return (
        '<cac:InvoiceLine>'
        '<cbc:ID>%s</cbc:ID>'
        '<cbc:InvoicedQuantity unitCode="%s">%s</cbc:InvoicedQuantity>'
        '<cbc:LineExtensionAmount currencyID="TRY">%.2f</cbc:LineExtensionAmount>'
        '<cac:TaxTotal><cbc:TaxAmount currencyID="TRY">%.2f</cbc:TaxAmount>'
        '<cac:TaxSubtotal><cbc:Percent>%s</cbc:Percent></cac:TaxSubtotal></cac:TaxTotal>'
        '<cac:Item>%s<cbc:Name>%s</cbc:Name>%s</cac:Item>'
        '<cac:Price><cbc:PriceAmount currencyID="TRY">%.2f</cbc:PriceAmount></cac:Price>'
        '</cac:InvoiceLine>'
    ) % (line_id, unit, qty, total, total * percent / 100, percent,
         desc, name or description, seller_id, price)


def _ubl_invoice(lines, uuid='11111111-2222-3333-4444-555555555555',
                 sender_vkn=SUPPLIER_VKN, sender_name='Anadolu Kırtasiye Ltd. Şti.',
                 currency='TRY', notes=('Sipariş no: 42',), type_code='SATIS'):
    """Gelen e-Fatura UBL-TR XML'i (bytes)."""
    notes_xml = ''.join('<cbc:Note>%s</cbc:Note>' % n for n in notes)
    type_xml = '<cbc:InvoiceTypeCode>%s</cbc:InvoiceTypeCode>' % type_code if type_code else ''
    cur_xml = '<cbc:DocumentCurrencyCode>%s</cbc:DocumentCurrencyCode>' % currency if currency else ''
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"'
        ' xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"'
        ' xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">'
        '<cbc:UBLVersionID>2.1</cbc:UBLVersionID>'
        '<cbc:ID>ANK2026000000123</cbc:ID>'
        '<cbc:UUID>%s</cbc:UUID>'
        '<cbc:IssueDate>2026-09-15</cbc:IssueDate>'
        '%s%s%s'
        '<cac:AccountingSupplierParty><cac:Party>'
        '<cac:PartyName><cbc:Name>%s</cbc:Name></cac:PartyName>'
        '<cac:PartyTaxScheme><cbc:CompanyID>%s</cbc:CompanyID>'
        '<cac:TaxScheme><cbc:Name>Çankaya</cbc:Name></cac:TaxScheme></cac:PartyTaxScheme>'
        '</cac:Party></cac:AccountingSupplierParty>'
        '<cac:AccountingCustomerParty><cac:Party>'
        '<cac:PartyTaxScheme><cbc:CompanyID>1234567890</cbc:CompanyID></cac:PartyTaxScheme>'
        '</cac:Party></cac:AccountingCustomerParty>'
        '<cac:TaxTotal><cbc:TaxAmount currencyID="TRY">40.00</cbc:TaxAmount></cac:TaxTotal>'
        '<cac:LegalMonetaryTotal>'
        '<cbc:TaxExclusiveAmount currencyID="TRY">200.00</cbc:TaxExclusiveAmount>'
        '<cbc:TaxInclusiveAmount currencyID="TRY">240.00</cbc:TaxInclusiveAmount>'
        '</cac:LegalMonetaryTotal>'
        '%s'
        '</Invoice>'
    ) % (uuid, type_xml, notes_xml, cur_xml, sender_name, sender_vkn, ''.join(lines))
    return xml.encode('utf-8')


class IncomingTestCommon(SovosTestCommon):
    """Gelen fatura testleri için tedarikçi, ürün, vergi, birim ve gider hesabı."""

    def setUp(self):
        super().setUp()
        self.supplier = self.env['res.partner'].create({
            'name': 'Anadolu Kırtasiye Ltd. Şti.',
            'vat': SUPPLIER_VKN,
            'supplier_rank': 1,
        })
        self.chair = self.env['product.product'].create({
            'name': 'Ofis Sandalyesi Ergonomik',
            'default_code': 'OS-12',
            'type': 'consu',
            'purchase_ok': True,
        })
        # Oranı alışılmadık seçildi: hesap planındaki vergilerle çakışmasın
        self.tax_purchase = self.env['account.tax'].create({
            'name': 'Test Alış KDV %17.5',
            'amount': 17.5,
            'amount_type': 'percent',
            'type_tax_use': 'purchase',
            'company_id': self.company.id,
        })
        self.uom_unit = self.env.ref('uom.product_uom_unit')
        self.uom_unit.x_ubl_code = UNIT_CODE
        self.account_expense = self.env['account.account'].search([
            ('account_type', '=', 'expense'),
            ('company_ids', 'in', self.company.id),
            ('deprecated', '=', False),
        ], limit=1)
        self.matcher = IncomingMatcher(self.env)


# ════════════════════════════════════════════════════════════════════════════
# UBL PARSER
# ════════════════════════════════════════════════════════════════════════════

class TestUblParser(SovosTestCommon):
    """UblParser.parse(): UBL-TR XML → dict."""

    def test_parse_header_parties_totals_and_notes(self):
        parsed = UblParser().parse(_ubl_invoice(
            [_ubl_line(1, 'Kalem')], notes=('Sipariş no: 42', '   ', 'İrsaliye 7'),
        ))
        self.assertEqual(parsed['uuid'], '11111111-2222-3333-4444-555555555555')
        self.assertEqual(parsed['invoice_number'], 'ANK2026000000123')
        self.assertEqual(parsed['invoice_date'], '2026-09-15')
        self.assertEqual(parsed['invoice_type_code'], 'SATIS')
        self.assertEqual(parsed['currency'], 'TRY')
        self.assertEqual(parsed['sender_vkn'], SUPPLIER_VKN)
        self.assertEqual(parsed['sender_name'], 'Anadolu Kırtasiye Ltd. Şti.')
        self.assertEqual(parsed['sender_tax_office'], 'Çankaya')
        self.assertEqual(parsed['receiver_vkn'], '1234567890')
        self.assertEqual(parsed['amount_untaxed'], 200.0)
        self.assertEqual(parsed['amount_tax'], 40.0)
        self.assertEqual(parsed['amount_total'], 240.0)
        # Boş not atlanır
        self.assertEqual(parsed['notes'], ['Sipariş no: 42', 'İrsaliye 7'])

    def test_parse_lines(self):
        parsed = UblParser().parse(_ubl_invoice([
            _ubl_line(1, 'Ofis Sandalyesi', qty=2, price=150.0, percent=20, code='OS-12', unit='KGM'),
            _ubl_line(2, 'Masa Lambası', qty=1, price=50.0, percent=10),
        ]))
        self.assertEqual(len(parsed['lines']), 2)
        first = parsed['lines'][0]
        self.assertEqual(first['line_id'], '1')
        self.assertEqual(first['description'], 'Ofis Sandalyesi')
        self.assertEqual(first['ubl_code'], 'OS-12')
        self.assertEqual(first['quantity'], 2.0)
        self.assertEqual(first['uom_code'], 'KGM')
        self.assertEqual(first['unit_price'], 150.0)
        self.assertEqual(first['line_total'], 300.0)
        self.assertEqual(first['tax_percent'], 20.0)
        self.assertEqual(first['tax_amount'], 60.0)
        self.assertEqual(parsed['lines'][1]['ubl_code'], '')

    def test_parse_line_description_falls_back_to_item_name(self):
        parsed = UblParser().parse(_ubl_invoice([_ubl_line(1, '', name='Sadece Ad')]))
        self.assertEqual(parsed['lines'][0]['description'], 'Sadece Ad')

    def test_parse_defaults_for_missing_optional_fields(self):
        """InvoiceTypeCode / para birimi / gönderici / birim kodu yoksa varsayılanlar."""
        xml = (
            b'<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"'
            b' xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"'
            b' xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">'
            b'<cbc:UUID>u-1</cbc:UUID>'
            b'<cac:InvoiceLine><cbc:ID>1</cbc:ID>'
            b'<cac:Price><cbc:PriceAmount>abc</cbc:PriceAmount></cac:Price></cac:InvoiceLine>'
            b'</Invoice>'
        )
        parsed = UblParser().parse(xml)
        self.assertEqual(parsed['invoice_type_code'], 'SATIS')
        self.assertEqual(parsed['currency'], 'TRY')
        self.assertEqual((parsed['sender_vkn'], parsed['sender_name'], parsed['receiver_vkn']), ('', '', ''))
        self.assertEqual(parsed['amount_total'], 0.0)
        self.assertEqual(parsed['notes'], [])
        line = parsed['lines'][0]
        self.assertEqual(line['uom_code'], 'C62')
        self.assertEqual(line['quantity'], 1.0)
        # Sayısal olmayan değer → 0.0 (exception yok)
        self.assertEqual(line['unit_price'], 0.0)

    def test_parse_invalid_xml_raises_value_error(self):
        with self.assertRaises(ValueError):
            UblParser().parse(b'<Invoice><cbc:ID>kapanmamis')

    def test_parse_does_not_resolve_external_entities(self):
        """XXE: tedarikçi XML'indeki SYSTEM entity yerel dosyayı okuyamamalı."""
        fd, path = tempfile.mkstemp(suffix='.txt')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write('GIZLI-DOSYA-ICERIGI')
            xml = (
                '<?xml version="1.0"?>'
                '<!DOCTYPE Invoice [<!ENTITY xxe SYSTEM "file://%s">]>'
                '<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"'
                ' xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">'
                '<cbc:UUID>u-xxe</cbc:UUID><cbc:Note>&xxe;</cbc:Note>'
                '</Invoice>' % path
            ).encode()
            parsed = UblParser().parse(xml)
        finally:
            os.unlink(path)
        self.assertNotIn('GIZLI-DOSYA-ICERIGI', repr(parsed))


# ════════════════════════════════════════════════════════════════════════════
# EŞLEME MOTORU
# ════════════════════════════════════════════════════════════════════════════

class TestIncomingMatcherPartner(IncomingTestCommon):
    """IncomingMatcher.find_partner(): VKN kesin eşleme → unvan benzerliği."""

    def test_vkn_exact_match(self):
        partner, conf, source = self.matcher.find_partner(SUPPLIER_VKN, 'Bambaşka Bir Ad')
        self.assertEqual((partner, conf, source), (self.supplier, 1.0, 'vkn_exact'))

    def test_name_fuzzy_auto_when_vkn_unknown(self):
        partner, conf, source = self.matcher.find_partner('9090909090', 'Anadolu Kırtasiye Ltd Şti')
        self.assertEqual(partner, self.supplier)
        self.assertEqual(source, 'fuzzy_auto')
        self.assertGreaterEqual(conf, 0.85)

    def test_name_fuzzy_suggest_band(self):
        # 'Anadolu Kırtasiye' ↔ 'Anadolu Kırtasiye Ltd. Şti.' ≈ 0.77
        partner, conf, source = self.matcher.find_partner('', 'Anadolu Kırtasiye')
        self.assertEqual(partner, self.supplier)
        self.assertEqual(source, 'fuzzy_suggest')
        self.assertTrue(0.60 <= conf < 0.85)

    def test_name_fuzzy_ignores_non_suppliers(self):
        self.supplier.supplier_rank = 0
        partner, conf, source = self.matcher.find_partner('', 'Anadolu Kırtasiye Ltd Şti')
        self.assertNotEqual(partner, self.supplier)

    def test_no_vkn_no_name_returns_none(self):
        self.assertEqual(self.matcher.find_partner('', ''), (False, 0.0, 'none'))

    def test_low_similarity_returns_none(self):
        self.assertEqual(
            self.matcher.find_partner('9090909090', 'Ege Ambalaj Sanayi XYZQ'),
            (False, 0.0, 'none'),
        )


class TestIncomingMatcherProduct(IncomingTestCommon):
    """IncomingMatcher.find_product(): öğrenen tablo → UBL kodu → kural + difflib."""

    def test_learned_mapping_wins_and_counts_usage(self):
        mapping = self.env['efatura.product.mapping'].create({
            'supplier_id': self.supplier.id,
            'efatura_description': 'KAGIT A4 80GR',
            'product_id': self.product.id,
            'account_id': self.account_expense.id,
            'tax_ids': [(6, 0, self.tax_purchase.ids)],
            'uom_id': self.uom_unit.id,
        })
        # Açıklama büyük/küçük harf duyarsız; UBL kodu başka ürünü gösterse de tablo öncelikli
        res = self.matcher.find_product(self.supplier.id, 'kagit a4 80gr', ubl_code='OS-12')
        self.assertEqual(res['product'], self.product)
        self.assertEqual(res['account'], self.account_expense)
        self.assertEqual(res['tax_ids'], self.tax_purchase)
        self.assertEqual(res['uom'], self.uom_unit)
        self.assertEqual((res['confidence'], res['source']), (1.0, 'learned_mapping'))
        self.assertEqual(mapping.usage_count, 1)
        self.assertEqual(mapping.last_used, date.today())

    def test_learned_mapping_is_per_supplier(self):
        other = self.env['res.partner'].create({'name': 'Başka Tedarikçi', 'supplier_rank': 1})
        self.env['efatura.product.mapping'].create({
            'supplier_id': other.id,
            'efatura_description': 'Masa Lambası LED',
            'product_id': self.product.id,
        })
        res = self.matcher.find_product(self.supplier.id, 'Masa Lambası LED')
        self.assertNotEqual(res['source'], 'learned_mapping')

    def test_ubl_code_match(self):
        res = self.matcher.find_product(self.supplier.id, 'Tamamen farklı açıklama', ubl_code='OS-12')
        self.assertEqual(res['product'], self.chair)
        self.assertEqual((res['confidence'], res['source']), (0.95, 'ubl_code'))
        self.assertFalse(res['account'])

    def test_difflib_auto(self):
        # Sondaki tire ve çoklu boşluk normalleştirilir
        res = self.matcher.find_product(False, '  Ofis   Sandalyesi Ergonomik - ')
        self.assertEqual(res['product'], self.chair)
        self.assertEqual(res['source'], 'difflib_auto')
        self.assertGreaterEqual(res['confidence'], 0.85)

    def test_difflib_suggest_band(self):
        # 'Ofis Sandalyesi' ↔ 'Ofis Sandalyesi Ergonomik' = 0.75
        res = self.matcher.find_product(False, 'Ofis Sandalyesi')
        self.assertEqual(res['product'], self.chair)
        self.assertEqual(res['source'], 'difflib_suggest')
        self.assertTrue(0.60 <= res['confidence'] < 0.85)

    def test_difflib_matches_purchase_description(self):
        self.product.description_purchase = 'Kartuş Toner Siyah'
        res = self.matcher.find_product(False, 'Kartuş Toner Siyah')
        self.assertEqual(res['product'], self.product)
        self.assertEqual(res['source'], 'difflib_auto')

    def test_difflib_skips_products_not_purchasable(self):
        self.chair.purchase_ok = False
        res = self.matcher.find_product(False, 'Ofis Sandalyesi Ergonomik')
        self.assertNotEqual(res['product'], self.chair)

    def test_supplier_rules_strip_prefix_and_code_suffix(self):
        raw = 'TR- Ofis Sandalyesi Ergonomik (OS-12)'
        self.assertEqual(
            self.matcher._apply_supplier_rules(self.supplier.id, raw),
            'Ofis Sandalyesi Ergonomik',
        )
        # Tedarikçi yoksa yalnız genel normalleştirme
        self.assertEqual(self.matcher._apply_supplier_rules(False, raw), raw)
        # Kural sonrası tam eşleşme → otomatik
        res = self.matcher.find_product(self.supplier.id, raw)
        self.assertEqual((res['product'], res['confidence']), (self.chair, 1.0))

    def test_no_match_returns_empty_result(self):
        res = self.matcher.find_product(self.supplier.id, 'Qwxz Plmk 9981')
        self.assertEqual(res, {
            'product': False, 'account': False, 'tax_ids': False,
            'uom': False, 'confidence': 0.0, 'source': 'none',
        })


class TestIncomingMatcherHelpers(IncomingTestCommon):
    """Vergi, birim ve gider hesabı yardımcıları."""

    def test_find_tax_purchase_only(self):
        self.env['account.tax'].create({
            'name': 'Test Satış KDV %17.5',
            'amount': 17.5,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'company_id': self.company.id,
        })
        self.assertEqual(self.matcher.find_tax(17.5, self.company), self.tax_purchase)

    def test_find_tax_zero_or_missing_returns_false(self):
        self.assertFalse(self.matcher.find_tax(0.0, self.company))
        self.assertFalse(self.matcher.find_tax(None, self.company))

    def test_find_uom_by_ubl_code(self):
        self.assertEqual(self.matcher.find_uom(UNIT_CODE), self.uom_unit)
        self.assertFalse(self.matcher.find_uom('YOK'))
        self.assertFalse(self.matcher.find_uom(''))

    def test_find_expense_account(self):
        account = self.matcher.find_expense_account(self.company)
        self.assertTrue(account)
        self.assertEqual(account.account_type, 'expense')
        self.assertIn(self.company, account.company_ids)


# ════════════════════════════════════════════════════════════════════════════
# ÖĞRENEN TABLO
# ════════════════════════════════════════════════════════════════════════════

class TestProductMapping(IncomingTestCommon):
    """efatura.product.mapping modeli."""

    def _mapping(self, supplier=None, description='Masa Lambası LED', **kw):
        vals = {
            'supplier_id': (supplier or self.supplier).id,
            'efatura_description': description,
            'product_id': self.product.id,
        }
        vals.update(kw)
        return self.env['efatura.product.mapping'].create(vals)

    def test_unique_supplier_description(self):
        self._mapping()
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self._mapping()
            self.env.flush_all()

    def test_same_description_allowed_for_other_supplier(self):
        other = self.env['res.partner'].create({'name': 'Başka Tedarikçi'})
        self._mapping()
        self.assertTrue(self._mapping(supplier=other))

    def test_find_mapping_case_insensitive(self):
        mapping = self._mapping(description='Toner HP 85A')
        Mapping = self.env['efatura.product.mapping']
        self.assertEqual(Mapping.find_mapping(self.supplier.id, 'TONER hp 85a'), mapping)
        self.assertFalse(Mapping.find_mapping(self.supplier.id, 'Toner HP 85'))

    def test_increment_usage(self):
        mapping = self._mapping(usage_count=4)
        mapping.increment_usage()
        self.assertEqual(mapping.usage_count, 5)
        self.assertEqual(mapping.last_used, date.today())

    def test_mapping_deleted_with_supplier(self):
        supplier = self.env['res.partner'].create({'name': 'Silinecek Tedarikçi'})
        mapping = self._mapping(supplier=supplier)
        supplier.unlink()
        self.assertFalse(mapping.exists())


# ════════════════════════════════════════════════════════════════════════════
# UÇTAN UCA SENKRONİZASYON
# ════════════════════════════════════════════════════════════════════════════

class TestIncomingSync(IncomingTestCommon):
    """_sync_incoming_for_company(): liste → UBL → parse → eşleme → in_invoice."""

    def _sync(self, xml=None, uuid='11111111-2222-3333-4444-555555555555',
              sender_vkn=SUPPLIER_VKN, ubl_error=None):
        header = [{'uuid': uuid, 'sender_vkn': sender_vkn, 'invoice_date': '2026-09-14'}]
        ubl_kw = {'side_effect': ubl_error} if ubl_error else {'return_value': xml}
        with patch.object(SovosInvoiceService, 'get_inbound_list', return_value=header), \
                patch.object(SovosInvoiceService, 'get_invoice_ubl', **ubl_kw):
            self.env['sovos.sync']._sync_incoming_for_company(self.company)
        return self.env['account.move'].search([
            ('x_sovos_uuid', '=', uuid), ('move_type', '=', 'in_invoice'),
        ])

    def test_full_match_creates_invoice_matched_auto(self):
        move = self._sync(_ubl_invoice([
            _ubl_line(1, 'Ofis Sandalyesi Mavi', qty=2, price=1500.0, percent=17.5, code='OS-12'),
        ]))
        self.assertEqual(len(move), 1)
        self.assertEqual(move.partner_id, self.supplier)
        self.assertEqual(move.x_efatura_match_status, 'matched_auto')
        self.assertEqual(move.x_efatura_status, 'accepted')
        self.assertEqual(move.state, 'draft')
        self.assertEqual(move.invoice_date, date(2026, 9, 15))  # UBL IssueDate, başlık değil
        self.assertIn('Sipariş no: 42', move.narration)
        line = move.invoice_line_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(line.product_id, self.chair)
        self.assertEqual(line.quantity, 2.0)
        self.assertEqual(line.price_unit, 1500.0)
        self.assertEqual(line.tax_ids, self.tax_purchase)
        self.assertEqual(line.product_uom_id, self.uom_unit)
        # Güvenli eşleme (ubl_code) → açıklamaya eşleme notu eklenmez
        self.assertEqual(line.name, 'Ofis Sandalyesi Mavi')

    def test_unmatched_line_goes_to_expense_and_review(self):
        move = self._sync(_ubl_invoice([
            _ubl_line(1, 'Ofis Sandalyesi Mavi', price=1500.0, percent=17.5, code='OS-12'),
            _ubl_line(2, 'Qwxz Plmk 9981', price=75.0, percent=17.5),
        ]))
        self.assertEqual(move.partner_id, self.supplier)
        self.assertEqual(move.x_efatura_match_status, 'review')
        unmatched = move.invoice_line_ids.filtered(lambda l: not l.product_id)
        self.assertEqual(len(unmatched), 1)
        self.assertEqual(unmatched.account_id, self.matcher.find_expense_account(self.company))
        # Düşük güven → kullanıcı görsün diye eşleme notu
        self.assertIn('Eşleme: none (0%)', unmatched.name)

    def test_unknown_sender_is_pending(self):
        move = self._sync(
            _ubl_invoice([_ubl_line(1, 'Ofis Sandalyesi Mavi', code='OS-12')],
                         sender_vkn='2020202020', sender_name='Ege Ambalaj Sanayi XYZQ'),
            sender_vkn='2020202020',
        )
        self.assertFalse(move.partner_id)
        self.assertEqual(move.x_efatura_match_status, 'pending')

    def test_partner_by_name_suggest_is_review(self):
        move = self._sync(
            _ubl_invoice([_ubl_line(1, 'Ofis Sandalyesi Mavi', code='OS-12')],
                         sender_vkn='2020202020', sender_name='Anadolu Kırtasiye'),
            sender_vkn='2020202020',
        )
        self.assertEqual(move.partner_id, self.supplier)
        self.assertEqual(move.x_efatura_match_status, 'review')

    def test_learned_mapping_used_on_next_invoice(self):
        mapping = self.env['efatura.product.mapping'].create({
            'supplier_id': self.supplier.id,
            'efatura_description': 'Qwxz Plmk 9981',
            'product_id': self.product.id,
        })
        move = self._sync(_ubl_invoice([_ubl_line(1, 'Qwxz Plmk 9981', percent=17.5)]))
        self.assertEqual(move.invoice_line_ids.product_id, self.product)
        self.assertEqual(move.x_efatura_match_status, 'matched_auto')
        self.assertEqual(mapping.usage_count, 1)

    def test_foreign_currency_from_ubl(self):
        eur = self.env.ref('base.EUR')
        eur.active = True
        move = self._sync(_ubl_invoice([_ubl_line(1, 'Ofis Sandalyesi Mavi', code='OS-12')], currency='EUR'))
        self.assertEqual(move.currency_id, eur)

    def test_ubl_fetch_failure_falls_back_to_header(self):
        """GetUBL başarısız → fatura başlık bilgisiyle, satırsız oluşur; inceleme bekler."""
        move = self._sync(ubl_error=Exception('Sovos zaman aşımı'))
        self.assertEqual(len(move), 1)
        self.assertEqual(move.partner_id, self.supplier)
        self.assertEqual(move.invoice_date, date(2026, 9, 14))
        self.assertFalse(move.invoice_line_ids)
        self.assertEqual(move.x_efatura_match_status, 'review')

    def test_unparseable_ubl_falls_back_to_header(self):
        move = self._sync(b'<bozuk')
        self.assertEqual(len(move), 1)
        self.assertFalse(move.invoice_line_ids)
        self.assertEqual(move.x_efatura_match_status, 'review')


# ════════════════════════════════════════════════════════════════════════════
# EŞLEME SİHİRBAZI
# ════════════════════════════════════════════════════════════════════════════

class TestIncomingMatchWizard(IncomingTestCommon):
    """sovos.incoming.match.wizard: bekleyen faturayı eşle, öğrenen tabloya yaz."""

    def setUp(self):
        super().setUp()
        self.invoice = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'invoice_date': date.today(),
            'x_sovos_uuid': 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
            'x_efatura_match_status': 'pending',
            'invoice_line_ids': [(0, 0, {
                'name': 'Masa Lambası LED',
                'quantity': 3,
                'price_unit': 100.0,
                'account_id': self.account_expense.id,
            })],
        })
        self.move_line = self.invoice.invoice_line_ids

    def _wizard(self, save_mappings=True, product=None):
        product = product or self.product
        return self.env['sovos.incoming.match.wizard'].create({
            'invoice_id': self.invoice.id,
            'partner_id': self.supplier.id,
            'save_mappings': save_mappings,
            'line_ids': [(0, 0, {
                'move_line_id': self.move_line.id,
                'efatura_description': 'Masa Lambası LED',
                'product_id': product.id,
                'tax_ids': [(6, 0, self.tax_purchase.ids)],
            })],
        })

    def test_open_wizard_action(self):
        action = self.invoice.action_open_incoming_match_wizard()
        self.assertEqual(action['res_model'], 'sovos.incoming.match.wizard')
        self.assertEqual(action['context'], {'default_invoice_id': self.invoice.id})

    def test_default_get_from_active_id(self):
        self.invoice.partner_id = self.supplier
        defaults = self.env['sovos.incoming.match.wizard'].with_context(
            active_id=self.invoice.id,
        ).default_get(['invoice_id', 'partner_id'])
        self.assertEqual(defaults['invoice_id'], self.invoice.id)
        self.assertEqual(defaults['partner_id'], self.supplier.id)

    def test_confirm_applies_partner_lines_and_learns(self):
        result = self._wizard().action_confirm()
        self.assertEqual(result, {'type': 'ir.actions.act_window_close'})
        self.assertEqual(self.invoice.partner_id, self.supplier)
        self.assertEqual(self.invoice.x_efatura_match_status, 'matched')
        self.assertEqual(self.move_line.product_id, self.product)
        self.assertEqual(self.move_line.tax_ids, self.tax_purchase)
        mapping = self.env['efatura.product.mapping'].find_mapping(self.supplier.id, 'Masa Lambası LED')
        self.assertEqual(mapping.product_id, self.product)
        self.assertEqual(mapping.tax_ids, self.tax_purchase)
        self.assertEqual((mapping.confidence, mapping.usage_count), (100.0, 1))

    def test_confirm_without_save_does_not_learn(self):
        self._wizard(save_mappings=False).action_confirm()
        self.assertEqual(self.invoice.x_efatura_match_status, 'matched')
        self.assertFalse(
            self.env['efatura.product.mapping'].find_mapping(self.supplier.id, 'Masa Lambası LED')
        )

    def test_confirm_updates_existing_mapping(self):
        mapping = self.env['efatura.product.mapping'].create({
            'supplier_id': self.supplier.id,
            'efatura_description': 'masa lambası led',
            'product_id': self.chair.id,
            'usage_count': 3,
        })
        self._wizard().action_confirm()
        self.assertEqual(mapping.product_id, self.product)
        self.assertEqual(mapping.usage_count, 4)
        self.assertEqual(
            self.env['efatura.product.mapping'].search_count([('supplier_id', '=', self.supplier.id)]), 1,
        )

    def test_learned_mapping_found_by_matcher(self):
        """Sihirbazda öğrenilen eşleme, aynı tedarikçinin sonraki faturasında otomatik kullanılır."""
        self._wizard().action_confirm()
        # Not: PostgreSQL ILIKE 'ı'↔'I' eşlemez; Türkçe harfler aynı yazımla aranır
        res = self.matcher.find_product(self.supplier.id, 'masa lambası LED')
        self.assertEqual((res['product'], res['source']), (self.product, 'learned_mapping'))

    def test_skip_keeps_invoice_pending(self):
        self._wizard().action_skip()
        self.assertEqual(self.invoice.x_efatura_match_status, 'pending')
        self.assertFalse(self.move_line.product_id)
