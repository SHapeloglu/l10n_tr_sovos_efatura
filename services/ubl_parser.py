# -*- coding: utf-8 -*-
"""
ubl_parser.py — Gelen e-Fatura UBL-TR 2.1 XML Parse Servisi
============================================================
Sovos'tan alınan ham UBL-TR 2.1 XML'ini Odoo'nun anlayacağı
dict yapısına çevirir.

Döndürülen yapı:
{
    'uuid': str,
    'invoice_number': str,
    'invoice_date': str (YYYY-MM-DD),
    'invoice_type_code': str,       # SATIS / IADE
    'currency': str,
    'sender_vkn': str,
    'sender_name': str,
    'sender_tax_office': str,
    'receiver_vkn': str,
    'amount_untaxed': float,
    'amount_tax': float,
    'amount_total': float,
    'lines': [
        {
            'line_id': str,
            'description': str,
            'ubl_code': str,        # SellersItemIdentification
            'quantity': float,
            'uom_code': str,        # C62, KGM vb.
            'unit_price': float,
            'line_total': float,
            'tax_percent': float,
            'tax_amount': float,
        },
        ...
    ],
    'notes': [str],
}
"""
import logging
from lxml import etree

_logger = logging.getLogger(__name__)

NS = {
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
}


def _txt(el, xpath, default=''):
    r = el.xpath(xpath, namespaces=NS)
    if r:
        v = r[0]
        return (v.text or '').strip() if hasattr(v, 'text') else str(v).strip()
    return default


def _flt(el, xpath, default=0.0):
    t = _txt(el, xpath)
    try:
        return float(t) if t else default
    except (ValueError, TypeError):
        return default


class UblParser:
    """Gelen e-Fatura UBL-TR 2.1 XML parse servisi."""

    def parse(self, xml_bytes):
        """
        UBL-TR XML'i parse eder.
        Raises: ValueError — XML parse edilemezse
        Returns: dict (yukarıdaki yapı)
        """
        try:
            root = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as e:
            raise ValueError('UBL XML parse hatası: %s' % e)

        result = {
            'uuid':              _txt(root, 'cbc:UUID'),
            'invoice_number':    _txt(root, 'cbc:ID'),
            'invoice_date':      _txt(root, 'cbc:IssueDate'),
            'invoice_type_code': _txt(root, 'cbc:InvoiceTypeCode', 'SATIS'),
            'currency':          _txt(root, 'cbc:DocumentCurrencyCode', 'TRY'),
        }

        # ── Gönderici ────────────────────────────────────────────────────
        s = root.find('.//cac:AccountingSupplierParty/cac:Party', NS)
        if s is not None:
            result['sender_name']       = _txt(s, 'cac:PartyName/cbc:Name')
            result['sender_vkn']        = _txt(s, 'cac:PartyTaxScheme/cbc:CompanyID')
            result['sender_tax_office'] = _txt(s, 'cac:PartyTaxScheme/cac:TaxScheme/cbc:Name')
        else:
            result.update(sender_name='', sender_vkn='', sender_tax_office='')

        # ── Alıcı ────────────────────────────────────────────────────────
        c = root.find('.//cac:AccountingCustomerParty/cac:Party', NS)
        result['receiver_vkn'] = _txt(c, 'cac:PartyTaxScheme/cbc:CompanyID') if c is not None else ''

        # ── Toplamlar ────────────────────────────────────────────────────
        result['amount_untaxed'] = _flt(root, 'cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount')
        result['amount_total']   = _flt(root, 'cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount')
        result['amount_tax']     = _flt(root, 'cac:TaxTotal/cbc:TaxAmount')

        # ── Notlar ───────────────────────────────────────────────────────
        result['notes'] = [
            n.text.strip() for n in root.findall('cbc:Note', NS)
            if n.text and n.text.strip()
        ]

        # ── Kalemler ─────────────────────────────────────────────────────
        result['lines'] = [
            self._parse_line(line) for line in root.findall('cac:InvoiceLine', NS)
        ]

        _logger.info(
            'UBL parse: UUID=%s %d kalem toplam=%s %s',
            result['uuid'], len(result['lines']),
            result['amount_total'], result['currency'],
        )
        return result

    def _parse_line(self, el):
        qty_el = el.find('cbc:InvoicedQuantity', NS)
        uom_code = qty_el.get('unitCode', 'C62') if qty_el is not None else 'C62'
        return {
            'line_id':     _txt(el, 'cbc:ID'),
            'description': _txt(el, 'cac:Item/cbc:Description') or _txt(el, 'cac:Item/cbc:Name'),
            'ubl_code':    _txt(el, 'cac:Item/cac:SellersItemIdentification/cbc:ID'),
            'quantity':    _flt(el, 'cbc:InvoicedQuantity', 1.0),
            'uom_code':    uom_code,
            'unit_price':  _flt(el, 'cac:Price/cbc:PriceAmount'),
            'line_total':  _flt(el, 'cbc:LineExtensionAmount'),
            'tax_percent': _flt(el, 'cac:TaxTotal/cac:TaxSubtotal/cbc:Percent'),
            'tax_amount':  _flt(el, 'cac:TaxTotal/cbc:TaxAmount'),
        }
