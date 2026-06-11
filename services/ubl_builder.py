# -*- coding: utf-8 -*-
"""
ubl_builder.py — UBL-TR 2.1 Fatura XML Üreticisi
==================================================
GİB'in zorunlu kıldığı UBL-TR 2.1 formatında fatura XML'i üretir.

Ne olduğu:
    UBL (Universal Business Language) ISO/IEC standardı bir XML formatıdır.
    GİB, Türkiye'ye özgü kurallarla TR1.2 profilini zorunlu kılmaktadır.

Referans:
    https://ebelge.gib.gov.tr/dosyalar/kilavuzlar/e-FaturaPaket.zip

Mimari kararlar:
    - lxml: C tabanlı hızlı XML kütüphanesi; etree API kullanılır
    - Namespace'ler dict ile yönetilir (NS sabiti)
    - _sub() yardımcısı: etree.SubElement çağrılarını kısaltır
    - Her bölüm ayrı metod (_build_supplier, _build_customer vb.)
"""
import logging
from datetime import datetime
from lxml import etree

_logger = logging.getLogger(__name__)

# ── XML Namespace Tanımları ────────────────────────────────────────────────
# Namespace: XML'de çakışan element isimlerini önlemek için URI tabanlı ön ek.
# Örnek: <cbc:ID> ile <cac:ID> farklı elemanlardır.
NS = {
    'ubl': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',       # Kök eleman
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',  # Bileşik elemanlar
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',      # Temel elemanlar
    'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2', # Uzantılar (imza)
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',                     # Şema referansı
}

# GİB'in zorunlu kıldığı sabit değerler
UBL_VERSION = '2.1'           # UBL versiyonu — değiştirilmez
CUSTOMIZATION_ID = 'TR1.2'    # GİB Türkiye profili — değiştirilmez

# Senaryo → ProfileID eşlemesi
# TICARIFATURA: B2B alıcısı; alıcı kabul/red yanıtı verir
# TEMELFATURA: B2B alıcısı; yanıt beklenmez
# EARSIVFATURA: GİB'e kayıtsız alıcı
PROFILE_ID_MAP = {
    'TICARIFATURA': 'TICARIFATURA',
    'TEMELFATURA': 'TEMELFATURA',
    'EARSIVFATURA': 'EARSIVFATURA',
}

# Birim kodu verilmemişse kullanılacak varsayılan (UN/CEFACT C62 = Adet)
DEFAULT_UBL_UNIT = 'C62'


# ── Yardımcı Fonksiyonlar ──────────────────────────────────────────────────

def _tag(ns_prefix, local):
    """
    Clark notation'da tam XML tag adı üretir.
    Örnek: _tag('cbc', 'ID') → '{urn:...:CommonBasicComponents-2}ID'
    lxml bu formatı kullanır; '{namespace}local' şeklinde.
    """
    return '{%s}%s' % (NS[ns_prefix], local)


def _sub(parent, ns_prefix, local, text=None, **attribs):
    """
    Parent elementin altına yeni bir child eleman ekler.

    Parametreler:
        parent     : Üst eleman (etree.Element)
        ns_prefix  : Namespace kısaltması ('cbc', 'cac', 'ext', vb.)
        local      : Yerel eleman adı ('ID', 'Name', 'Amount', vb.)
        text       : Eleman içeriği (opsiyonel). Verilirse str'e çevrilir.
        **attribs  : XML attribute'ları. Örnek: currencyID='TRY'

    Dönüş: Oluşturulan child eleman (daha fazla alt eleman eklemek için)

    Örnek kullanım:
        amount_el = _sub(total, 'cbc', 'PayableAmount', '1000.00', currencyID='TRY')
        # → <cbc:PayableAmount currencyID="TRY">1000.00</cbc:PayableAmount>
    """
    el = etree.SubElement(parent, _tag(ns_prefix, local), **attribs)
    if text is not None:
        el.text = str(text)
    return el


class UblBuilder:
    """
    Tek fatura için UBL-TR 2.1 XML üretir.

    Kullanım:
        xml_bytes = UblBuilder(company).build(invoice, uuid, number, scenario)
    """

    def __init__(self, company):
        """
        Parametreler:
            company (res.company): Gönderici şirket; adres, VKN, telefon için kullanılır.
        """
        self.company = company

    def build(self, invoice, uuid, invoice_number, scenario):
        """
        Ana üretim metodu — tam UBL-TR fatura XML'ini oluşturur.

        Parametreler:
            invoice        : account.move kaydı (Odoo faturası)
            uuid           : Fatura UUID'si (str, UUID v4 formatında)
            invoice_number : GİB fatura numarası (ör: ABC2024000000001)
            scenario       : 'TICARIFATURA', 'TEMELFATURA' veya 'EARSIVFATURA'

        Dönüş:
            bytes — UTF-8 kodlanmış XML içeriği

        XML Yapısı (özet):
            <Invoice>
              <ext:UBLExtensions>     ← İmza placeholder (Sovos doldurur)
              <cbc:UBLVersionID>      ← 2.1
              <cbc:ProfileID>         ← Senaryo
              <cbc:ID>                ← Fatura numarası
              <cbc:UUID>              ← Benzersiz tanımlayıcı
              <cac:AccountingSupplierParty>  ← Gönderici
              <cac:AccountingCustomerParty>  ← Alıcı
              <cac:LegalMonetaryTotal>       ← Para toplamları
              <cac:TaxTotal>                 ← Vergi toplamları
              <cac:InvoiceLine>              ← Kalemler (her satır için)
        """
        # XML kök elemanı oluştur; nsmap: tüm namespace'leri tanımlar
        root = etree.Element(_tag('ubl', 'Invoice'), nsmap=NS)

        # ── UBL Extensions (dijital imza için yer tutucu) ──────────────────
        # Sovos bu bloğu imza ile doldurur; biz sadece boş placeholder koyuyoruz
        ext_content = _sub(root, 'ext', 'UBLExtensions')
        _sub(ext_content, 'ext', 'UBLExtension')

        # ── Temel Fatura Bilgileri ─────────────────────────────────────────
        _sub(root, 'cbc', 'UBLVersionID', UBL_VERSION)      # Zorunlu: '2.1'
        _sub(root, 'cbc', 'CustomizationID', CUSTOMIZATION_ID)  # Zorunlu: 'TR1.2'
        _sub(root, 'cbc', 'ProfileID', PROFILE_ID_MAP.get(scenario, 'TICARIFATURA'))
        _sub(root, 'cbc', 'ID', invoice_number)              # GİB fatura numarası
        _sub(root, 'cbc', 'CopyIndicator', 'false')          # Asıl nüsha (kopya değil)
        _sub(root, 'cbc', 'UUID', uuid)                      # Benzersiz tanımlayıcı
        _sub(root, 'cbc', 'IssueDate', str(invoice.invoice_date))  # YYYY-MM-DD formatı

        # Saat bilgisi: fatura modelinde alan varsa kullan, yoksa 00:00:00
        _sub(root, 'cbc', 'IssueTime',
             (invoice.invoice_date_time or datetime.now()).strftime('%H:%M:%S')
             if hasattr(invoice, 'invoice_date_time') else '00:00:00')

        _sub(root, 'cbc', 'InvoiceTypeCode', 'SATIS')        # Satış faturası
        _sub(root, 'cbc', 'DocumentCurrencyCode', invoice.currency_id.name or 'TRY')
        _sub(root, 'cbc', 'LineCountNumeric', str(len(invoice.invoice_line_ids)))

        # ── Taraf Bilgileri ────────────────────────────────────────────────
        self._build_supplier(root, invoice)   # Gönderici (şirketimiz)
        self._build_customer(root, invoice)   # Alıcı (müşteri)

        # ── Finansal Toplamlar ─────────────────────────────────────────────
        self._build_monetary_total(root, invoice)  # KDV dahil/hariç tutarlar
        self._build_tax_totals(root, invoice)      # Vergi kırılımları

        # ── Fatura Kalemleri ───────────────────────────────────────────────
        # Sadece ürün/hizmet satırları alınır (başlık, not gibi display_type satırlar hariç)
        for idx, line in enumerate(
            invoice.invoice_line_ids.filtered(lambda l: l.display_type == 'product'),
            start=1  # Kalem numarası 1'den başlar
        ):
            self._build_invoice_line(root, line, idx)

        # XML'i UTF-8 bytes olarak döndür
        xml_bytes = etree.tostring(root, xml_declaration=True, encoding='UTF-8', pretty_print=True)
        return xml_bytes

    def _build_supplier(self, root, invoice):
        """
        AccountingSupplierParty bloğunu oluşturur.
        Gönderici = şirketimiz (self.company).
        GİB'in gerektirdiği: isim, adres, VKN, iletişim bilgileri.
        """
        company = self.company
        supplier = _sub(root, 'cac', 'AccountingSupplierParty')
        party = _sub(supplier, 'cac', 'Party')

        # WebsiteURI: placeholder — Sovos posta kutusu bilgisini buraya koyabilir
        _sub(party, 'cbc', 'WebsiteURI')

        # Şirket ticari unvanı
        party_name = _sub(party, 'cac', 'PartyName')
        _sub(party_name, 'cbc', 'Name', company.name)

        # Şirket adresi
        addr = _sub(party, 'cac', 'PostalAddress')
        _sub(addr, 'cbc', 'StreetName', company.street or '')
        _sub(addr, 'cbc', 'CityName', company.city or '')
        country = _sub(addr, 'cac', 'Country')
        _sub(country, 'cbc', 'IdentificationCode', company.country_id.code or 'TR')

        # Vergi kimlik bilgileri
        tax_scheme = _sub(party, 'cac', 'PartyTaxScheme')
        tax_id = _sub(tax_scheme, 'cac', 'TaxScheme')
        _sub(tax_id, 'cbc', 'Name', company.x_sovos_sender_vkn or '')
        # CompanyID: Resmi VKN; yoksa Sovos VKN kullanılır
        _sub(tax_scheme, 'cbc', 'CompanyID', company.vat or company.x_sovos_sender_vkn or '')

        # İletişim bilgileri
        contact = _sub(party, 'cac', 'Contact')
        _sub(contact, 'cbc', 'Telephone', company.phone or '')
        _sub(contact, 'cbc', 'ElectronicMail', company.email or '')

    def _build_customer(self, root, invoice):
        """
        AccountingCustomerParty bloğunu oluşturur.
        Alıcı = invoice.partner_id (müşteri).
        """
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

        # Alıcı vergi bilgileri: VKN + vergi dairesi
        tax_scheme = _sub(party, 'cac', 'PartyTaxScheme')
        _sub(tax_scheme, 'cbc', 'CompanyID', partner.vat or '')
        tax_node = _sub(tax_scheme, 'cac', 'TaxScheme')
        _sub(tax_node, 'cbc', 'Name', partner.x_vergi_dairesi or '')

    def _build_monetary_total(self, root, invoice):
        """
        LegalMonetaryTotal bloğunu oluşturur — para toplamları.

        Alan açıklamaları:
          LineExtensionAmount  : KDV hariç ara toplam (satır tutarları toplamı)
          TaxExclusiveAmount   : Vergi hariç toplam (LineExtensionAmount ile genellikle aynı)
          TaxInclusiveAmount   : KDV dahil toplam (müşterinin ödeyeceği tutar)
          PayableAmount        : Ödenecek tutar (kalan borç; tüm indirimler düşüldükten sonra)

        currencyID attribute: GİB her tutara para birimi attribute'u zorunlu kılar.
        """
        total = _sub(root, 'cac', 'LegalMonetaryTotal')
        currency = invoice.currency_id.name or 'TRY'

        # '%.2f' : 2 ondalık basamak formatı (GİB zorunluluğu)
        _sub(total, 'cbc', 'LineExtensionAmount', '%.2f' % invoice.amount_untaxed, currencyID=currency)
        _sub(total, 'cbc', 'TaxExclusiveAmount',  '%.2f' % invoice.amount_untaxed, currencyID=currency)
        _sub(total, 'cbc', 'TaxInclusiveAmount',  '%.2f' % invoice.amount_total,   currencyID=currency)
        _sub(total, 'cbc', 'PayableAmount',       '%.2f' % invoice.amount_residual, currencyID=currency)

    def _build_tax_totals(self, root, invoice):
        """
        TaxTotal bloğunu oluşturur — vergi kırılımları.

        Yapı:
          <TaxTotal>
            <TaxAmount>          ← Tüm vergilerin toplamı
            <TaxSubtotal>        ← Her vergi türü için ayrı blok
              <TaxableAmount>    ← Vergi matrahı
              <TaxAmount>        ← Bu vergi türünün tutarı
              <Percent>          ← Oran (ör: 18.00)
              <TaxCategory>
                <TaxScheme>
                  <Name>         ← Vergi adı (ör: KDV)

        Gruplama mantığı:
            Aynı vergi adlı satırlar birleştirilir.
            Örnek: Hem kalem 1 hem kalem 2'de %18 KDV varsa tek bir TaxSubtotal olur.
        """
        currency = invoice.currency_id.name or 'TRY'

        # Vergi gruplarını topla: {vergi_adı: {base, amount, percent, name}}
        tax_groups = {}
        for line in invoice.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
            for tax in line.tax_ids:
                key = tax.name
                if key not in tax_groups:
                    tax_groups[key] = {
                        'base': 0.0,
                        'amount': 0.0,
                        'percent': tax.amount,  # ör: 18.0
                        'name': tax.name
                    }
                base = line.price_subtotal
                tax_amount = base * (tax.amount / 100.0)
                tax_groups[key]['base'] += base
                tax_groups[key]['amount'] += tax_amount

        # TaxTotal ana elemanı
        tax_total = _sub(root, 'cac', 'TaxTotal')
        total_tax = sum(g['amount'] for g in tax_groups.values())
        _sub(tax_total, 'cbc', 'TaxAmount', '%.2f' % total_tax, currencyID=currency)

        # Her vergi türü için TaxSubtotal
        for group in tax_groups.values():
            subtotal = _sub(tax_total, 'cac', 'TaxSubtotal')
            _sub(subtotal, 'cbc', 'TaxableAmount', '%.2f' % group['base'],   currencyID=currency)
            _sub(subtotal, 'cbc', 'TaxAmount',     '%.2f' % group['amount'], currencyID=currency)
            _sub(subtotal, 'cbc', 'Percent',       '%.2f' % group['percent'])
            tax_cat = _sub(subtotal, 'cac', 'TaxCategory')
            scheme = _sub(tax_cat, 'cac', 'TaxScheme')
            _sub(scheme, 'cbc', 'Name', group['name'])

    def _build_invoice_line(self, root, line, idx):
        """
        Tek bir fatura kalemi için InvoiceLine bloğu oluşturur.

        Parametreler:
            root : XML kök elemanı (InvoiceLine buraya eklenir)
            line : account.move.line kaydı
            idx  : Kalem sıra numarası (1'den başlar)

        UBL InvoiceLine yapısı:
          <InvoiceLine>
            <ID>                  ← Sıra numarası
            <InvoicedQuantity>    ← Miktar + birim kodu
            <LineExtensionAmount> ← Satır tutarı (KDV hariç)
            <TaxTotal>            ← Bu satıra ait vergi
            <Item>                ← Ürün/hizmet açıklaması
            <Price>               ← Birim fiyatı
        """
        currency = line.move_id.currency_id.name or 'TRY'
        inv_line = _sub(root, 'cac', 'InvoiceLine')

        _sub(inv_line, 'cbc', 'ID', str(idx))  # Satır sırası

        # Birim kodu: önce product_uom'dan al, yoksa varsayılan C62 (Adet) kullan
        ubl_unit = (line.product_uom_id.x_ubl_code if line.product_uom_id else None) or DEFAULT_UBL_UNIT
        # unitCode attribute: GİB UN/CEFACT birim kodu zorunlu kılar
        _sub(inv_line, 'cbc', 'InvoicedQuantity', '%.6f' % line.quantity, unitCode=ubl_unit)
        _sub(inv_line, 'cbc', 'LineExtensionAmount', '%.2f' % line.price_subtotal, currencyID=currency)

        # Satır vergi toplamı
        tax_total = _sub(inv_line, 'cac', 'TaxTotal')
        line_tax = sum(
            line.price_subtotal * (t.amount / 100.0)
            for t in line.tax_ids
        )
        _sub(tax_total, 'cbc', 'TaxAmount', '%.2f' % line_tax, currencyID=currency)

        # Ürün/hizmet açıklaması
        item = _sub(inv_line, 'cac', 'Item')
        _sub(item, 'cbc', 'Description', line.name or '')   # Uzun açıklama
        _sub(item, 'cbc', 'Name',
             line.product_id.name if line.product_id else line.name or '')  # Kısa ad

        # Birim fiyat (6 ondalık: küçük tutarlar için yeterli hassasiyet)
        price = _sub(inv_line, 'cac', 'Price')
        _sub(price, 'cbc', 'PriceAmount', '%.6f' % line.price_unit, currencyID=currency)
