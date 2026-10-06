# -*- coding: utf-8 -*-
"""
UBL Validator Testleri — v8.0 GÜNCELLENDİ
==========================================
Test edilen kod: services/ubl_validator.py
Test edilen sınıf/metod: UblValidator.validate(xml_bytes)

UBL VALİDASYON KATMANLARI
--------------------------
validate() metodu XML'i 3 aşamada kontrol eder. Herhangi bir aşama
başarısız olursa fatura GÖNDERİLMEZ.

    Katman 0 — XML_PARSE
        XML sözdizimi geçerli mi? (well-formed)
        Hatalıysa: (False, 'XML_PARSE', [...])
        ↓ Geçtiyse devam et

    Katman 1 — XSD  (lxml.etree.XMLSchema)
        XML yapısı GİB şemasına uygun mu? (zorunlu alanlar, tipler)
        Dosya yoksa: ATLA (uyarı logla, bloke etme)
        Hatalıysa: (False, 'XSD', [...])
        ↓ Geçtiyse devam et

    Katman 2 — GİB İş Kuralları  (lxml XPath)
        GİB Schematron'un fatura iş kuralları XPath ile doğrulanır.
        saxonche, derlenmiş .xsl dosyası GEREKMEZ.
        Hatalıysa: (False, 'SCHEMATRON', [...])
        ↓ Geçtiyse devam et

    Başarı → (True, None, [])

v8.0 değişiklikleri (v6.1'den):
  - saxonche kaldırıldı — lxml + XPath ile GİB iş kuralları
  - _run_schematron_saxon → _check_gib_rules
  - _saxonche_available() fonksiyonu kaldırıldı
  - Exception davranışı değişti: artık UserError fırlatır (gönderimi BLOKLAR)
  - XSD dizin yapısı değişti: schemas/maindoc/ + schemas/common/

Risk Seviyesi: YÜKSEK — yanlış validasyon = GİB reddi
"""
from unittest.mock import patch, MagicMock

from .common import SovosTestCommon


# ── Test XML sabitleri ────────────────────────────────────────────────────────

# Minimal parse edilebilir XML (XSD/iş kuralı testlerinde mock ile geçilir)
VALID_XML = b'''<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:UBLVersionID>2.1</cbc:UBLVersionID>
  <cbc:ID>TST2026000000001</cbc:ID>
</Invoice>'''

# Kasıtlı bozuk XML — XML_PARSE hatası üretir
BROKEN_XML = b'<?xml version="1.0"?><Unclosed'


class TestUblValidator(SovosTestCommon):
    """
    UblValidator sınıfının 3 katmanlı validasyon sürecini test eder.

    Mock stratejisi:
        - _load_xsd()        → XSD nesnesini mock'la (disk erişimi gereksiz)
        - _check_gib_rules() → İş kuralı sonucunu mock'la
        - XML_PARSE testi    → Mock yok; lxml built-in, harici bağımlılık yok
    """

    # ════════════════════════════════════════════════════════════════════
    # KATMAN 0: XML_PARSE
    # ════════════════════════════════════════════════════════════════════

    def test_validate_returns_xml_parse_error_on_broken_xml(self):
        """
        Bozuk XML → (False, 'XML_PARSE', [...]) dönmeli.

        Mock kullanılmaz — lxml parse'ı harici bağımlılık gerektirmez.
        """
        from odoo.addons.l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        valid, layer, errors = UblValidator().validate(BROKEN_XML)

        self.assertFalse(valid)
        self.assertEqual(layer, 'XML_PARSE')
        self.assertTrue(errors, 'Hata listesi dolu olmalı')

    # ════════════════════════════════════════════════════════════════════
    # KATMAN 1: XSD
    # ════════════════════════════════════════════════════════════════════

    def test_validate_xsd_layer_with_invalid_xml(self):
        """
        XSD doğrulaması başarısız → (False, 'XSD', [...]) dönmeli.
        """
        from odoo.addons.l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        mock_xsd = MagicMock()
        mock_xsd.validate.return_value = False
        mock_xsd.error_log = ['cbc:ID zorunlu alan eksik']

        validator = UblValidator()
        with patch.object(validator, '_load_xsd', return_value=mock_xsd):
            valid, layer, errors = validator.validate(VALID_XML)

        self.assertFalse(valid)
        self.assertEqual(layer, 'XSD')
        self.assertTrue(errors)

    def test_validate_skips_xsd_when_schema_file_missing(self):
        """
        XSD dosyası yoksa (_load_xsd None döner) katman ATLANMALI,
        gönderim bloke edilmemeli.
        """
        from odoo.addons.l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        validator = UblValidator()
        with patch.object(validator, '_load_xsd', return_value=None), \
             patch.object(validator, '_check_gib_rules', return_value=[]):
            valid, layer, errors = validator.validate(VALID_XML)

        self.assertTrue(valid, 'XSD yoksa katman 1 atlanmalı, geçerli sayılmalı')

    # ════════════════════════════════════════════════════════════════════
    # KATMAN 2: GİB İŞ KURALLARI
    # ════════════════════════════════════════════════════════════════════

    def test_validate_business_rule_failure(self):
        """
        GİB iş kuralı ihlali → (False, 'SCHEMATRON', [...]) dönmeli.

        Örnek: Hatalı fatura ID formatı, geçersiz ProfileID vb.
        """
        from odoo.addons.l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        mock_xsd = MagicMock()
        mock_xsd.validate.return_value = True  # XSD geçti

        validator = UblValidator()
        with patch.object(validator, '_load_xsd', return_value=mock_xsd), \
             patch.object(validator, '_check_gib_rules',
                          return_value=['cbc:ID formatı hatalı: ABC format bekleniyor']):
            valid, layer, errors = validator.validate(VALID_XML)

        self.assertFalse(valid)
        self.assertEqual(layer, 'SCHEMATRON')
        self.assertTrue(errors)

    def test_validate_business_rule_exception_blocks_sending(self):
        """
        _check_gib_rules beklenmedik exception verirse UserError fırlatmalı
        ve gönderimi BLOKLAMAMALI.

        v8.0 davranış değişikliği (v6.1'den farklı):
            v6.1: exception → atla, geçerli say (savunmacı)
            v8.0: exception → UserError fırlat (gönderimi blokla)

        Neden değişti?
            Schematron artık GİB'in kendi .xml dosyasından türetilmiş
            deterministik XPath kuralları. Beklenmedik exception,
            validasyonun hiç çalışmadığı anlamına gelir. Bu durumda
            GİB'e hatalı fatura göndermek yerine kullanıcıyı bilgilendirip
            durmak daha güvenlidir.
        """
        from odoo.addons.l10n_tr_sovos_efatura.services.ubl_validator import UblValidator
        from odoo.exceptions import UserError

        mock_xsd = MagicMock()
        mock_xsd.validate.return_value = True

        validator = UblValidator()
        with patch.object(validator, '_load_xsd', return_value=mock_xsd), \
             patch.object(validator, '_check_gib_rules',
                          side_effect=RuntimeError('XPath beklenmedik hata')):
            with self.assertRaises(UserError):
                validator.validate(VALID_XML)

    def test_validate_skips_business_rules_when_not_applicable(self):
        """
        _check_gib_rules boş liste döndürürse (ihlal yok) geçerli sayılmalı.
        """
        from odoo.addons.l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        mock_xsd = MagicMock()
        mock_xsd.validate.return_value = True

        validator = UblValidator()
        with patch.object(validator, '_load_xsd', return_value=mock_xsd), \
             patch.object(validator, '_check_gib_rules', return_value=[]):
            valid, layer, errors = validator.validate(VALID_XML)

        self.assertTrue(valid)
        self.assertIsNone(layer)
        self.assertEqual(errors, [])

    # ════════════════════════════════════════════════════════════════════
    # BAŞARILI VALİDASYON
    # ════════════════════════════════════════════════════════════════════

    def test_validate_returns_true_when_both_layers_pass(self):
        """
        XSD geçti + iş kuralları geçti → (True, None, []) dönmeli.
        """
        from odoo.addons.l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        mock_xsd = MagicMock()
        mock_xsd.validate.return_value = True

        validator = UblValidator()
        with patch.object(validator, '_load_xsd', return_value=mock_xsd), \
             patch.object(validator, '_check_gib_rules', return_value=[]):
            valid, layer, errors = validator.validate(VALID_XML)

        self.assertTrue(valid)
        self.assertIsNone(layer)
        self.assertEqual(errors, [])

    # ════════════════════════════════════════════════════════════════════
    # XSD CACHE
    # ════════════════════════════════════════════════════════════════════

    def test_xsd_loaded_once_and_cached(self):
        """
        Aynı UblValidator instance'ında XSD şeması sadece BİR KEZ yüklenmeli.

        XSD parse etmek pahalıdır (CPU + bellek).
        İlk yüklemeden sonra self._xsd'de cache'de tutulur.
        """
        from odoo.addons.l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        validator = UblValidator()
        mock_xsd = MagicMock()
        mock_xsd.validate.return_value = True

        load_count = {'n': 0}

        def counting_load():
            if validator._xsd is None:
                load_count['n'] += 1
                validator._xsd = mock_xsd
            return validator._xsd

        with patch.object(validator, '_load_xsd', side_effect=counting_load), \
             patch.object(validator, '_check_gib_rules', return_value=[]):
            validator.validate(VALID_XML)
            validator.validate(VALID_XML)

        self.assertEqual(load_count['n'], 1,
            'XSD şeması sadece bir kez yüklenmeli (cache)')

    # ════════════════════════════════════════════════════════════════════
    # GİB İŞ KURALI BİRİMSEL TESTLERİ
    # ════════════════════════════════════════════════════════════════════

    def test_gib_rules_invoice_id_format(self):
        """
        _check_gib_rules() ID format kuralını doğru yakalamalı.
        ABC2026000000001 (16 karakter) formatı zorunludur.
        """
        from odoo.addons.l10n_tr_sovos_efatura.services.ubl_validator import UblValidator
        from lxml import etree

        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2">
  <ext:UBLExtensions><ext:UBLExtension><ext:ExtensionContent/></ext:UBLExtension></ext:UBLExtensions>
  <cbc:UBLVersionID>2.1</cbc:UBLVersionID>
  <cbc:CustomizationID>TR1.2</cbc:CustomizationID>
  <cbc:ProfileID>TICARIFATURA</cbc:ProfileID>
  <cbc:ID>YANLIS</cbc:ID>
  <cbc:CopyIndicator>false</cbc:CopyIndicator>
  <cbc:UUID>550e8400-e29b-41d4-a716-446655440000</cbc:UUID>
  <cbc:IssueDate>2026-06-23</cbc:IssueDate>
  <cbc:InvoiceTypeCode>SATIS</cbc:InvoiceTypeCode>
  <cbc:DocumentCurrencyCode>TRY</cbc:DocumentCurrencyCode>
  <cbc:LineCountNumeric>1</cbc:LineCountNumeric>
  <cac:AccountingSupplierParty><cac:Party>
    <cac:PartyIdentification><cbc:ID>1234567890</cbc:ID></cac:PartyIdentification>
  </cac:Party></cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty><cac:Party>
    <cac:PartyIdentification><cbc:ID>9876543210</cbc:ID></cac:PartyIdentification>
  </cac:Party></cac:AccountingCustomerParty>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="TRY">100.00</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="TRY">100.00</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="TRY">120.00</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="TRY">120.00</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
  <cac:InvoiceLine>
    <cbc:ID>1</cbc:ID>
    <cbc:InvoicedQuantity unitCode="C62">1</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="TRY">100.00</cbc:LineExtensionAmount>
    <cac:Item><cbc:Name>Test</cbc:Name></cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="TRY">100.00</cbc:PriceAmount></cac:Price>
  </cac:InvoiceLine>
</Invoice>'''

        doc = etree.fromstring(xml)
        errors = UblValidator()._check_gib_rules(doc)

        id_errors = [e for e in errors if 'cbc:ID' in e]
        self.assertTrue(id_errors, 'Hatalı ID formatı yakalanmalı')

    def test_gib_rules_future_date_rejected(self):
        """
        Gelecek tarihli fatura → IssueDate hatası dönmeli.
        """
        from odoo.addons.l10n_tr_sovos_efatura.services.ubl_validator import UblValidator
        from lxml import etree

        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2">
  <ext:UBLExtensions><ext:UBLExtension><ext:ExtensionContent/></ext:UBLExtension></ext:UBLExtensions>
  <cbc:UBLVersionID>2.1</cbc:UBLVersionID>
  <cbc:CustomizationID>TR1.2</cbc:CustomizationID>
  <cbc:ProfileID>TICARIFATURA</cbc:ProfileID>
  <cbc:ID>ABC2026000000001</cbc:ID>
  <cbc:CopyIndicator>false</cbc:CopyIndicator>
  <cbc:UUID>550e8400-e29b-41d4-a716-446655440000</cbc:UUID>
  <cbc:IssueDate>2099-01-01</cbc:IssueDate>
  <cbc:InvoiceTypeCode>SATIS</cbc:InvoiceTypeCode>
  <cbc:DocumentCurrencyCode>TRY</cbc:DocumentCurrencyCode>
  <cbc:LineCountNumeric>1</cbc:LineCountNumeric>
  <cac:AccountingSupplierParty><cac:Party>
    <cac:PartyIdentification><cbc:ID>1234567890</cbc:ID></cac:PartyIdentification>
  </cac:Party></cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty><cac:Party>
    <cac:PartyIdentification><cbc:ID>9876543210</cbc:ID></cac:PartyIdentification>
  </cac:Party></cac:AccountingCustomerParty>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="TRY">100.00</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="TRY">100.00</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="TRY">120.00</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="TRY">120.00</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
  <cac:InvoiceLine>
    <cbc:ID>1</cbc:ID>
    <cbc:InvoicedQuantity unitCode="C62">1</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="TRY">100.00</cbc:LineExtensionAmount>
    <cac:Item><cbc:Name>Test</cbc:Name></cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="TRY">100.00</cbc:PriceAmount></cac:Price>
  </cac:InvoiceLine>
</Invoice>'''

        doc = etree.fromstring(xml)
        errors = UblValidator()._check_gib_rules(doc)

        date_errors = [e for e in errors if 'IssueDate' in e and 'gelecek' in e.lower()]
        self.assertTrue(date_errors, 'Gelecek tarih hatası yakalanmalı')

    def test_gib_rules_ticarifatura_requires_customer_vkn(self):
        """
        TICARIFATURA senaryosunda alıcı VKN/TCKN zorunludur.
        """
        from odoo.addons.l10n_tr_sovos_efatura.services.ubl_validator import UblValidator
        from lxml import etree

        # Alıcı PartyIdentification olmadan TICARIFATURA
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2">
  <ext:UBLExtensions><ext:UBLExtension><ext:ExtensionContent/></ext:UBLExtension></ext:UBLExtensions>
  <cbc:UBLVersionID>2.1</cbc:UBLVersionID>
  <cbc:CustomizationID>TR1.2</cbc:CustomizationID>
  <cbc:ProfileID>TICARIFATURA</cbc:ProfileID>
  <cbc:ID>ABC2026000000001</cbc:ID>
  <cbc:CopyIndicator>false</cbc:CopyIndicator>
  <cbc:UUID>550e8400-e29b-41d4-a716-446655440000</cbc:UUID>
  <cbc:IssueDate>2026-06-23</cbc:IssueDate>
  <cbc:InvoiceTypeCode>SATIS</cbc:InvoiceTypeCode>
  <cbc:DocumentCurrencyCode>TRY</cbc:DocumentCurrencyCode>
  <cbc:LineCountNumeric>1</cbc:LineCountNumeric>
  <cac:AccountingSupplierParty><cac:Party>
    <cac:PartyIdentification><cbc:ID>1234567890</cbc:ID></cac:PartyIdentification>
  </cac:Party></cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty><cac:Party/></cac:AccountingCustomerParty>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="TRY">100.00</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="TRY">100.00</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="TRY">120.00</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="TRY">120.00</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
  <cac:InvoiceLine>
    <cbc:ID>1</cbc:ID>
    <cbc:InvoicedQuantity unitCode="C62">1</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="TRY">100.00</cbc:LineExtensionAmount>
    <cac:Item><cbc:Name>Test</cbc:Name></cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="TRY">100.00</cbc:PriceAmount></cac:Price>
  </cac:InvoiceLine>
</Invoice>'''

        doc = etree.fromstring(xml)
        errors = UblValidator()._check_gib_rules(doc)

        vkn_errors = [e for e in errors if 'TICARIFATURA' in e and 'VKN' in e]
        self.assertTrue(vkn_errors, 'TICARIFATURA alıcı VKN eksikliği yakalanmalı')
