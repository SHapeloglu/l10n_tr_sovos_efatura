# -*- coding: utf-8 -*-
"""
Atomik Numara Rezervasyonu Testleri — v6.1
Kod: models/account_move.py — _reserve_invoice_number(), _release_number()

v6.1 Değişiklikler:
  - _release_number() artık parametresiz (self üzerinden çalışır)
  - super().action_post() validasyon SONRASI, Sovos ÖNCE çağrılıyor
  - action_post() tek super() çağrısı → çift post riski giderildi

Risk Seviyesi: KRİTİK
"""
from unittest.mock import patch

from odoo.exceptions import UserError

from .common import SovosTestCommon


class TestAtomicNumber(SovosTestCommon):

    # ── Başarılı akış ─────────────────────────────────────────────────

    def test_number_confirmed_on_successful_send(self):
        """
        Başarılı gönderimde x_number_status=confirmed, x_reserved_number dolu,
        fatura name = rezerve numara, UUID kayıtlı.
        """
        inv = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            inv.action_post()

        self.assertEqual(inv.x_number_status, 'confirmed')
        self.assertTrue(inv.x_reserved_number)
        self.assertEqual(inv.name, inv.x_reserved_number)
        self.assertTrue(inv.x_sovos_uuid)
        self.assertEqual(inv.x_efatura_status, 'sent')
        self.assertEqual(inv.state, 'posted')

    def test_envelope_uuid_saved_from_sovos(self):
        """
        Sovos'tan dönen envelope UUID x_sovos_envelope_uuid'e kaydedilmeli.
        """
        inv = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():  # 'mock-envelope-uuid' döner
            inv.action_post()
        self.assertEqual(inv.x_sovos_envelope_uuid, 'mock-envelope-uuid')

    def test_invoice_state_is_posted_after_success(self):
        """
        v6.1: super().action_post() validasyon sonrası çağrılıyor.
        Sovos başarılıysa state=posted olmalı.
        """
        inv = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            inv.action_post()
        self.assertEqual(inv.state, 'posted')

    # ── UBL üretim hatası → numara serbest ────────────────────────────

    def test_number_released_on_ubl_build_failure(self):
        """
        UblBuilder.build() exception fırlatırsa numara serbest bırakılmalı,
        fatura state=draft kalmalı (super() henüz çağrılmamış).
        """
        inv = self._create_invoice()
        with patch(
            'l10n_tr_sovos_efatura.services.ubl_builder.UblBuilder.build',
            side_effect=Exception('lxml serialize hatası'),
        ):
            with self.assertRaises(UserError):
                inv.action_post()

        self.assertEqual(inv.x_number_status, 'released')
        self.assertEqual(inv.x_efatura_status, 'error')
        self.assertEqual(inv.state, 'draft',
            'UBL üretim hatasında fatura draft kalmalıydı')

    # ── XSD hatası → numara serbest ───────────────────────────────────

    def test_number_released_on_xsd_failure(self):
        """
        XSD validasyon hatasında numara serbest, fatura draft, x_validation_errors dolu.
        v6.1: super().action_post() daha sonra çağrılıyor → state draft kalır.
        """
        inv = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_xsd_fail(['cbc:ID zorunlu']):
            with self.assertRaises(UserError):
                inv.action_post()

        self.assertEqual(inv.x_number_status, 'released')
        self.assertEqual(inv.x_efatura_status, 'error')
        self.assertEqual(inv.state, 'draft')
        self.assertIn('cbc:ID', inv.x_validation_errors)

    def test_number_released_on_schematron_failure(self):
        """Schematron hatasında numara serbest, fatura draft."""
        inv = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_schematron_fail(['BR-01: Tutar tutarsız']):
            with self.assertRaises(UserError):
                inv.action_post()

        self.assertEqual(inv.x_number_status, 'released')
        self.assertEqual(inv.state, 'draft')
        self.assertIn('BR-01', inv.x_validation_errors)

    def test_number_released_on_xml_parse_failure(self):
        """
        v6.1 YENİ: XML_PARSE katmanı hatasında numara serbest.
        """
        inv = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_parse_fail():
            with self.assertRaises(UserError) as cm:
                inv.action_post()

        self.assertEqual(inv.x_number_status, 'released')
        self.assertIn('XML_PARSE', str(cm.exception))

    # ── Sovos hatası → numara serbest + draft'a dön ───────────────────

    def test_number_released_on_sovos_failure(self):
        """
        Sovos erişilemez: numara serbest, button_draft() çağrılır.
        v6.1: super().action_post() Sovos'tan ÖNCE çağrılmış → fatura POSTED,
        ardından button_draft() ile draft'a dönmeli.
        """
        inv = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_failure('Zaman aşımı (60s)'):
            with self.assertRaises(UserError):
                inv.action_post()

        self.assertEqual(inv.x_number_status, 'released')
        self.assertEqual(inv.x_efatura_status, 'error')
        self.assertEqual(inv.state, 'draft',
            'Sovos hatasında button_draft() faturayı draft\'a döndürmeliydi')

    def test_number_released_on_rate_limit(self):
        """HTTP 429 rate limit hatasında numara serbest."""
        inv = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_failure('RATE_LIMIT_429'):
            with self.assertRaises(UserError):
                inv.action_post()
        self.assertEqual(inv.x_number_status, 'released')

    # ── Ön koşul kontrolleri ──────────────────────────────────────────

    def test_missing_sequence_raises_user_error(self):
        self.company.x_invoice_sequence_id = False
        inv = self._create_invoice()
        with self.assertRaises(UserError) as cm:
            inv.action_post()
        self.assertIn('numara serisi', str(cm.exception).lower())

    def test_missing_company_vkn_raises_user_error(self):
        self.company.x_sovos_sender_vkn = False
        inv = self._create_invoice()
        with self.assertRaises(UserError) as cm:
            inv.action_post()
        self.assertIn('VKN', str(cm.exception))

    def test_missing_partner_vkn_raises_user_error(self):
        self.partner_efatura.vat = False
        inv = self._create_invoice()
        with self.assertRaises(UserError) as cm:
            inv.action_post()
        self.assertIn('VKN', str(cm.exception))

    def test_missing_invoice_date_raises_user_error(self):
        inv = self._create_invoice(invoice_date=False)
        with self.assertRaises(UserError) as cm:
            inv.action_post()
        self.assertIn('tarih', str(cm.exception).lower())

    def test_missing_sovos_credentials_raises_user_error(self):
        self.company.x_sovos_invoice_user = False
        inv = self._create_invoice()
        with self.assertRaises(UserError) as cm:
            inv.action_post()
        self.assertIn('kullanıcı', str(cm.exception).lower())

    # ── Non-e-fatura hareketler etkilenmemeli ─────────────────────────

    def test_purchase_invoice_bypasses_efatura(self):
        """
        Alış faturası (in_invoice) e-Fatura akışına girmemeli.
        v6.1: action_post() filtered → other_moves super()'a gidiyor.
        """
        purchase_journal = self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', self.company.id),
        ], limit=1)
        inv = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner_efatura.id,
            'invoice_date': '2026-06-01',
            'journal_id': purchase_journal.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Alış Kalemi',
                'quantity': 1,
                'price_unit': 500.0,
                'account_id': self.account_income.id,
            })],
        })
        inv.action_post()
        self.assertEqual(inv.state, 'posted')
        self.assertFalse(inv.x_sovos_uuid,
            'Alış faturasında x_sovos_uuid boş olmalı')

    def test_no_double_post_on_mixed_selection(self):
        """
        v6.1 DÜZELTİLDİ: Karma seçimde (efatura + diğer) çift post riski giderildi.
        Her hareket tam olarak bir kez post edilmeli.
        """
        efatura_inv = self._create_invoice(partner=self.partner_efatura)
        misc_move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.env['account.journal'].search([
                ('type', '=', 'general'),
                ('company_id', '=', self.company.id),
            ], limit=1).id,
        })
        combo = efatura_inv | misc_move

        post_call_count = {'efatura': 0}

        original_post = type(efatura_inv)._efatura_post_single

        def counting_post(self_inv):
            post_call_count['efatura'] += 1
            return original_post(self_inv)

        with patch.object(type(efatura_inv), '_efatura_post_single', counting_post), \
             self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            combo.action_post()

        self.assertEqual(post_call_count['efatura'], 1,
            'e-Fatura tam olarak bir kez post edilmeli (çift post yok)')
