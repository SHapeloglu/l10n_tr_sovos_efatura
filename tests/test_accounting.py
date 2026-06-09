# -*- coding: utf-8 -*-
"""
Muhasebe Fişi Testleri — TDHP Eşlemesi
Kod: Odoo'nun standart muhasebe motoru + modülün action_post() override'ı

BRD Kabul Kriterleri:
  AC-07 (P0 — Canlıya Çıkış Şartı):
    Satış muhasebe fişi TDHP 120/600/391 ile doğru oluşur.
  AC-08 (P0 — Canlıya Çıkış Şartı):
    Alış muhasebe fişi TDHP 320/190/gider ile doğru oluşur.

Spec §16 (TDHP Eşlemesi):
  Satış:
    120 Alıcılar         Borç   (invoice total)
    600 Yurt İçi Satış   Alacak (subtotal)
    391 Hesaplanan KDV   Alacak (tax amount)
  Alış:
    320 Satıcılar        Alacak (invoice total)
    190 İndirilecek KDV  Borç   (tax amount)
    153/740/7xx Gider    Borç   (subtotal)

Not: Odoo'da TDHP hesap kodları türe göre şöyle eşlenir:
  receivable    → 120 Alıcılar
  payable       → 320 Satıcılar
  tax           → 391 / 190
  income        → 600
  expense       → 153/740/7xx
Bu testler account_type üzerinden doğrulama yapar; sabit kod araması yapmaz.
"""
from unittest.mock import patch

from odoo.exceptions import UserError
from .common import SovosTestCommon


class TestSaleAccountingEntry(SovosTestCommon):
    """AC-07: Satış faturası muhasebe fişi — TDHP 120/600/391."""

    def _post_invoice_with_mocks(self, partner=None, **kwargs):
        """Satış faturasını mock'larla gönderir, fatura döner."""
        inv = self._create_invoice(partner=partner, **kwargs)
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            inv.action_post()
        return inv

    def test_sale_invoice_creates_journal_entry(self):
        """
        AC-07: Satış faturası onaylanınca muhasebe fişi (journal entry) oluşmalı.
        Fatura POSTED durumunda olmalı ve en az 2 muhasebe satırı içermeli.
        """
        inv = self._post_invoice_with_mocks()
        self.assertEqual(inv.state, 'posted',
            'Başarılı gönderim sonrası fatura POSTED olmalı')
        self.assertTrue(inv.line_ids,
            'POSTED faturada muhasebe satırları (line_ids) oluşmalı')
        self.assertGreaterEqual(len(inv.line_ids), 2,
            'En az borç + alacak satırı olmalı')

    def test_sale_invoice_has_receivable_line(self):
        """
        AC-07: Satış faturasında 'receivable' (Alıcılar / TDHP 120) tipinde
        borç satırı bulunmalı.
        """
        inv = self._post_invoice_with_mocks()
        receivable_lines = inv.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        )
        self.assertTrue(receivable_lines,
            'Satış faturasında Alıcılar (receivable) hesap satırı bulunmalı (TDHP 120)')

    def test_sale_invoice_receivable_is_debit(self):
        """
        AC-07: Alıcılar hesabı borç (debit) tarafında olmalı.
        """
        inv = self._post_invoice_with_mocks()
        receivable_line = inv.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        )[:1]
        self.assertGreater(receivable_line.debit, 0,
            'Alıcılar hesabı borç (debit) olmalı')
        self.assertEqual(receivable_line.credit, 0,
            'Alıcılar hesabı alacak (credit) sıfır olmalı')

    def test_sale_invoice_has_income_line(self):
        """
        AC-07: Satış faturasında gelir (income) hesap satırı bulunmalı (TDHP 600).
        """
        inv = self._post_invoice_with_mocks()
        income_lines = inv.line_ids.filtered(
            lambda l: l.account_id.account_type == 'income'
        )
        self.assertTrue(income_lines,
            'Satış faturasında Yurt İçi Satışlar (income) hesap satırı bulunmalı (TDHP 600)')

    def test_sale_invoice_income_is_credit(self):
        """
        AC-07: Satış gelir hesabı alacak (credit) tarafında olmalı.
        """
        inv = self._post_invoice_with_mocks()
        income_line = inv.line_ids.filtered(
            lambda l: l.account_id.account_type == 'income'
        )[:1]
        self.assertGreater(income_line.credit, 0,
            'Satış gelir hesabı alacak (credit) olmalı')

    def test_sale_invoice_journal_entry_is_balanced(self):
        """
        AC-07: Muhasebe fişi dengeli olmalı — toplam borç = toplam alacak.
        """
        inv = self._post_invoice_with_mocks()
        total_debit = sum(inv.line_ids.mapped('debit'))
        total_credit = sum(inv.line_ids.mapped('credit'))
        self.assertAlmostEqual(total_debit, total_credit, places=2,
            msg='Muhasebe fişi dengeli olmalı: toplam borç = toplam alacak')

    def test_sale_invoice_receivable_amount_equals_invoice_total(self):
        """
        AC-07: Alıcılar borç tutarı fatura toplamına eşit olmalı.
        """
        inv = self._post_invoice_with_mocks()
        receivable_line = inv.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        )[:1]
        self.assertAlmostEqual(
            receivable_line.debit, inv.amount_total, places=2,
            msg='Alıcılar borç tutarı fatura toplam tutarına eşit olmalı'
        )

    def test_sale_invoice_with_tax_has_tax_line(self):
        """
        AC-07: Vergi içeren satış faturasında 'tax' tipinde muhasebe satırı
        (Hesaplanan KDV / TDHP 391) bulunmalı.
        """
        tax = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('company_id', '=', self.company.id),
        ], limit=1)

        if not tax:
            self.skipTest('Satış vergisi tanımlı değil — vergi satırı testi atlandı')

        inv = self._create_invoice()
        inv.invoice_line_ids[0].write({'tax_ids': [(4, tax.id)]})

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            inv.action_post()

        tax_lines = inv.line_ids.filtered(
            lambda l: l.account_id.account_type in ('liability_current', 'tax')
                      or l.tax_line_id
        )
        self.assertTrue(tax_lines,
            'Vergi içeren satış faturasında KDV hesap satırı bulunmalı (TDHP 391)')

    def test_sale_invoice_partner_set_on_receivable_line(self):
        """
        AC-07: Alıcılar satırında partner_id dolu olmalı — muhasebe takibi için zorunlu.
        """
        inv = self._post_invoice_with_mocks()
        receivable_line = inv.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        )[:1]
        self.assertEqual(receivable_line.partner_id, self.partner_efatura,
            'Alıcılar satırında doğru partner_id bulunmalı')


class TestPurchaseAccountingEntry(SovosTestCommon):
    """AC-08: Alış faturası muhasebe fişi — TDHP 320/190/gider."""

    def _create_purchase_invoice(self, **kwargs):
        """Alış faturası oluşturur."""
        account_expense = self.env['account.account'].search([
            ('account_type', 'in', ('expense', 'expense_depreciation')),
            ('company_id', '=', self.company.id),
        ], limit=1)

        if not account_expense:
            account_expense = self.account_income  # fallback

        purchase_journal = self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', self.company.id),
        ], limit=1)

        vals = {
            'move_type': 'in_invoice',
            'partner_id': self.partner_efatura.id,
            'invoice_date': __import__('datetime').date.today(),
            'journal_id': purchase_journal.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Alış Kalemi',
                'quantity': 1,
                'price_unit': 500.0,
                'account_id': account_expense.id,
            })],
        }
        vals.update(kwargs)
        return self.env['account.move'].create(vals)

    def test_purchase_invoice_creates_journal_entry(self):
        """
        AC-08: Alış faturası onaylanınca muhasebe fişi oluşmalı.
        Alış faturaları e-Fatura akışına girmez — Odoo standart action_post() çalışır.
        """
        inv = self._create_purchase_invoice()
        inv.action_post()

        self.assertEqual(inv.state, 'posted',
            'Alış faturası POSTED olmalı')
        self.assertTrue(inv.line_ids,
            'Alış faturasında muhasebe satırları oluşmalı')
        self.assertGreaterEqual(len(inv.line_ids), 2)

    def test_purchase_invoice_has_payable_line(self):
        """
        AC-08: Alış faturasında 'payable' (Satıcılar / TDHP 320) tipinde
        alacak satırı bulunmalı.
        """
        inv = self._create_purchase_invoice()
        inv.action_post()

        payable_lines = inv.line_ids.filtered(
            lambda l: l.account_id.account_type == 'liability_payable'
        )
        self.assertTrue(payable_lines,
            'Alış faturasında Satıcılar (payable) hesap satırı bulunmalı (TDHP 320)')

    def test_purchase_invoice_payable_is_credit(self):
        """
        AC-08: Satıcılar hesabı alacak (credit) tarafında olmalı.
        """
        inv = self._create_purchase_invoice()
        inv.action_post()

        payable_line = inv.line_ids.filtered(
            lambda l: l.account_id.account_type == 'liability_payable'
        )[:1]
        self.assertGreater(payable_line.credit, 0,
            'Satıcılar hesabı alacak (credit) olmalı')

    def test_purchase_invoice_has_expense_line(self):
        """
        AC-08: Alış faturasında gider/mal hesabı (expense) satırı bulunmalı
        (TDHP 153/740/7xx).
        """
        inv = self._create_purchase_invoice()
        inv.action_post()

        expense_lines = inv.line_ids.filtered(
            lambda l: l.account_id.account_type in ('expense', 'expense_depreciation')
        )
        self.assertTrue(expense_lines,
            'Alış faturasında gider hesabı satırı bulunmalı (TDHP 153/740/7xx)')

    def test_purchase_invoice_expense_is_debit(self):
        """
        AC-08: Gider hesabı borç (debit) tarafında olmalı.
        """
        inv = self._create_purchase_invoice()
        inv.action_post()

        expense_line = inv.line_ids.filtered(
            lambda l: l.account_id.account_type in ('expense', 'expense_depreciation')
        )[:1]
        self.assertGreater(expense_line.debit, 0,
            'Gider hesabı borç (debit) olmalı')

    def test_purchase_invoice_journal_entry_is_balanced(self):
        """
        AC-08: Alış faturası muhasebe fişi dengeli olmalı.
        """
        inv = self._create_purchase_invoice()
        inv.action_post()

        total_debit = sum(inv.line_ids.mapped('debit'))
        total_credit = sum(inv.line_ids.mapped('credit'))
        self.assertAlmostEqual(total_debit, total_credit, places=2,
            msg='Alış muhasebe fişi dengeli olmalı: toplam borç = toplam alacak')

    def test_purchase_invoice_payable_amount_equals_total(self):
        """
        AC-08: Satıcılar alacak tutarı fatura toplam tutarına eşit olmalı.
        """
        inv = self._create_purchase_invoice()
        inv.action_post()

        payable_line = inv.line_ids.filtered(
            lambda l: l.account_id.account_type == 'liability_payable'
        )[:1]
        self.assertAlmostEqual(
            payable_line.credit, inv.amount_total, places=2,
            msg='Satıcılar alacak tutarı fatura toplam tutarına eşit olmalı'
        )

    def test_purchase_invoice_with_tax_has_deductible_vat_line(self):
        """
        AC-08: Vergi içeren alış faturasında İndirilecek KDV (TDHP 190)
        satırı bulunmalı.
        """
        tax = self.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('company_id', '=', self.company.id),
        ], limit=1)

        if not tax:
            self.skipTest('Alış vergisi tanımlı değil — KDV testi atlandı')

        account_expense = self.env['account.account'].search([
            ('account_type', 'in', ('expense', 'expense_depreciation')),
            ('company_id', '=', self.company.id),
        ], limit=1)

        purchase_journal = self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', self.company.id),
        ], limit=1)

        inv = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner_efatura.id,
            'invoice_date': __import__('datetime').date.today(),
            'journal_id': purchase_journal.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Vergi İçeren Alış',
                'quantity': 1,
                'price_unit': 500.0,
                'account_id': account_expense.id if account_expense else self.account_income.id,
                'tax_ids': [(4, tax.id)],
            })],
        })
        inv.action_post()

        tax_lines = inv.line_ids.filtered(lambda l: l.tax_line_id)
        self.assertTrue(tax_lines,
            'Vergi içeren alış faturasında İndirilecek KDV satırı bulunmalı (TDHP 190)')

    def test_purchase_invoice_bypasses_efatura_flow(self):
        """
        AC-08: Alış faturaları (in_invoice) e-Fatura akışına girmemeli.
        Modülün action_post() override'ı sadece out_invoice için çalışmalı.
        """
        inv = self._create_purchase_invoice()

        # e-Fatura servislerinin çağrılmadığını doğrula
        with patch('l10n_tr_sovos_efatura.services.sovos_invoice_service'
                   '.SovosInvoiceService.send_ubl') as mock_send:
            inv.action_post()
            mock_send.assert_not_called()

        self.assertEqual(inv.state, 'posted')

    def test_incoming_invoice_from_cron_accounting_entry(self):
        """
        AC-08: Cron ile alınan gelen fatura (in_invoice) partner eşlendikten
        sonra action_post() ile muhasebe fişi oluşturulabilmeli.
        Spec §16.2: 'Kullanıcı partner eşler → action_post() → muhasebe fişi o an oluşur.'
        """
        account_expense = self.env['account.account'].search([
            ('account_type', 'in', ('expense', 'expense_depreciation')),
            ('company_id', '=', self.company.id),
        ], limit=1)

        purchase_journal = self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', self.company.id),
        ], limit=1)

        # Cron tarafından oluşturulmuş, partner'sız taslak fatura simüle et
        incoming = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': False,  # cron partner bulamadı
            'invoice_date': __import__('datetime').date.today(),
            'journal_id': purchase_journal.id,
            'x_sovos_uuid': 'incoming-uuid-test-001',
            'x_efatura_status': 'draft',
            'invoice_line_ids': [(0, 0, {
                'name': 'Gelen Fatura Kalemi',
                'quantity': 1,
                'price_unit': 200.0,
                'account_id': account_expense.id if account_expense else self.account_income.id,
            })],
        })

        # Fişin oluşmadığını doğrula (partner yok)
        self.assertFalse(incoming.partner_id)

        # Kullanıcı partner eşler
        incoming.partner_id = self.partner_efatura

        # action_post() → muhasebe fişi oluşur
        incoming.action_post()

        self.assertEqual(incoming.state, 'posted')
        self.assertTrue(incoming.line_ids,
            'Partner eşlendikten sonra muhasebe fişi oluşmalı')

        payable_lines = incoming.line_ids.filtered(
            lambda l: l.account_id.account_type == 'liability_payable'
        )
        self.assertTrue(payable_lines,
            'Gelen faturada Satıcılar satırı bulunmalı')
