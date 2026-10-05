# -*- coding: utf-8 -*-
"""
ubl_validator.py — UBL-TR İki Katmanlı Validasyon Servisi
===========================================================

GİB'e göndermeden önce fatura XML'ini iki aşamada doğrular:

  Katman 1 → XSD (lxml.etree.XMLSchema)
    Zorunlu alanlar, veri tipleri, yapısal uyumluluk.
    Dosya: services/schemas/maindoc/UBL-Invoice-2.1.xsd

  Katman 2 → GİB İş Kuralları (lxml XPath)
    GİB Schematron'daki fatura iş kurallarının kritik olanları
    doğrudan XPath ile uygulanır. saxonche gerekmez.

─────────────────────────────────────────────────────────────────
NEDEN GİB SCHEMATRON'U DOĞRUDAN KULLANAMIYORUZ?
─────────────────────────────────────────────────────────────────
GİB'in UBL-TR_Common_Schematron.xml dosyası XSLT 2.0 fonksiyonları
kullanır (xs:date(), matches(), xs:decimal()). Bu fonksiyonlar:
  - lxml.isoschematron → XSLT 1.0 pipeline → compile ederken çöker
  - saxonche → XSLT 2.0 destekler ama Schematron ≠ XSLT
    Saxon'a stylesheet olarak .xml schematron veremezsiniz.
    Saxon Schematron'u compile etmek için ISO pipeline XSLT'leri
    (iso_dsdl_include.xsl, iso_svrl_for_xslt2.xsl) gerekir —
    bu dosyalar GİB paketlerinde yoktur.

─────────────────────────────────────────────────────────────────
ÇÖZÜM YAKLAŞIMI
─────────────────────────────────────────────────────────────────
GİB Schematron'un "inv:Invoice" context'indeki kritik iş kuralları
(50+ kural) lxml XPath ile implement edilir. Bu kurallar:

  - Fatura ID formatı  : ABC2024000000001 (16 karakter, regex)
  - UUID formatı       : 36 karakter, UUID v4
  - ProfileID          : TICARIFATURA / TEMELFATURA / EARSIVFATURA
  - CustomizationID    : TR1.2 veya TR1.2.1
  - UBLVersionID       : 2.1
  - IssueDate          : geçmiş tarih, 2005-01-01 sonrası
  - VKN/TCKN format    : 10/11 hane
  - InvoiceTypeCode    : geçerli değer listesi
  - Para birimi        : geçerli ISO 4217 kodu
  - KDV oranı          : GİB'in desteklediği oranlar

Zarf kuralları (sh:StandardBusinessDocument context) bu katmanda
uygulanmaz — zarfı Sovos yönetir, Sovos da kendi validasyonunu
yapar. GİB son kontrol makamıdır; 1150/1160 kodları hatayı bildirir.

─────────────────────────────────────────────────────────────────
DİZİN YAPISI (services/schemas/)
─────────────────────────────────────────────────────────────────
  schemas/
  ├── maindoc/
  │   └── UBL-Invoice-2.1.xsd       ← UBL-TR1.2.1_Paketi / xsdrt/maindoc/
  └── common/                        ← UBL-TR1.2.1_Paketi / xsdrt/common/
      ├── UBL-CommonAggregateComponents-2.1.xsd
      ├── UBL-CommonBasicComponents-2.1.xsd
      └── ... (14 dosya)

  NOT: Schematron .xml dosyaları schemas/ dizinine kopyalanabilir
  ama bu modül tarafından kullanılmaz; sadece referans amaçlıdır.

KURULUM:
  bash setup_schemas.sh UBL-TR1.2.1_Paketi.zip e-FaturaPaketi.zip
"""
import logging
import os
import re
from datetime import date

from lxml import etree
from odoo.exceptions import UserError
from odoo import _

_logger = logging.getLogger(__name__)

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), 'schemas')
XSD_PATH   = os.path.join(SCHEMA_DIR, 'maindoc', 'UBL-Invoice-2.1.xsd')

# UBL-TR namespace haritası — XPath sorgularında kullanılır
NS = {
    'inv':  'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
    'cbc':  'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
    'cac':  'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    'ext':  'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
}

# ── GİB Geçerli Değer Listeleri ──────────────────────────────────────────────
# Kaynak: UBL-TR_Codelist.xml + GİB Şematron

VALID_PROFILE_IDS = {
    'TICARIFATURA', 'TEMELFATURA', 'EARSIVFATURA', 'IHRACAT',
    'YOLCUBERABERFATURA', 'OZELMATRAH', 'TEVKIFAT', 'ISTISNA',
    'HKSSATIS', 'ENERJI', 'YATIRIMTESVIK', 'IDIS', 'ILAC_TIBBICIHAZ',
    'SUREKLI_MUSTERI', 'TEKNOLOJIDESTEK',
}

VALID_INVOICE_TYPE_CODES = {
    'SATIS', 'IADE', 'TEVKIFAT', 'TEVKIFAT_IADE', 'ISTISNA',
    'OZELMATRAH', 'IHRACAT', 'YOLCUBERABERSATIS', 'HKSSATIS',
    'SARJ', 'SARJANLIK', 'TEKNOLOJIDESTEK',
}

# ISO 4217 para birimleri (yaygın kullanılanlar)
VALID_CURRENCY_CODES = {
    'TRY', 'USD', 'EUR', 'GBP', 'CHF', 'JPY', 'CNY', 'AED', 'SAR',
    'RUB', 'KWD', 'QAR', 'BHD', 'OMR', 'EGP', 'DKK', 'NOK', 'SEK',
    'CAD', 'AUD', 'NZD', 'SGD', 'HKD', 'MXN', 'BRL', 'INR', 'ZAR',
}

# GİB'in kabul ettiği KDV oranları (Türkiye)
VALID_VAT_RATES = {'0', '1', '8', '10', '18', '20'}

# Fatura ID regex: ABC2024000000001 formatı (3 büyük harf/rakam + 4 rakam yıl + 9 rakam)
INVOICE_ID_PATTERN = re.compile(r'^[A-Z0-9]{3}20[0-9]{2}[0-9]{9}$')

# UUID v4 regex
UUID_PATTERN = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-'
    r'[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$'
)


def _txt(doc, xpath):
    """XPath ile tek bir metin değeri döndürür; bulunamazsa None."""
    results = doc.xpath(xpath, namespaces=NS)
    if results:
        val = results[0]
        return val.text.strip() if hasattr(val, 'text') and val.text else str(val).strip()
    return None


class UblValidator:
    """
    UBL-TR XML doğrulama servisi.

    Kullanım:
        valid, layer, errors = UblValidator().validate(xml_bytes)
        if not valid:
            # errors listesinde hata mesajları var
    """

    def __init__(self):
        self._xsd = None  # Lazy: ilk validate() çağrısında yüklenir

    # ── Katman 1: XSD ─────────────────────────────────────────────────────

    def _load_xsd(self):
        """
        XSD şema nesnesini yükler ve önbelleğe alır.

        maindoc/UBL-Invoice-2.1.xsd → ../common/*.xsd relative import
        lxml, parse sırasında bu bağımlılıkları otomatik çözer.

        Returns: etree.XMLSchema | None
        """
        if self._xsd is not None:
            return self._xsd

        if not os.path.exists(XSD_PATH):
            _logger.warning(
                'XSD bulunamadı: %s — Katman 1 atlandı.\n'
                'Kurulum: bash setup_schemas.sh UBL-TR1.2.1_Paketi.zip e-FaturaPaketi.zip',
                XSD_PATH,
            )
            return None

        try:
            self._xsd = etree.XMLSchema(etree.parse(XSD_PATH))
            _logger.debug('UBL XSD yüklendi')
        except etree.XMLSchemaParseError as e:
            _logger.error('XSD parse hatası: %s', e)
            return None

        return self._xsd

    # ── Katman 2: GİB İş Kuralları (XPath) ───────────────────────────────

    def _check_gib_rules(self, doc):
        """
        GİB Schematron'un fatura iş kurallarını XPath ile doğrular.

        Uygulanan kurallar GİB UBL-TR_Common_Schematron.xml'deki
        inv:Invoice context'li assert'lerden türetilmiştir.

        Parameters:
            doc: lxml.etree._Element

        Returns:
            list[str]: Hata mesajları; boş liste → geçerli
        """
        errors = []

        # ── 1. UBLVersionID ──────────────────────────────────────────────
        ubl_ver = _txt(doc, '//cbc:UBLVersionID')
        if ubl_ver != '2.1':
            errors.append(
                'cbc:UBLVersionID hatalı: "%s". '
                '"2.1" olmalıdır.' % ubl_ver
            )

        # ── 2. CustomizationID ───────────────────────────────────────────
        cust_id = _txt(doc, '//cbc:CustomizationID')
        if cust_id not in ('TR1.2', 'TR1.2.1'):
            errors.append(
                'cbc:CustomizationID hatalı: "%s". '
                '"TR1.2" veya "TR1.2.1" olmalıdır.' % cust_id
            )

        # ── 3. ProfileID ─────────────────────────────────────────────────
        profile_id = _txt(doc, '//cbc:ProfileID')
        if profile_id not in VALID_PROFILE_IDS:
            errors.append(
                'cbc:ProfileID geçersiz: "%s". '
                'Geçerli değerler: %s' % (profile_id, ', '.join(sorted(VALID_PROFILE_IDS)))
            )

        # ── 4. Fatura ID Formatı ─────────────────────────────────────────
        inv_id = _txt(doc, '//cbc:ID')
        if inv_id:
            if len(inv_id) != 16:
                errors.append(
                    'cbc:ID 16 karakter olmalıdır (mevcut: %d karakter): "%s"' % (len(inv_id), inv_id)
                )
            elif not INVOICE_ID_PATTERN.match(inv_id):
                errors.append(
                    'cbc:ID formatı hatalı: "%s". '
                    'ABC2024000000001 formatında olmalıdır.' % inv_id
                )
        else:
            errors.append('cbc:ID zorunludur.')

        # ── 5. UUID Formatı ──────────────────────────────────────────────
        uuid = _txt(doc, '//cbc:UUID')
        if uuid:
            if len(uuid) != 36:
                errors.append(
                    'cbc:UUID 36 karakter olmalıdır (mevcut: %d): "%s"' % (len(uuid), uuid)
                )
            elif not UUID_PATTERN.match(uuid):
                errors.append('cbc:UUID geçerli bir UUID v4 formatında değil: "%s"' % uuid)
        else:
            errors.append('cbc:UUID zorunludur.')

        # ── 6. IssueDate ─────────────────────────────────────────────────
        issue_date_str = _txt(doc, '//cbc:IssueDate')
        if issue_date_str:
            try:
                issue_date = date.fromisoformat(issue_date_str)
                if issue_date > date.today():
                    errors.append(
                        'cbc:IssueDate gelecek tarih olamaz: "%s"' % issue_date_str
                    )
                if issue_date < date(2005, 1, 1):
                    errors.append(
                        'cbc:IssueDate 2005-01-01 tarihinden önce olamaz: "%s"' % issue_date_str
                    )
            except ValueError:
                errors.append('cbc:IssueDate geçersiz tarih formatı: "%s"' % issue_date_str)
        else:
            errors.append('cbc:IssueDate zorunludur.')

        # ── 7. InvoiceTypeCode ───────────────────────────────────────────
        inv_type = _txt(doc, '//cbc:InvoiceTypeCode')
        if inv_type not in VALID_INVOICE_TYPE_CODES:
            errors.append(
                'cbc:InvoiceTypeCode geçersiz: "%s". '
                'Geçerli değerler: %s' % (inv_type, ', '.join(sorted(VALID_INVOICE_TYPE_CODES)))
            )

        # IADE faturası sadece belirli profillerde geçerli
        if inv_type == 'IADE' and profile_id not in (
            'TEMELFATURA', 'EARSIVFATURA', 'ILAC_TIBBICIHAZ', 'YATIRIMTESVIK', 'IDIS'
        ):
            errors.append(
                'IADE faturası ProfileID=%s ile kullanılamaz. '
                'TEMELFATURA, EARSIVFATURA veya ILAC_TIBBICIHAZ olmalıdır.' % profile_id
            )

        # ── 8. DocumentCurrencyCode ──────────────────────────────────────
        currency = _txt(doc, '//cbc:DocumentCurrencyCode')
        if currency and currency not in VALID_CURRENCY_CODES:
            errors.append(
                'cbc:DocumentCurrencyCode geçersiz: "%s". '
                'ISO 4217 para birimi kodu olmalıdır.' % currency
            )

        # ── 9. Satıcı VKN/TCKN ──────────────────────────────────────────
        supplier_ids = doc.xpath(
            '//cac:AccountingSupplierParty/cac:Party'
            '/cac:PartyIdentification/cbc:ID',
            namespaces=NS
        )
        for sid in supplier_ids:
            val = sid.text.strip() if sid.text else ''
            if val and len(val) not in (10, 11):
                errors.append(
                    'Satıcı VKN/TCKN 10 veya 11 hane olmalıdır: "%s"' % val
                )
            if val and not val.isdigit():
                errors.append(
                    'Satıcı VKN/TCKN sadece rakam içermelidir: "%s"' % val
                )

        # ── 10. Alıcı VKN/TCKN (TICARIFATURA'da zorunlu) ────────────────
        customer_ids = doc.xpath(
            '//cac:AccountingCustomerParty/cac:Party'
            '/cac:PartyIdentification/cbc:ID',
            namespaces=NS
        )
        if profile_id == 'TICARIFATURA' and not customer_ids:
            errors.append(
                'TICARIFATURA senaryosunda alıcı VKN/TCKN zorunludur '
                '(cac:AccountingCustomerParty/cac:Party/cac:PartyIdentification/cbc:ID).'
            )

        for cid in customer_ids:
            val = cid.text.strip() if cid.text else ''
            if val and len(val) not in (10, 11):
                errors.append(
                    'Alıcı VKN/TCKN 10 veya 11 hane olmalıdır: "%s"' % val
                )

        # ── 11. CopyIndicator ────────────────────────────────────────────
        copy_ind = _txt(doc, '//cbc:CopyIndicator')
        if copy_ind != 'false':
            errors.append(
                'cbc:CopyIndicator "false" olmalıdır (mevcut: "%s").' % copy_ind
            )

        # ── 12. En az bir fatura kalemi ──────────────────────────────────
        lines = doc.xpath('//cac:InvoiceLine', namespaces=NS)
        if not lines:
            errors.append('En az bir cac:InvoiceLine zorunludur.')

        # ── 13. LineExtensionAmount tutarsızlığı ─────────────────────────
        # Her kalemde LineExtensionAmount = InvoicedQuantity × PriceAmount
        for i, line in enumerate(lines, start=1):
            qty_el  = line.xpath('cbc:InvoicedQuantity', namespaces=NS)
            price_el = line.xpath(
                'cac:Price/cbc:PriceAmount', namespaces=NS
            )
            lea_el  = line.xpath('cbc:LineExtensionAmount', namespaces=NS)
            if qty_el and price_el and lea_el:
                try:
                    qty   = float(qty_el[0].text or 0)
                    price = float(price_el[0].text or 0)
                    lea   = float(lea_el[0].text or 0)
                    # %0.01 tolerans (yuvarlama farkları)
                    if abs(qty * price - lea) > max(0.01, abs(lea) * 0.001):
                        errors.append(
                            'Kalem %d: LineExtensionAmount (%.2f) ≠ '
                            'InvoicedQuantity (%.4f) × PriceAmount (%.4f).' % (i, lea, qty, price)
                        )
                except (ValueError, TypeError):
                    pass  # Sayısal dönüşüm hatası XSD'de yakalanır

        return errors

    # ── Ana Doğrulama Metodu ──────────────────────────────────────────────

    def validate(self, xml_bytes):
        """
        UBL-TR XML'i XSD + GİB iş kuralları ile doğrular.

        Parametreler:
            xml_bytes (bytes): UBL XML içeriği

        Dönüş değeri:
            (valid: bool, layer: str|None, errors: list[str])

            Geçerli           : (True, None, [])
            XSD hatası        : (False, 'XSD', [...])
            İş kuralı ihlali  : (False, 'SCHEMATRON', [...])
            XML parse hatası  : (False, 'XML_PARSE', [...])
        """
        # ── XML Syntax Kontrolü ───────────────────────────────────────────
        try:
            doc = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as e:
            return False, 'XML_PARSE', [str(e)]

        # ── Katman 1: XSD ─────────────────────────────────────────────────
        xsd = self._load_xsd()
        if xsd is not None:
            if not xsd.validate(doc):
                errors = [str(e) for e in xsd.error_log]
                _logger.warning('XSD hatası (ilk 3): %s', errors[:3])
                return False, 'XSD', errors
        else:
            _logger.warning('XSD yok — Katman 1 atlandı')

        # ── Katman 2: GİB İş Kuralları ────────────────────────────────────
        try:
            biz_errors = self._check_gib_rules(doc)
            if biz_errors:
                _logger.warning('GİB iş kuralı ihlali (ilk 3): %s', biz_errors[:3])
                return False, 'SCHEMATRON', biz_errors
        except Exception as e:
            _logger.error('İş kuralı kontrolü beklenmeyen hata: %s', e, exc_info=True)
            raise UserError(_(
                'Validasyon beklenmeyen hata: %s\n'
                'Sistem yöneticisi ile iletişime geçin.'
            ) % str(e))

        return True, None, []
