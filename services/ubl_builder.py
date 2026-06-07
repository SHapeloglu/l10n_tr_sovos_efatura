# -*- coding: utf-8 -*-
"""
UBL-TR 2.1 fatura XML üreticisi.
GİB e-Fatura Paketi: https://ebelge.gib.gov.tr/dosyalar/kilavuzlar/e-FaturaPaket.zip
"""
import logging
from datetime import datetime
from lxml import etree

_logger = logging.getLogger(__name__)

# ── Namespace Tanımları ────────────────────────────────────────────────
NS = {
    'ubl': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
    'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
}

UBL_VERSION = '2.1'
CUSTOMIZATION_ID = 'TR1.2'
PROFILE_ID_MAP = {
    'TICARIFATURA': 'TICARIFATURA',
    'TEMELFATURA': 'TEMELFATURA',
    'EARSIVFATURA': 'EARSIVFATURA',
}

# Varsayılan UBL birim kodu
DEFAULT_UBL_UNIT = 'C62'  # Adet


def _tag(ns_prefix, local):
    return '{%s}%s' % (NS[ns_prefix], local)


def _sub(parent, ns_prefix, local, text=None, **attribs):
    el = etree.SubElement(parent, _tag(ns_prefix, local), **attribs)
    if text is not None:
        el.text = str(text)
    return el


class UblBuilder:
    def __init__(self, company):
        self.company = company

    def build(self, invoice, uuid, invoice_number, scenario):
        """
        UBL-TR 2.1 Invoice XML üretir.
        Returns: bytes (UTF-8 encoded XML)
        """
        root = etree.Element(_tag('ubl', 'Invoice'), nsmap=NS)

        # ── UBL Extensions (imza placeholder) ────────────────────────
        ext_content = _sub(root, 'ext', 'UBLExtensions')
        _sub(ext_content, 'ext', 'UBLExtension')  # Sovos doldurur

        # ── Temel Alanlar ─────────────────────────────────────────────
        _sub(root, 'cbc', 'UBLVersionID', UBL_VERSION)
        _sub(root, 'cbc', 'CustomizationID', CUSTOMIZATION_ID)
        _sub(root, 'cbc', 'ProfileID', PROFILE_ID_MAP.get(scenario, 'TICARIFATURA'))
        _sub(root, 'cbc', 'ID', invoice_number)
        _sub(root, 'cbc', 'CopyIndicator', 'false')
        _sub(root, 'cbc', 'UUID', uuid)
        _sub(root, 'cbc', 'IssueDate', str(invoice.invoice_date))
        _sub(root, 'cbc', 'IssueTime',
             (invoice.invoice_date_time or datetime.now()).strftime('%H:%M:%S') if hasattr(invoice, 'invoice_date_time') else '00:00:00')
        _sub(root, 'cbc', 'InvoiceTypeCode', 'SATIS')
        _sub(root, 'cbc', 'DocumentCurrencyCode', invoice.currency_id.name or 'TRY')
        _sub(root, 'cbc', 'LineCountNumeric', str(len(invoice.invoice_line_ids)))

        # ── Gönderici ─────────────────────────────────────────────────
        self._build_supplier(root, invoice)

        # ── Alıcı ─────────────────────────────────────────────────────
        self._build_customer(root, invoice)

        # ── Para Toplamları ───────────────────────────────────────────
        self._build_monetary_total(root, invoice)

        # ── Vergi Toplamları ─────────────────────────────────────────
        self._build_tax_totals(root, invoice)

        # ── Fatura Kalemleri ─────────────────────────────────────────
        for idx, line in enumerate(invoice.invoice_line_ids.filtered(lambda l: l.display_type == 'product'), start=1):
            self._build_invoice_line(root, line, idx)

        xml_bytes = etree.tostring(root, xml_declaration=True, encoding='UTF-8', pretty_print=True)
        return xml_bytes

    def _build_supplier(self, root, invoice):
        company = self.company
        supplier = _sub(root, 'cac', 'AccountingSupplierParty')
        party = _sub(supplier, 'cac', 'Party')

        gb_node = _sub(party, 'cbc', 'WebsiteURI')  # placeholder

        # İsim
        party_name = _sub(party, 'cac', 'PartyName')
        _sub(party_name, 'cbc', 'Name', company.name)

        # Adres
        addr = _sub(party, 'cac', 'PostalAddress')
        _sub(addr, 'cbc', 'StreetName', company.street or '')
        _sub(addr, 'cbc', 'CityName', company.city or '')
        country = _sub(addr, 'cac', 'Country')
        _sub(country, 'cbc', 'IdentificationCode', company.country_id.code or 'TR')

        # Vergi bilgisi
        tax_scheme = _sub(party, 'cac', 'PartyTaxScheme')
        tax_id = _sub(tax_scheme, 'cac', 'TaxScheme')
        _sub(tax_id, 'cbc', 'Name', company.x_sovos_sender_vkn or '')
        scheme_node = _sub(tax_scheme, 'cbc', 'CompanyID', company.vat or company.x_sovos_sender_vkn or '')

        # İletişim
        contact = _sub(party, 'cac', 'Contact')
        _sub(contact, 'cbc', 'Telephone', company.phone or '')
        _sub(contact, 'cbc', 'ElectronicMail', company.email or '')

    def _build_customer(self, root, invoice):
        partner = invoice.partner_id
        customer = _sub(root, 'cac', 'AccountingCustomerParty')
        party = _sub(customer, 'cac', 'Party')

        party_name = _sub(party, 'cac', 'PartyName')
        _sub(party_name, 'cbc', 'Name', partner.name or '')

        addr = _sub(party, 'cac', 'PostalAddress')
        _sub(addr, 'cbc', 'StreetName', partner.street or '')
        _sub(addr, 'cbc', 'CityName', partner.city or '')
        country = _sub(addr, 'cac', 'Country')
        _sub(country, 'cbc', 'IdentificationCode',
             partner.country_id.code if partner.country_id else 'TR')

        tax_scheme = _sub(party, 'cac', 'PartyTaxScheme')
        _sub(tax_scheme, 'cbc', 'CompanyID', partner.vat or '')
        tax_node = _sub(tax_scheme, 'cac', 'TaxScheme')
        _sub(tax_node, 'cbc', 'Name', partner.x_vergi_dairesi or '')

    def _build_monetary_total(self, root, invoice):
        total = _sub(root, 'cac', 'LegalMonetaryTotal')
        currency = invoice.currency_id.name or 'TRY'
        _sub(total, 'cbc', 'LineExtensionAmount', '%.2f' % invoice.amount_untaxed,
             currencyID=currency)
        _sub(total, 'cbc', 'TaxExclusiveAmount', '%.2f' % invoice.amount_untaxed,
             currencyID=currency)
        _sub(total, 'cbc', 'TaxInclusiveAmount', '%.2f' % invoice.amount_total,
             currencyID=currency)
        _sub(total, 'cbc', 'PayableAmount', '%.2f' % invoice.amount_residual,
             currencyID=currency)

    def _build_tax_totals(self, root, invoice):
        currency = invoice.currency_id.name or 'TRY'
        # Vergi gruplarını topla
        tax_groups = {}
        for line in invoice.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
            for tax in line.tax_ids:
                key = tax.name
                if key not in tax_groups:
                    tax_groups[key] = {
                        'base': 0.0, 'amount': 0.0,
                        'percent': tax.amount, 'name': tax.name
                    }
                base = line.price_subtotal
                tax_amount = base * (tax.amount / 100.0)
                tax_groups[key]['base'] += base
                tax_groups[key]['amount'] += tax_amount

        tax_total = _sub(root, 'cac', 'TaxTotal')
        total_tax = sum(g['amount'] for g in tax_groups.values())
        _sub(tax_total, 'cbc', 'TaxAmount', '%.2f' % total_tax, currencyID=currency)

        for group in tax_groups.values():
            subtotal = _sub(tax_total, 'cac', 'TaxSubtotal')
            _sub(subtotal, 'cbc', 'TaxableAmount', '%.2f' % group['base'], currencyID=currency)
            _sub(subtotal, 'cbc', 'TaxAmount', '%.2f' % group['amount'], currencyID=currency)
            _sub(subtotal, 'cbc', 'Percent', '%.2f' % group['percent'])
            tax_cat = _sub(subtotal, 'cac', 'TaxCategory')
            scheme = _sub(tax_cat, 'cac', 'TaxScheme')
            _sub(scheme, 'cbc', 'Name', group['name'])

    def _build_invoice_line(self, root, line, idx):
        currency = line.move_id.currency_id.name or 'TRY'
        inv_line = _sub(root, 'cac', 'InvoiceLine')
        _sub(inv_line, 'cbc', 'ID', str(idx))
        ubl_unit = (line.product_uom_id.x_ubl_code if line.product_uom_id else None) or DEFAULT_UBL_UNIT
        _sub(inv_line, 'cbc', 'InvoicedQuantity', '%.6f' % line.quantity, unitCode=ubl_unit)
        _sub(inv_line, 'cbc', 'LineExtensionAmount', '%.2f' % line.price_subtotal, currencyID=currency)

        # Vergi
        tax_total = _sub(inv_line, 'cac', 'TaxTotal')
        line_tax = sum(
            line.price_subtotal * (t.amount / 100.0) for t in line.tax_ids
        )
        _sub(tax_total, 'cbc', 'TaxAmount', '%.2f' % line_tax, currencyID=currency)

        # Kalem açıklaması
        item = _sub(inv_line, 'cac', 'Item')
        _sub(item, 'cbc', 'Description', line.name or '')
        _sub(item, 'cbc', 'Name', line.product_id.name if line.product_id else line.name or '')

        # Fiyat
        price = _sub(inv_line, 'cac', 'Price')
        _sub(price, 'cbc', 'PriceAmount', '%.6f' % line.price_unit, currencyID=currency)
