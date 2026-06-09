# -*- coding: utf-8 -*-
"""
Ortak test altyapısı — tüm test sınıfları bu base'den miras alır.
v6.1 güncel: _release_number() parametresiz, super().action_post() sırası değişti,
saxonche/UblValidator yeni imza, e-Arşiv ayrı cron.
"""
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from odoo.tests.common import TransactionCase


class SovosTestCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def setUp(self):
        super().setUp()

        # ── Şirket ──────────────────────────────────────────────────────
        self.company = self.env.company
        self.company.write({
            'vat': '1234567890',
            'x_sovos_invoice_user': 'test_invoice_user',
            'x_sovos_invoice_pass': 'test_invoice_pass',
            'x_sovos_archive_user': 'test_archive_user',
            'x_sovos_archive_pass': 'test_archive_pass',
            'x_sovos_sender_vkn': '1234567890',
            'x_sovos_identifier': 'GB1234567890',
            'x_sovos_template_id': 'TMPL001',
            'x_sovos_test_mode': True,
            'x_sovos_admin_email': 'admin@test.com',
        })

        # ── Numara serisi ────────────────────────────────────────────────
        self.invoice_sequence = self.env['ir.sequence'].create({
            'name': 'Test e-Fatura Serisi',
            'code': 'test.efatura',
            'prefix': 'TST%(year)s',
            'padding': 9,
            'number_increment': 1,
            'number_next': 1,
            'company_id': self.company.id,
        })
        self.company.x_invoice_sequence_id = self.invoice_sequence

        # ── e-Fatura müşterisi ───────────────────────────────────────────
        self.partner_efatura = self.env['res.partner'].create({
            'name': 'Test Ticaret A.Ş.',
            'vat': '9876543210',
            'email': 'test@testticaret.com',
            'x_efatura_type': 'efatura',
            'x_default_scenario': 'TICARIFATURA',
            'x_efatura_type_updated': date.today(),
            'x_vergi_dairesi': 'Büyük Mükellefler',
            'country_id': self.env.ref('base.tr').id,
        })

        # ── e-Arşiv müşterisi ────────────────────────────────────────────
        self.partner_earsiv = self.env['res.partner'].create({
            'name': 'Bireysel Müşteri',
            'vat': '12345678901',
            'email': 'bireysel@gmail.com',
            'x_efatura_type': 'earsiv',
            'x_default_scenario': 'EARSIVFATURA',
            'x_efatura_type_updated': date.today(),
            'country_id': self.env.ref('base.tr').id,
        })

        # ── Cache boş müşteri ────────────────────────────────────────────
        self.partner_no_cache = self.env['res.partner'].create({
            'name': 'Yeni Müşteri Ltd.',
            'vat': '5555555555',
            'email': 'yeni@musteri.com',
            'x_efatura_type': False,
            'x_efatura_type_updated': False,
            'country_id': self.env.ref('base.tr').id,
        })

        # ── Test ürünü ───────────────────────────────────────────────────
        self.product = self.env['product.product'].create({
            'name': 'Test Ürünü',
            'type': 'service',
            'list_price': 1000.0,
        })

        self.account_income = self.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_id', '=', self.company.id),
        ], limit=1)

        self.sale_journal = self.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', self.company.id),
        ], limit=1)

    # ── Factory Metodları ─────────────────────────────────────────────

    def _create_invoice(self, partner=None, lines=None, **kwargs):
        if partner is None:
            partner = self.partner_efatura
        if lines is None:
            lines = [(1, 1000.0, self.account_income)]
        line_vals = [(0, 0, {
            'name': 'Test Kalemi',
            'quantity': qty,
            'price_unit': price,
            'account_id': account.id,
        }) for qty, price, account in lines]
        vals = {
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_date': date.today(),
            'journal_id': self.sale_journal.id,
            'invoice_line_ids': line_vals,
        }
        vals.update(kwargs)
        return self.env['account.move'].create(vals)

    def _create_sent_invoice(self, partner=None, scenario='TICARIFATURA', **kwargs):
        """DB'ye direkt yazılmış sent fatura — Sovos çağrısı olmaz."""
        if partner is None:
            partner = self.partner_efatura
        inv = self._create_invoice(partner=partner, **kwargs)
        inv.write({
            'state': 'posted',
            'name': 'TST2026000000001',
            'x_sovos_uuid': 'test-uuid-1234-5678-abcd-ef0123456789',
            'x_sovos_envelope_uuid': 'env-uuid-1234-5678-abcd-ef0123456789',
            'x_efatura_type': partner.x_efatura_type if partner else 'efatura',
            'x_efatura_scenario': scenario,
            'x_efatura_status': 'sent',
            'x_efatura_send_date': '2026-06-01 10:00:00',
            'x_number_status': 'confirmed',
            'x_reserved_number': 'TST2026000000001',
        })
        if scenario == 'TICARIFATURA':
            inv.write({
                'x_inv_response_status': 'beklemede',
                'x_inv_response_deadline': date.today() + timedelta(days=8),
            })
        return inv

    # ── Mock Yardımcıları ─────────────────────────────────────────────
    # v6.1: UblValidator bir sınıf instance'ı — patch yolu güncellendi

    def _mock_ubl_builder(self):
        dummy_xml = b'<?xml version="1.0" encoding="UTF-8"?><Invoice>TEST</Invoice>'
        return patch(
            'l10n_tr_sovos_efatura.services.ubl_builder.UblBuilder.build',
            return_value=dummy_xml,
        )

    def _mock_validator_valid(self):
        return patch(
            'l10n_tr_sovos_efatura.services.ubl_validator.UblValidator.validate',
            return_value=(True, None, []),
        )

    def _mock_validator_xsd_fail(self, errors=None):
        return patch(
            'l10n_tr_sovos_efatura.services.ubl_validator.UblValidator.validate',
            return_value=(False, 'XSD', errors or ['cbc:ID zorunlu alan eksik']),
        )

    def _mock_validator_schematron_fail(self, errors=None):
        return patch(
            'l10n_tr_sovos_efatura.services.ubl_validator.UblValidator.validate',
            return_value=(False, 'SCHEMATRON', errors or ['BR-01: Fatura numarası zorunlu']),
        )

    def _mock_validator_parse_fail(self):
        """v6.1 yeni: XML_PARSE katmanı."""
        return patch(
            'l10n_tr_sovos_efatura.services.ubl_validator.UblValidator.validate',
            return_value=(False, 'XML_PARSE', ['XML sözdizim hatası satır 1']),
        )

    def _mock_sovos_invoice_success(self):
        return patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.send_ubl',
            return_value='mock-envelope-uuid',
        )

    def _mock_sovos_archive_success(self):
        return patch(
            'l10n_tr_sovos_efatura.services.sovos_archive_service'
            '.SovosArchiveService.send_invoice',
            return_value='mock-archive-uuid',
        )

    def _mock_sovos_failure(self, msg='Sovos bağlantı hatası'):
        return patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.send_ubl',
            side_effect=Exception(msg),
        )

    def _mock_vkn_check(self, is_registered=True):
        return patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.check_vkn_registered',
            return_value=is_registered,
        )

    def _mock_vkn_check_failure(self):
        return patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.check_vkn_registered',
            side_effect=Exception('Sovos bağlantı hatası'),
        )
