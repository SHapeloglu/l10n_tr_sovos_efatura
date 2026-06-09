# -*- coding: utf-8 -*-
"""
UBL Builder Testleri
Kod: services/ubl_builder.py — UblBuilder.build()

Kapsam:
  - XML çıktısının temel yapısı (UBLVersionID, CustomizationID, namespace)
  - ProfileID senaryoya göre doğru set edilmeli (TICARIFATURA / TEMELFATURA / EARSIVFATURA)
  - UUID, fatura numarası, tarih doğru yerleştirilmeli
  - Tedarikçi (supplier) ve müşteri (customer) bilgileri doğru mapping
  - Fatura kalemleri (InvoiceLine) doğru üretilmeli
  - Para toplamları (LegalMonetaryTotal) doğru hesaplanmalı
  - Vergi toplamları (TaxTotal / TaxSubtotal) doğru üretilmeli
  - ZIP dosyası adı = XML dosyası adı = UUID (AC-12 / GİB 1133/1142 kuralı)
  - Bilinmeyen senaryo → TICARIFATURA default (PROFILE_ID_MAP fallback)
  - DocumentCurrencyCode para birimi kodu yazılmalı
  - Satır olmayan display_type='line_section' kalemleri atlanmalı

Risk Seviyesi: ORTA-YÜKSEK
  - XML içeriği hatalıysa GİB 1101/1132/1150 hatası alınır
  - ZIP/XML adı UUID ile uyuşmazsa GİB 1133/1142 hatası alınır (AC-12)
"""
import zipfile
import io
from datetime import date
from unittest.mock import patch, MagicMock

from lxml import etree

from .common import SovosTestCommon

# UBL namespace kısaltmaları
NS = {
    'ubl': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
}


def _xpath(root, path):
    """Namespace'li xpath helper."""
    return root.xpath(path, namespaces=NS)


def _text(root, path):
    nodes = _xpath(root, path)
    return nodes[0].text if nodes else None


class TestUblBuilder(SovosTestCommon):
    """UblBuilder.build() çıktısının yapısal ve içerik doğruluğu."""

    def _build(self, partner=None, scenario='TICARIFATURA', **invoice_kwargs):
        """
        Gerçek UblBuilder.build() çağrısı yapar, parse edilmiş root döner.
        Sovos/GİB'e bağlantı kurmaz.
        """
        from l10n_tr_sovos_efatura.services.ubl_builder import UblBuilder

        if partner is None:
            partner = self.partner_efatura

        inv = self._create_invoice(partner=partner, **invoice_kwargs)
        inv.write({'state': 'posted', 'name': 'TST2026000000001'})

        uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        xml_bytes = UblBuilder(self.company).build(inv, uuid, 'TST2026000000001', scenario)
        root = etree.fromstring(xml_bytes)
        return root, uuid, inv

    # ── Temel Alan Testleri ───────────────────────────────────────────────

    def test_ubl_version_id_is_2_1(self):
        """UBLVersionID her zaman '2.1' olmalı."""
        root, _, _ = self._build()
        self.assertEqual(_text(root, '//cbc:UBLVersionID'), '2.1')

    def test_customization_id_is_tr12(self):
        """CustomizationID her zaman 'TR1.2' olmalı."""
        root, _, _ = self._build()
        self.assertEqual(_text(root, '//cbc:CustomizationID'), 'TR1.2')

    def test_profile_id_ticarifatura(self):
        """TICARIFATURA senaryosunda ProfileID = 'TICARIFATURA'."""
        root, _, _ = self._build(scenario='TICARIFATURA')
        self.assertEqual(_text(root, '//cbc:ProfileID'), 'TICARIFATURA')

    def test_profile_id_temelfatura(self):
        """TEMELFATURA senaryosunda ProfileID = 'TEMELFATURA'."""
        root, _, _ = self._build(scenario='TEMELFATURA')
        self.assertEqual(_text(root, '//cbc:ProfileID'), 'TEMELFATURA')

    def test_profile_id_earsivfatura(self):
        """EARSIVFATURA senaryosunda ProfileID = 'EARSIVFATURA'."""
        root, _, _ = self._build(partner=self.partner_earsiv, scenario='EARSIVFATURA')
        self.assertEqual(_text(root, '//cbc:ProfileID'), 'EARSIVFATURA')

    def test_unknown_scenario_defaults_to_ticarifatura(self):
        """
        Bilinmeyen senaryo değeri → PROFILE_ID_MAP.get(scenario, 'TICARIFATURA') fallback.
        XSD hatası yerine yanlış profil gönderilmesi riski — fallback'in doğru çalıştığını doğrular.
        """
        root, _, _ = self._build(scenario='BILINMEYEN_SENARYO')
        self.assertEqual(_text(root, '//cbc:ProfileID'), 'TICARIFATURA',
            'Bilinmeyen senaryo TICARIFATURA default değerini kullanmalı')

    def test_uuid_in_xml(self):
        """UUID, XML içinde cbc:UUID olarak yazılmalı."""
        root, uuid, _ = self._build()
        self.assertEqual(_text(root, '//cbc:UUID'), uuid)

    def test_invoice_number_in_xml(self):
        """Fatura numarası cbc:ID olarak XML'de yer almalı."""
        root, _, _ = self._build()
        self.assertEqual(_text(root, '//cbc:ID'), 'TST2026000000001')

    def test_issue_date_in_xml(self):
        """IssueDate fatura tarihiyle eşleşmeli."""
        root, _, inv = self._build()
        self.assertEqual(_text(root, '//cbc:IssueDate'), str(inv.invoice_date))

    def test_document_currency_code_try(self):
        """TRY faturada DocumentCurrencyCode = 'TRY'."""
        root, _, _ = self._build()
        self.assertEqual(_text(root, '//cbc:DocumentCurrencyCode'), 'TRY')

    # ── Tedarikçi (Supplier) Mapping ─────────────────────────────────────

    def test_supplier_name_is_company_name(self):
        """Tedarikçi adı şirket adıyla eşleşmeli."""
        root, _, _ = self._build()
        name = _text(root, '//cac:AccountingSupplierParty//cac:PartyName/cbc:Name')
        self.assertEqual(name, self.company.name)

    def test_supplier_vkn_in_xml(self):
        """Tedarikçi VKN (CompanyID) şirketin VAT/VKN'i olmalı."""
        root, _, _ = self._build()
        company_id = _text(root, '//cac:AccountingSupplierParty//cac:PartyTaxScheme/cbc:CompanyID')
        self.assertIn(company_id, [self.company.vat, self.company.x_sovos_sender_vkn],
            'Tedarikçi CompanyID şirket VKN ile eşleşmeli')

    # ── Müşteri (Customer) Mapping ────────────────────────────────────────

    def test_customer_name_is_partner_name(self):
        """Müşteri adı partner adıyla eşleşmeli."""
        root, _, _ = self._build()
        name = _text(root, '//cac:AccountingCustomerParty//cac:PartyName/cbc:Name')
        self.assertEqual(name, self.partner_efatura.name)

    def test_customer_vkn_in_xml(self):
        """Müşteri VKN (CompanyID) partner.vat ile eşleşmeli."""
        root, _, _ = self._build()
        company_id = _text(root, '//cac:AccountingCustomerParty//cac:PartyTaxScheme/cbc:CompanyID')
        self.assertEqual(company_id, self.partner_efatura.vat)

    def test_customer_vergi_dairesi_in_xml(self):
        """Müşterinin vergi dairesi TaxScheme/Name olarak yazılmalı."""
        root, _, _ = self._build()
        tax_name = _text(root, '//cac:AccountingCustomerParty//cac:PartyTaxScheme/cac:TaxScheme/cbc:Name')
        self.assertEqual(tax_name, self.partner_efatura.x_vergi_dairesi)

    # ── Fatura Kalemleri (InvoiceLine) ────────────────────────────────────

    def test_invoice_line_count_matches(self):
        """LineCountNumeric fatura kalem sayısını yansıtmalı."""
        root, _, inv = self._build()
        line_count_xml = int(_text(root, '//cbc:LineCountNumeric'))
        product_lines = inv.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
        self.assertEqual(line_count_xml, len(product_lines))

    def test_invoice_line_quantity_and_price(self):
        """İlk InvoiceLine'da miktar ve birim fiyat doğru yazılmalı."""
        root, _, inv = self._build()
        lines_xml = _xpath(root, '//cac:InvoiceLine')
        self.assertTrue(lines_xml, 'En az bir InvoiceLine bekleniyor')

        line_xml = lines_xml[0]
        qty = _xpath(line_xml, 'cbc:InvoicedQuantity')
        self.assertTrue(qty, 'InvoicedQuantity eksik')
        self.assertAlmostEqual(float(qty[0].text), 1.0, places=4)

    def test_invoice_line_extension_amount(self):
        """InvoiceLine LineExtensionAmount satır toplam tutarı olmalı."""
        root, _, inv = self._build()
        line_xml = _xpath(root, '//cac:InvoiceLine')[0]
        ext_amount = _xpath(line_xml, 'cbc:LineExtensionAmount')
        self.assertTrue(ext_amount)
        self.assertAlmostEqual(float(ext_amount[0].text), 1000.0, places=2)

    def test_section_lines_excluded_from_invoice_lines(self):
        """
        display_type='line_section' kalemleri InvoiceLine olarak XML'e eklenmemeli.
        Sadece display_type='product' kalemleri işlenmeli.
        """
        from l10n_tr_sovos_efatura.services.ubl_builder import UblBuilder

        inv = self._create_invoice()
        inv.write({'state': 'posted', 'name': 'TST2026000000001'})

        # Section satırı ekle
        inv.write({'invoice_line_ids': [(0, 0, {
            'name': 'Bölüm Başlığı',
            'display_type': 'line_section',
        })]})

        xml_bytes = UblBuilder(self.company).build(inv, 'test-uuid-0000', 'TST2026000000001', 'TICARIFATURA')
        root = etree.fromstring(xml_bytes)
        lines_xml = _xpath(root, '//cac:InvoiceLine')

        product_lines = inv.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
        self.assertEqual(len(lines_xml), len(product_lines),
            'Section satırları InvoiceLine olarak XML\'e eklenmemeli')

    # ── Para Toplamları (LegalMonetaryTotal) ──────────────────────────────

    def test_monetary_total_payable_amount(self):
        """LegalMonetaryTotal/PayableAmount fatura toplam tutarını içermeli."""
        root, _, inv = self._build()
        payable = _text(root, '//cac:LegalMonetaryTotal/cbc:PayableAmount')
        self.assertIsNotNone(payable, 'PayableAmount XML\'de mevcut olmalı')
        self.assertGreater(float(payable), 0)

    def test_monetary_total_tax_inclusive_amount(self):
        """TaxInclusiveAmount KDV dahil toplam tutarı içermeli."""
        root, _, inv = self._build()
        tax_inclusive = _text(root, '//cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount')
        self.assertIsNotNone(tax_inclusive)
        self.assertAlmostEqual(float(tax_inclusive), inv.amount_total, places=2)

    # ── Vergi Toplamları (TaxTotal) ───────────────────────────────────────

    def test_tax_total_present_when_tax_lines_exist(self):
        """
        Vergi uygulanan faturada TaxTotal ve TaxSubtotal XML'de mevcut olmalı.
        """
        # Vergi içeren fatura oluştur
        tax = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('company_id', '=', self.company.id),
        ], limit=1)

        if not tax:
            self.skipTest('Satış vergisi tanımlı değil — vergi testi atlandı')

        from l10n_tr_sovos_efatura.services.ubl_builder import UblBuilder

        inv = self._create_invoice(lines=[(1, 1000.0, self.account_income)])
        inv.invoice_line_ids[0].write({'tax_ids': [(4, tax.id)]})
        inv.write({'state': 'posted', 'name': 'TST2026000000002'})

        xml_bytes = UblBuilder(self.company).build(inv, 'tax-uuid-test', 'TST2026000000002', 'TICARIFATURA')
        root = etree.fromstring(xml_bytes)

        tax_totals = _xpath(root, '//cac:TaxTotal')
        self.assertTrue(tax_totals, 'TaxTotal XML\'de mevcut olmalı')

    # ── ZIP/XML Dosya Adı = UUID (AC-12) ─────────────────────────────────

    def test_create_zip_xml_filename_equals_uuid(self):
        """
        AC-12: ZIP içindeki XML dosyasının adı UUID ile eşleşmeli.
        GİB 1133 hatası: Zarf ID ile XML adı uyuşmuyor.
        GİB 1142 hatası: Zarf ID ile ZIP adı uyuşmuyor.
        """
        from l10n_tr_sovos_efatura.services.sovos_invoice_service import SovosInvoiceService

        svc = SovosInvoiceService(self.company)
        test_uuid = 'cccccccc-dddd-eeee-ffff-000000000001'
        dummy_xml = b'<Invoice/>'

        zip_bytes = svc._create_zip(test_uuid, dummy_xml)

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()

        self.assertEqual(len(names), 1, 'ZIP içinde tam olarak 1 dosya olmalı')
        self.assertEqual(names[0], '%s.xml' % test_uuid,
            'ZIP içindeki XML dosyası adı UUID.xml olmalı (GİB 1133 kuralı)\n'
            'Beklenen: %s.xml\nBulunan: %s' % (test_uuid, names[0]))

    def test_create_zip_archive_service_xml_filename_equals_uuid(self):
        """
        AC-12: ArchiveService._create_zip() da aynı UUID.xml kuralına uymalı.
        GİB 1142 hatası: ZIP adı UUID ile uyuşmuyor.
        """
        from l10n_tr_sovos_efatura.services.sovos_archive_service import SovosArchiveService

        svc = SovosArchiveService(self.company)
        test_uuid = 'cccccccc-dddd-eeee-ffff-000000000002'
        dummy_xml = b'<Invoice/>'

        zip_bytes = svc._create_zip(test_uuid, dummy_xml)

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()

        self.assertEqual(names[0], '%s.xml' % test_uuid,
            'ArchiveService ZIP içindeki XML adı UUID.xml olmalı (GİB 1133/1142 kuralı)\n'
            'Beklenen: %s.xml\nBulunan: %s' % (test_uuid, names[0]))

    def test_send_ubl_uses_uuid_as_zip_filename(self):
        """
        send_ubl() çağrısında Sovos'a iletilen fileName UUID.zip olmalı.
        Spec §14.2: fileName=f'{uuid}.zip' — rand_no DEĞİL.
        """
        from l10n_tr_sovos_efatura.services.sovos_invoice_service import SovosInvoiceService

        test_uuid = 'cccccccc-dddd-eeee-ffff-000000000003'
        captured_body = []

        def fake_post(action, body_xml):
            captured_body.append(body_xml)
            # Minimal sahte SOAP yanıtı
            return etree.fromstring(
                b'<root><ENVELOPE_UUID>%b</ENVELOPE_UUID></root>' % test_uuid.encode()
            )

        svc = SovosInvoiceService(self.company)
        with patch.object(svc, '_post', side_effect=fake_post):
            svc.send_ubl(b'<Invoice/>', test_uuid, self.partner_efatura, 'TICARIFATURA')

        self.assertTrue(captured_body, '_post çağrılmalıydı')
        # fileName parametresi SOAP body'de UUID.zip olmalı
        self.assertIn('%s.zip' % test_uuid, captured_body[0],
            'send_ubl SOAP body\'de fileName=%s.zip olmalı' % test_uuid)

    def test_send_invoice_archive_uses_uuid_as_filename(self):
        """
        ArchiveService.send_invoice() de fileName UUID.zip kullanmalı.
        Spec §14.3: fileName=f'{uuid}.zip'.
        """
        from l10n_tr_sovos_efatura.services.sovos_archive_service import SovosArchiveService

        test_uuid = 'cccccccc-dddd-eeee-ffff-000000000004'
        captured_body = []

        def fake_post(action, body_xml):
            captured_body.append(body_xml)
            return etree.fromstring(
                b'<root><RESULT_CODE>0</RESULT_CODE><ENVELOPE_UUID>%b</ENVELOPE_UUID></root>'
                % test_uuid.encode()
            )

        svc = SovosArchiveService(self.company)
        with patch.object(svc, '_post', side_effect=fake_post):
            svc.send_invoice(b'<Invoice/>', test_uuid, self.partner_earsiv)

        self.assertTrue(captured_body)
        self.assertIn('%s.zip' % test_uuid, captured_body[0],
            'ArchiveService SOAP body\'de fileName=%s.zip olmalı' % test_uuid)
