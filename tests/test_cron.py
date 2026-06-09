# -*- coding: utf-8 -*-
"""
Cron & Senkronizasyon Testleri — v6.1
Kod: models/sovos_sync.py

v6.1 YENİ:
  - cron_sync_earsiv_status() → ayrı e-Arşiv cron (GetInvoiceDocument)
  - _notify_admin() → mail.mail + Odoo message (mail.message)
  - _check_8day_for_company() → compute field bypass, tarih hesabı burada

Risk Seviyesi: ORTA
"""
from datetime import date, timedelta
from unittest.mock import patch, MagicMock, call

from odoo.exceptions import UserError

from .common import SovosTestCommon


class TestCronSync(SovosTestCommon):

    # ── Gelen fatura senkronizasyonu ──────────────────────────────────

    def test_incoming_invoice_created_with_partner(self):
        """
        Gelen fatura VKN eşleşirse partner dolu in_invoice oluşturulmalı.
        """
        sync = self.env['sovos.sync']
        mock_invoices = [{
            'uuid': 'inbound-uuid-0001',
            'sender_vkn': self.partner_efatura.vat,
            'invoice_date': '2026-06-01',
        }]

        with patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.get_inbound_list',
            return_value=mock_invoices,
        ):
            sync._sync_incoming_for_company(self.company)

        created = self.env['account.move'].search([
            ('x_sovos_uuid', '=', 'inbound-uuid-0001'),
            ('move_type', '=', 'in_invoice'),
        ])
        self.assertTrue(created)
        self.assertEqual(created.partner_id, self.partner_efatura)
        self.assertEqual(created.x_efatura_status, 'accepted')

    def test_incoming_invoice_created_without_partner(self):
        """
        VKN eşleşmezse partner_id=False, fatura yine oluşturulmalı.
        Muhasebeci eşleme yapana kadar draft kalır.
        """
        sync = self.env['sovos.sync']
        mock_invoices = [{
            'uuid': 'inbound-uuid-0002',
            'sender_vkn': '9999999999',  # Odoo'da yok
            'invoice_date': '2026-06-01',
        }]
        with patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.get_inbound_list',
            return_value=mock_invoices,
        ):
            sync._sync_incoming_for_company(self.company)

        created = self.env['account.move'].search([
            ('x_sovos_uuid', '=', 'inbound-uuid-0002'),
        ])
        self.assertTrue(created)
        self.assertFalse(created.partner_id,
            'Partner bulunamazsa partner_id=False olmalı — muhasebe fişi oluşmaz')

    def test_incoming_invoice_not_duplicated(self):
        """Aynı UUID ikinci kez gelirse yeni kayıt oluşturulmamalı."""
        sync = self.env['sovos.sync']
        existing_uuid = 'inbound-uuid-exist'
        self.env['account.move'].create({
            'move_type': 'in_invoice',
            'x_sovos_uuid': existing_uuid,
            'partner_id': self.partner_efatura.id,
            'journal_id': self.env['account.journal'].search([
                ('type', '=', 'purchase'), ('company_id', '=', self.company.id),
            ], limit=1).id,
        })

        mock_invoices = [{'uuid': existing_uuid, 'sender_vkn': '1111111111'}]
        with patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.get_inbound_list',
            return_value=mock_invoices,
        ):
            sync._sync_incoming_for_company(self.company)

        count = self.env['account.move'].search_count([('x_sovos_uuid', '=', existing_uuid)])
        self.assertEqual(count, 1, 'Mükerrer kayıt oluşturulmamalı')

    # ── e-Fatura durum takibi ─────────────────────────────────────────

    def test_efatura_status_cron_queries_sent_invoices(self):
        """
        e-Fatura cron → 'sent'/'sending' durumundaki efatura faturaları sorgulamalı.
        """
        inv = self._create_sent_invoice()  # x_efatura_type='efatura'

        with patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.get_envelope_status',
            return_value=(1300, 'Başarılı'),
        ) as mock_status:
            self.env['sovos.sync']._sync_efatura_status_for_company(self.company)

        mock_status.assert_called_once_with(inv.x_sovos_envelope_uuid)
        self.assertEqual(inv.x_efatura_status, 'accepted')

    def test_efatura_status_cron_skips_earsiv_invoices(self):
        """
        v6.1: e-Fatura cron e-Arşiv faturalarını sorgulamaz (ayrı cron).
        """
        inv = self._create_sent_invoice(partner=self.partner_earsiv, scenario='EARSIVFATURA')
        inv.write({'x_efatura_type': 'earsiv'})

        with patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.get_envelope_status',
        ) as mock_status:
            self.env['sovos.sync']._sync_efatura_status_for_company(self.company)

        mock_status.assert_not_called()

    # ── e-Arşiv ayrı cron — v6.1 YENİ ───────────────────────────────

    def test_earsiv_status_cron_queries_earsiv_invoices(self):
        """
        v6.1 YENİ: e-Arşiv cron → ArchiveService.get_invoice_status() çağrılmalı.
        """
        inv = self._create_sent_invoice(partner=self.partner_earsiv, scenario='EARSIVFATURA')
        inv.write({'x_efatura_type': 'earsiv'})

        with patch(
            'l10n_tr_sovos_efatura.services.sovos_archive_service'
            '.SovosArchiveService.get_invoice_status',
            return_value=(1300, 'Başarılı'),
        ) as mock_status:
            self.env['sovos.sync']._sync_earsiv_status_for_company(self.company)

        mock_status.assert_called_once_with(inv.x_sovos_uuid)
        self.assertEqual(inv.x_efatura_status, 'accepted')

    def test_earsiv_cron_skips_efatura_invoices(self):
        """e-Arşiv cron e-Fatura faturalarını sorgulamaz."""
        inv = self._create_sent_invoice()  # x_efatura_type='efatura'

        with patch(
            'l10n_tr_sovos_efatura.services.sovos_archive_service'
            '.SovosArchiveService.get_invoice_status',
        ) as mock_status:
            self.env['sovos.sync']._sync_earsiv_status_for_company(self.company)

        mock_status.assert_not_called()

    # ── Admin bildirimi — v6.1 güncellendi ───────────────────────────

    def test_notify_admin_creates_mail_message(self):
        """
        _notify_admin() → mail.message oluşturulmalı (Odoo bildirimi).
        """
        sync = self.env['sovos.sync']
        mail_msg_count_before = self.env['mail.message'].search_count([
            ('model', '=', 'res.company'),
            ('res_id', '=', self.company.id),
        ])
        sync._notify_admin(self.company, 'cron_test', 'Test hata mesajı')

        mail_msg_count_after = self.env['mail.message'].search_count([
            ('model', '=', 'res.company'),
            ('res_id', '=', self.company.id),
        ])
        self.assertGreater(mail_msg_count_after, mail_msg_count_before)

    def test_notify_admin_sends_email_when_admin_email_set(self):
        """
        v6.1 YENİ: x_sovos_admin_email doluysa mail.mail de oluşturulmalı.
        """
        self.company.x_sovos_admin_email = 'admin@test.com'
        sync = self.env['sovos.sync']

        with patch.object(
            self.env['mail.mail'].__class__, 'send', return_value=None
        ) as mock_send:
            mail_count_before = self.env['mail.mail'].search_count([
                ('email_to', '=', 'admin@test.com'),
            ])
            sync._notify_admin(self.company, 'test_task', 'Hata')
            mail_count_after = self.env['mail.mail'].search_count([
                ('email_to', '=', 'admin@test.com'),
            ])

        self.assertGreater(mail_count_after, mail_count_before,
            'Admin e-postası oluşturulmalı')

    def test_cron_continues_after_single_company_failure(self):
        """
        Bir şirket için cron başarısız olursa diğer şirketler etkilenmemeli.
        """
        company2 = self.env['res.company'].create({
            'name': 'Test Şirket 2',
            'x_sovos_invoice_user': 'user2',
        })

        sync = self.env['sovos.sync']

        call_order = []

        def failing_then_ok(company):
            call_order.append(company.id)
            if company.id == self.company.id:
                raise Exception('Şirket 1 hatası')

        with patch.object(sync, '_sync_incoming_for_company', side_effect=failing_then_ok), \
             patch.object(sync, '_notify_admin'):
            sync._cron_run_for_all_companies('cron_sync_incoming_invoices')

        self.assertIn(company2.id, call_order,
            'Şirket 1 başarısız olsa da Şirket 2 çalışmalı')

    # ── 8 gün uyarısı ────────────────────────────────────────────────

    def test_8day_warning_cron_posts_message_on_expiring_invoices(self):
        """
        Deadline yarın veya bugün olan TICARIFATURA'lara chatter mesajı eklenmeli.
        v6.1: store=False compute field bypass — tarih hesabı cron'da yapılıyor.
        """
        inv = self._create_sent_invoice(scenario='TICARIFATURA')
        inv.write({
            'x_inv_response_deadline': date.today(),  # bugün son gün
            'x_inv_response_status': 'beklemede',
        })

        msg_count_before = self.env['mail.message'].search_count([
            ('model', '=', 'account.move'),
            ('res_id', '=', inv.id),
        ])

        self.env['sovos.sync']._check_8day_for_company(self.company)

        msg_count_after = self.env['mail.message'].search_count([
            ('model', '=', 'account.move'),
            ('res_id', '=', inv.id),
        ])
        self.assertGreater(msg_count_after, msg_count_before)

    def test_8day_warning_cron_skips_already_responded(self):
        """
        Kabul/red almış faturalara uyarı mesajı eklenmemeli.
        """
        inv = self._create_sent_invoice(scenario='TICARIFATURA')
        inv.write({
            'x_inv_response_deadline': date.today(),
            'x_inv_response_status': 'kabul',  # zaten kabul
        })

        with patch.object(inv, 'message_post') as mock_post:
            self.env['sovos.sync']._check_8day_for_company(self.company)
        mock_post.assert_not_called()

    # ── VKN Cache cron ───────────────────────────────────────────────

    def test_vkn_cache_cron_refreshes_stale_partners(self):
        """
        31 günlük cache → _refresh_vkn_for_company() refresh_efatura_type() çağırmalı.
        """
        self.partner_efatura.write({
            'x_efatura_type_updated': date.today() - timedelta(days=31),
            'customer_rank': 1,
        })

        with patch(
            'l10n_tr_sovos_efatura.models.res_partner.ResPartner.refresh_efatura_type'
        ) as mock_refresh:
            self.env['sovos.sync']._refresh_vkn_for_company(self.company)

        mock_refresh.assert_called()

    def test_vkn_cache_cron_skips_fresh_partners(self):
        """
        10 günlük cache → cron'da yenileme yapılmamalı.
        """
        self.partner_efatura.write({
            'x_efatura_type_updated': date.today() - timedelta(days=10),
            'customer_rank': 1,
        })

        with patch(
            'l10n_tr_sovos_efatura.models.res_partner.ResPartner.refresh_efatura_type'
        ) as mock_refresh:
            self.env['sovos.sync']._refresh_vkn_for_company(self.company)

        mock_refresh.assert_not_called()
