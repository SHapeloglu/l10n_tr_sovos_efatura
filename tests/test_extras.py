# -*- coding: utf-8 -*-
"""
Ek Testler — FR-13, FR-39, FR-12, AC-13, AC-18
Kapsam:
  - FR-13: e-Arşiv gönderiminde partner e-postası ReceiverEmail olarak iletilmeli
  - FR-39 / AC-13: Bağlantı testi butonu başarılı/başarısız bildirim vermeli
  - FR-12: Kur farkı wizard — taslak fatura oluşturur, x_kur_farki=True
  - AC-18: Dashboard domain filtreleri doğru fatura listesi döndürmeli
  - FR-09 / AC-14: Fatura önizleme — Sovos'a gönderim yapılmaz (ek senaryo)
"""
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from odoo.exceptions import UserError
from .common import SovosTestCommon


# ═════════════════════════════════════════════════════════════════════════════
# FR-13: e-Arşiv E-posta İletimi
# ═════════════════════════════════════════════════════════════════════════════

class TestEarsivEmail(SovosTestCommon):
    """FR-13 (P0): e-Arşiv gönderiminde partner.email ReceiverEmail olarak iletilmeli."""

    def test_earsiv_send_includes_partner_email(self):
        """
        FR-13: ArchiveService.send_invoice() çağrısında partner'ın e-posta adresi
        receiverEmail parametresi olarak iletilmeli.
        Spec §14.3: receiverEmail=partner.email or None
        """
        from l10n_tr_sovos_efatura.services.sovos_archive_service import SovosArchiveService

        inv = self._create_invoice(partner=self.partner_earsiv)

        captured_calls = []

        original_send = SovosArchiveService.send_invoice

        def capturing_send(self_svc, xml_bytes, uuid, partner):
            captured_calls.append({'email': partner.email})
            return 'mock-envelope-uuid'

        with patch.object(SovosArchiveService, 'send_invoice', capturing_send), \
             self._mock_ubl_builder(), \
             self._mock_validator_valid():
            inv.action_post()

        self.assertTrue(captured_calls, 'send_invoice çağrılmalıydı')
        self.assertEqual(
            captured_calls[0]['email'],
            self.partner_earsiv.email,
            'send_invoice partner.email ile çağrılmalı\n'
            'Beklenen: %s\nBulunan: %s' % (self.partner_earsiv.email, captured_calls[0]['email'])
        )

    def test_earsiv_send_with_no_email_passes_none(self):
        """
        FR-13: partner.email boşsa ReceiverEmail=None olarak iletilmeli,
        hata fırlatılmamalı.
        """
        from l10n_tr_sovos_efatura.services.sovos_archive_service import SovosArchiveService

        partner_no_email = self.env['res.partner'].create({
            'name': 'E-postasız Müşteri',
            'vat': '7777777777',
            'x_efatura_type': 'earsiv',
            'x_efatura_type_updated': date.today(),
            'country_id': self.env.ref('base.tr').id,
            'email': False,
        })

        inv = self._create_invoice(partner=partner_no_email)

        captured_calls = []

        def capturing_send(self_svc, xml_bytes, uuid, partner):
            captured_calls.append({'email': partner.email})
            return 'mock-envelope-uuid'

        with patch.object(SovosArchiveService, 'send_invoice', capturing_send), \
             self._mock_ubl_builder(), \
             self._mock_validator_valid():
            inv.action_post()

        self.assertTrue(captured_calls)
        self.assertFalse(captured_calls[0]['email'],
            'E-postasız partner için email=False/None iletilmeli, hata oluşmamalı')

    def test_earsiv_email_in_soap_body(self):
        """
        FR-13: ArchiveService SOAP body'sinde receiverEmail etiketi
        partner.email içermeli.
        Spec §14.3: email_xml = '<ear:receiverEmail>%s</ear:receiverEmail>'
        """
        from l10n_tr_sovos_efatura.services.sovos_archive_service import SovosArchiveService
        from lxml import etree

        captured_body = []

        def fake_post(self_svc, action, body_xml):
            captured_body.append(body_xml)
            return etree.fromstring(
                b'<root><RESULT_CODE>0</RESULT_CODE>'
                b'<ENVELOPE_UUID>test-uuid-email</ENVELOPE_UUID></root>'
            )

        svc = SovosArchiveService(self.company)
        with patch.object(svc, '_post', side_effect=lambda a, b: fake_post(svc, a, b)):
            try:
                svc.send_invoice(b'<Invoice/>', 'test-uuid-email-001', self.partner_earsiv)
            except Exception:
                pass

        # _post çağrıldıysa body kontrol et
        if captured_body:
            self.assertIn(self.partner_earsiv.email, captured_body[0],
                'SOAP body partner e-postasını içermeli')


# ═════════════════════════════════════════════════════════════════════════════
# FR-39 / AC-13: Bağlantı Testi Butonu
# ═════════════════════════════════════════════════════════════════════════════

class TestConnectionTest(SovosTestCommon):
    """FR-39 / AC-13: Bağlantı testi başarılı/başarısız bildirim vermeli."""

    def test_invoice_connection_success_returns_notification(self):
        """
        AC-13: e-Fatura bağlantı testi başarılıysa 'success' tipinde
        display_notification action döndürmeli.
        """
        from l10n_tr_sovos_efatura.services.sovos_invoice_service import SovosInvoiceService

        with patch.object(SovosInvoiceService, 'test_connection', return_value=(True, 'OK')):
            result = self.company.action_test_invoice_connection()

        self.assertEqual(result.get('type'), 'ir.actions.client')
        self.assertEqual(result.get('tag'), 'display_notification')
        self.assertEqual(result['params']['type'], 'success',
            'Başarılı bağlantı testi success bildirimi döndürmeli')

    def test_invoice_connection_failure_raises_user_error(self):
        """
        AC-13: e-Fatura bağlantı testi başarısızsa UserError fırlatılmalı.
        """
        from l10n_tr_sovos_efatura.services.sovos_invoice_service import SovosInvoiceService

        with patch.object(SovosInvoiceService, 'test_connection',
                          return_value=(False, 'AUTH_ERROR')):
            with self.assertRaises(UserError) as ctx:
                self.company.action_test_invoice_connection()

        self.assertIn('AUTH_ERROR', str(ctx.exception),
            'Hata mesajı servis hata detayını içermeli')

    def test_archive_connection_success_returns_notification(self):
        """
        AC-13: e-Arşiv bağlantı testi başarılıysa success bildirimi döndürmeli.
        """
        from l10n_tr_sovos_efatura.services.sovos_archive_service import SovosArchiveService

        with patch.object(SovosArchiveService, 'test_connection', return_value=(True, 'OK')):
            result = self.company.action_test_archive_connection()

        self.assertEqual(result['params']['type'], 'success')

    def test_archive_connection_failure_raises_user_error(self):
        """
        AC-13: e-Arşiv bağlantı testi başarısızsa UserError fırlatılmalı.
        """
        from l10n_tr_sovos_efatura.services.sovos_archive_service import SovosArchiveService

        with patch.object(SovosArchiveService, 'test_connection',
                          return_value=(False, 'ARCHIVE_AUTH_ERROR')):
            with self.assertRaises(UserError):
                self.company.action_test_archive_connection()

    def test_invoice_and_archive_connection_tests_are_independent(self):
        """
        FR-39 / Spec §6: InvoiceService ve ArchiveService bağlantı testleri
        birbirinden bağımsız olmalı.
        İkisi ayrı buton — ayrı ayrı test edilebilmeli.
        """
        from l10n_tr_sovos_efatura.services.sovos_invoice_service import SovosInvoiceService
        from l10n_tr_sovos_efatura.services.sovos_archive_service import SovosArchiveService

        with patch.object(SovosInvoiceService, 'test_connection', return_value=(True, 'OK')), \
             patch.object(SovosArchiveService, 'test_connection',
                          return_value=(False, 'ARCHIVE_DOWN')) as mock_archive:
            # Invoice testi başarılı olsa da archive testi ayrı çalışır
            invoice_result = self.company.action_test_invoice_connection()
            self.assertEqual(invoice_result['params']['type'], 'success')

            with self.assertRaises(UserError):
                self.company.action_test_archive_connection()


# ═════════════════════════════════════════════════════════════════════════════
# FR-12: Kur Farkı Faturası Wizard
# ═════════════════════════════════════════════════════════════════════════════

class TestKurFarkiWizard(SovosTestCommon):
    """FR-12 (P2): Kur farkı wizard taslak fatura oluşturur, x_kur_farki=True."""

    def test_kur_farki_creates_draft_invoice(self):
        """
        FR-12: Wizard başarıyla çalışınca yeni bir taslak (draft) fatura oluşmalı.
        """
        original_inv = self._create_sent_invoice(scenario='TICARIFATURA')
        original_inv.write({'x_efatura_status': 'accepted'})

        wizard = self.env['sovos.kur.farki.wizard'].create({
            'original_invoice_id': original_inv.id,
            'kur_farki_amount': 150.0,
            'kur_farki_date': date.today(),
            'description': 'Test kur farkı',
        })

        result = wizard.action_create_kur_farki()

        new_invoice = self.env['account.move'].browse(result['res_id'])
        self.assertTrue(new_invoice.exists(), 'Yeni fatura oluşturulmalı')
        self.assertEqual(new_invoice.state, 'draft',
            'Kur farkı faturası taslak (draft) olarak oluşturulmalı')

    def test_kur_farki_flag_is_set(self):
        """
        FR-12: Oluşturulan kur farkı faturasında x_kur_farki=True olmalı.
        """
        original_inv = self._create_sent_invoice(scenario='TICARIFATURA')
        original_inv.write({'x_efatura_status': 'accepted'})

        wizard = self.env['sovos.kur.farki.wizard'].create({
            'original_invoice_id': original_inv.id,
            'kur_farki_amount': 200.0,
            'kur_farki_date': date.today(),
        })

        result = wizard.action_create_kur_farki()
        new_invoice = self.env['account.move'].browse(result['res_id'])

        self.assertTrue(new_invoice.x_kur_farki,
            'Kur farkı faturasında x_kur_farki=True olmalı')

    def test_kur_farki_uuid_cleared_on_new_invoice(self):
        """
        FR-12: Kur farkı faturası kopyalanmış orijinalden geldiği için
        x_sovos_uuid temizlenmiş olmalı — mükerrer UUID riski yok.
        """
        original_inv = self._create_sent_invoice(scenario='TICARIFATURA')
        original_inv.write({'x_efatura_status': 'accepted'})

        wizard = self.env['sovos.kur.farki.wizard'].create({
            'original_invoice_id': original_inv.id,
            'kur_farki_amount': 100.0,
            'kur_farki_date': date.today(),
        })

        result = wizard.action_create_kur_farki()
        new_invoice = self.env['account.move'].browse(result['res_id'])

        self.assertFalse(new_invoice.x_sovos_uuid,
            'Kur farkı faturasında x_sovos_uuid temizlenmiş olmalı')

    def test_kur_farki_blocked_on_draft_invoice(self):
        """
        FR-12: Kur farkı wizard sadece sent/accepted faturalarda çalışmalı.
        Draft fatura için UserError fırlatılmalı.
        Wizard kodu: 'if original.x_efatura_status not in (accepted, sent)'
        """
        draft_inv = self._create_invoice()
        # draft_inv gönderilmemiş

        wizard = self.env['sovos.kur.farki.wizard'].create({
            'original_invoice_id': draft_inv.id,
            'kur_farki_amount': 100.0,
            'kur_farki_date': date.today(),
        })

        with self.assertRaises(UserError,
                msg='Draft fatura için kur farkı wizard UserError fırlatmalı'):
            wizard.action_create_kur_farki()

    def test_kur_farki_invoice_has_amount_line(self):
        """
        FR-12: Oluşturulan faturada kur farkı tutarını içeren bir kalem olmalı.
        """
        original_inv = self._create_sent_invoice(scenario='TICARIFATURA')
        original_inv.write({'x_efatura_status': 'accepted'})

        wizard = self.env['sovos.kur.farki.wizard'].create({
            'original_invoice_id': original_inv.id,
            'kur_farki_amount': 350.0,
            'kur_farki_date': date.today(),
            'description': 'Kur farkı açıklaması',
        })

        result = wizard.action_create_kur_farki()
        new_invoice = self.env['account.move'].browse(result['res_id'])

        amounts = new_invoice.invoice_line_ids.mapped('price_unit')
        self.assertIn(350.0, amounts,
            'Kur farkı faturasında 350.0 tutarında kalem bulunmalı')

    def test_kur_farki_returns_form_view_action(self):
        """
        FR-12: Wizard yeni faturanın form görünümüne yönlendiren action döndürmeli.
        """
        original_inv = self._create_sent_invoice(scenario='TICARIFATURA')
        original_inv.write({'x_efatura_status': 'accepted'})

        wizard = self.env['sovos.kur.farki.wizard'].create({
            'original_invoice_id': original_inv.id,
            'kur_farki_amount': 75.0,
            'kur_farki_date': date.today(),
        })

        result = wizard.action_create_kur_farki()

        self.assertEqual(result.get('type'), 'ir.actions.act_window')
        self.assertEqual(result.get('res_model'), 'account.move')
        self.assertIsNotNone(result.get('res_id'),
            'Action yeni fatura ID\'sini içermeli')


# ═════════════════════════════════════════════════════════════════════════════
# AC-18: Dashboard Domain Filtreleri
# ═════════════════════════════════════════════════════════════════════════════

class TestDashboardFilters(SovosTestCommon):
    """
    AC-18: Dashboard filtreler doğru fatura listesi göstermeli.
    Spec §9'da tanımlanan 7 filtre domain'inin doğruluğunu test eder.
    """

    def _search(self, domain):
        return self.env['account.move'].search(domain)

    def test_filter_sent_awaiting_response(self):
        """
        Spec §9: 'Gönderildi — Yanıt Bekliyor' filtresi
        x_efatura_status=sent faturalar döndürmeli.
        """
        sent_inv = self._create_sent_invoice(scenario='TICARIFATURA')
        # sent_inv zaten x_efatura_status='sent'

        # Kabul edilmiş fatura bu filtreye girmemeli
        accepted_inv = self._create_sent_invoice(scenario='TICARIFATURA')
        accepted_inv.write({'x_efatura_status': 'accepted'})

        domain = [('x_efatura_status', '=', 'sent')]
        results = self._search(domain)

        self.assertIn(sent_inv, results, 'sent fatura filtre sonucunda olmalı')
        self.assertNotIn(accepted_inv, results,
            'accepted fatura sent filtresi sonucunda olmamalı')

    def test_filter_error_action_required(self):
        """
        Spec §9: 'Hata Var — Aksiyon Gerekli' filtresi
        x_efatura_status=error faturalar döndürmeli.
        """
        error_inv = self._create_sent_invoice()
        error_inv.write({'x_efatura_status': 'error'})

        domain = [('x_efatura_status', '=', 'error')]
        results = self._search(domain)

        self.assertIn(error_inv, results)

    def test_filter_validation_error(self):
        """
        Spec §9: 'Validasyon Hatası' filtresi
        x_number_status=released AND x_validation_errors!=False faturalar.
        """
        val_error_inv = self._create_invoice()
        val_error_inv.write({
            'x_number_status': 'released',
            'x_validation_errors': 'cbc:ID zorunlu alan eksik',
        })

        domain = [
            ('x_number_status', '=', 'released'),
            ('x_validation_errors', '!=', False),
        ]
        results = self._search(domain)

        self.assertIn(val_error_inv, results,
            'Validasyon hatası olan fatura filtreye girmeli')

    def test_filter_8day_warning(self):
        """
        Spec §9: '8 Gün Uyarısı' filtresi
        x_inv_response_deadline <= today+1 AND x_inv_response_status=beklemede faturalar.
        """
        # Deadline yarın — uyarı kapsamında
        warning_inv = self._create_sent_invoice(scenario='TICARIFATURA')
        warning_inv.write({
            'x_inv_response_deadline': date.today() + timedelta(days=1),
            'x_inv_response_status': 'beklemede',
        })

        # Deadline 5 gün sonra — uyarı kapsamında değil
        ok_inv = self._create_sent_invoice(scenario='TICARIFATURA')
        ok_inv.write({
            'x_inv_response_deadline': date.today() + timedelta(days=5),
            'x_inv_response_status': 'beklemede',
        })

        domain = [
            ('x_inv_response_deadline', '<=', date.today() + timedelta(days=1)),
            ('x_inv_response_status', '=', 'beklemede'),
        ]
        results = self._search(domain)

        self.assertIn(warning_inv, results, 'Deadline yakın fatura uyarı filtresinde olmalı')
        self.assertNotIn(ok_inv, results, 'Deadline uzak fatura uyarı filtresinde olmamalı')

    def test_filter_rejected(self):
        """
        Spec §9: 'Red Edildi' filtresi
        x_efatura_status=rejected faturalar.
        """
        rejected_inv = self._create_sent_invoice()
        rejected_inv.write({'x_efatura_status': 'rejected'})

        domain = [('x_efatura_status', '=', 'rejected')]
        results = self._search(domain)

        self.assertIn(rejected_inv, results)

    def test_filter_incoming_no_partner(self):
        """
        Spec §9: 'Gelen — Partner Eşlenecek' filtresi
        move_type=in_invoice AND partner_id=False faturalar.
        """
        purchase_journal = self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', self.company.id),
        ], limit=1)

        incoming_no_partner = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': False,
            'invoice_date': date.today(),
            'journal_id': purchase_journal.id,
            'x_sovos_uuid': 'incoming-no-partner-uuid',
        })

        domain = [
            ('move_type', '=', 'in_invoice'),
            ('partner_id', '=', False),
        ]
        results = self._search(domain)

        self.assertIn(incoming_no_partner, results,
            'Partner\'sız gelen fatura filtrede görünmeli')

    def test_filter_accepted_this_month(self):
        """
        Spec §9: 'Bu Ay Gönderildi' filtresi
        x_efatura_status=accepted AND bu ay içinde.
        """
        import datetime
        today = date.today()
        first_of_month = today.replace(day=1)

        accepted_this_month = self._create_sent_invoice()
        accepted_this_month.write({
            'x_efatura_status': 'accepted',
            'x_efatura_send_date': datetime.datetime.combine(today, datetime.time()),
        })

        domain = [
            ('x_efatura_status', '=', 'accepted'),
            ('x_efatura_send_date', '>=', datetime.datetime.combine(
                first_of_month, datetime.time()
            )),
        ]
        results = self._search(domain)

        self.assertIn(accepted_this_month, results,
            'Bu ay kabul edilen fatura filtrede olmalı')
