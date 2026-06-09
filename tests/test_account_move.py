# -*- coding: utf-8 -*-
"""
Fatura Gönderimi & Toplu Gönderim Testleri — v6.1
Kod: models/account_move.py — _efatura_post_single(), action_send_efatura_bulk()

v6.1 Değişiklikler:
  - action_send_efatura_bulk() → POSTED + henüz gönderilmemiş filtresi
    (eski: sadece draft — yeni spec: POSTED ama x_efatura_status in ('draft', False))
  - 'validasyon' string arama kırılgan bug devam ediyor
  - e-Arşiv ayrı cron

Risk Seviyesi: YÜKSEK
"""
import time
from datetime import date
from unittest.mock import patch, MagicMock

from odoo.exceptions import UserError

from .common import SovosTestCommon


class TestEFaturaPost(SovosTestCommon):

    # ── Senaryo yönlendirme ───────────────────────────────────────────

    def test_efatura_partner_uses_invoice_service(self):
        """GİB kayıtlı müşteri → InvoiceService.send_ubl() çağrılmalı."""
        inv = self._create_invoice(partner=self.partner_efatura)
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success() as mock_send:
            inv.action_post()

        mock_send.assert_called_once()
        self.assertEqual(inv.x_efatura_type, 'efatura')
        self.assertEqual(inv.x_efatura_status, 'sent')
        self.assertEqual(inv.state, 'posted')

    def test_earsiv_partner_uses_archive_service(self):
        """GİB kayıtsız müşteri → ArchiveService.send_invoice() çağrılmalı."""
        inv = self._create_invoice(partner=self.partner_earsiv)
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_archive_success() as mock_send:
            inv.action_post()

        mock_send.assert_called_once()
        self.assertEqual(inv.x_efatura_type, 'earsiv')
        self.assertEqual(inv.x_efatura_status, 'sent')

    def test_earsiv_ticarifatura_scenario_raises_user_error(self):
        """
        e-Arşiv alıcısına TICARIFATURA gönderilmek istenirse UserError.
        Spec §1.2: kullanıcı senaryo değiştirmedikçe bloke.
        """
        self.partner_earsiv.x_default_scenario = 'TICARIFATURA'
        inv = self._create_invoice(partner=self.partner_earsiv)
        with self.assertRaises(UserError) as cm:
            inv.action_post()
        self.assertIn('GİB e-Fatura sistemine kayıtlı değil', str(cm.exception))

    def test_earsiv_with_earsivfatura_scenario_succeeds(self):
        """e-Arşiv alıcısına EARSIVFATURA senaryosu → başarılı."""
        self.partner_earsiv.x_default_scenario = 'EARSIVFATURA'
        inv = self._create_invoice(partner=self.partner_earsiv)
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_archive_success():
            inv.action_post()
        self.assertEqual(inv.x_efatura_status, 'sent')

    def test_ticarifatura_sets_response_fields(self):
        """TICARIFATURA → x_inv_response_status='beklemede', deadline=bugün+8."""
        inv = self._create_invoice(partner=self.partner_efatura)
        inv.x_efatura_scenario = 'TICARIFATURA'
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            inv.action_post()

        self.assertEqual(inv.x_inv_response_status, 'beklemede')
        self.assertEqual(
            inv.x_inv_response_deadline,
            date.today() + __import__('datetime').timedelta(days=8)
        )

    def test_earsiv_does_not_set_response_deadline(self):
        """e-Arşiv → 8 günlük yanıt süresi set edilmemeli."""
        inv = self._create_invoice(partner=self.partner_earsiv)
        self.partner_earsiv.x_default_scenario = 'EARSIVFATURA'
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_archive_success():
            inv.action_post()
        self.assertFalse(inv.x_inv_response_deadline)

    def test_unique_uuids_for_each_invoice(self):
        """Her fatura için farklı UUID üretilmeli."""
        inv1 = self._create_invoice()
        inv2 = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            inv1.action_post()
            inv2.action_post()

        self.assertNotEqual(inv1.x_sovos_uuid, inv2.x_sovos_uuid)
        self.assertTrue(inv1.x_sovos_uuid)
        self.assertTrue(inv2.x_sovos_uuid)

    def test_efatura_status_is_sending_during_send(self):
        """
        Sovos çağrısı sırasında x_efatura_status='sending' olmalı.
        Uzun süren gönderimde kullanıcı 'Gönderiliyor' görür.
        """
        inv = self._create_invoice()
        status_during_send = []

        def capture_status(*args, **kwargs):
            status_during_send.append(inv.x_efatura_status)
            return 'mock-envelope-uuid'

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             patch(
                 'l10n_tr_sovos_efatura.services.sovos_invoice_service'
                 '.SovosInvoiceService.send_ubl',
                 side_effect=capture_status,
             ):
            inv.action_post()

        self.assertEqual(status_during_send[0], 'sending')

    # ── Önizleme ─────────────────────────────────────────────────────

    def test_preview_returns_act_url(self):
        """Önizleme ir.actions.act_url dönmeli."""
        inv = self._create_invoice()
        inv.write({'state': 'posted', 'name': 'TST2026000000001'})

        with self._mock_ubl_builder(), self._mock_validator_valid():
            result = inv.action_preview_efatura()

        self.assertEqual(result['type'], 'ir.actions.act_url')

    def test_preview_shows_validation_error_in_html(self):
        """Validasyon hatası varsa önizlemede HTML içinde gösterilmeli."""
        inv = self._create_invoice()
        inv.write({'state': 'posted', 'name': 'TST2026000000001'})

        with self._mock_ubl_builder(), \
             self._mock_validator_xsd_fail(['Test XSD hatası']):
            result = inv.action_preview_efatura()

        self.assertIn('Validasyon Hatası', result['url'])
        self.assertIn('XSD', result['url'])

    def test_preview_does_not_send_to_sovos(self):
        """Önizleme Sovos'a gönderim yapmamalı."""
        inv = self._create_invoice()
        inv.write({'state': 'posted', 'name': 'TST2026000000001'})

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success() as mock_send:
            inv.action_preview_efatura()

        mock_send.assert_not_called()


class TestBulkSend(SovosTestCommon):

    # ── Başarılı toplu gönderim ───────────────────────────────────────

    def test_bulk_sends_all_draft_invoices(self):
        """3 draft fatura → 3'ü de sent olmalı."""
        invs = self.env['account.move']
        for _ in range(3):
            invs |= self._create_invoice(partner=self.partner_efatura)

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            result = invs.action_send_efatura_bulk()

        self.assertIn('3', result['params']['message'])
        for inv in invs:
            self.assertEqual(inv.x_efatura_status, 'sent')

    def test_bulk_sorted_by_partner_vkn(self):
        """
        Faturalar alıcı VKN'e göre sıralı işlenmeli.
        Aynı alıcı ardışık → Sovos cache avantajı.
        """
        partner_a = self.env['res.partner'].create({
            'name': 'A Şirketi', 'vat': '1111111111',
            'x_efatura_type': 'efatura',
            'x_efatura_type_updated': date.today(),
        })
        partner_b = self.env['res.partner'].create({
            'name': 'B Şirketi', 'vat': '2222222222',
            'x_efatura_type': 'efatura',
            'x_efatura_type_updated': date.today(),
        })

        inv_b = self._create_invoice(partner=partner_b)
        inv_a = self._create_invoice(partner=partner_a)
        selection = inv_b | inv_a  # kasıtlı ters sıra

        processed = []

        def track_order(xml_bytes, uuid, partner, scenario):
            processed.append(partner.vat)
            return 'mock-uuid'

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             patch(
                 'l10n_tr_sovos_efatura.services.sovos_invoice_service'
                 '.SovosInvoiceService.send_ubl',
                 side_effect=track_order,
             ):
            selection.action_send_efatura_bulk()

        self.assertEqual(processed, sorted(processed),
            'Faturalar VKN\'e göre sıralı işlenmeli')

    def test_bulk_rate_limit_sleep_called(self):
        """500ms bekleme her gönderimden sonra çağrılmalı."""
        inv = self._create_invoice()

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success(), \
             patch('l10n_tr_sovos_efatura.models.account_move.time.sleep') as mock_sleep:
            inv.action_send_efatura_bulk()

        mock_sleep.assert_called_with(0.5)

    # ── Filtre ───────────────────────────────────────────────────────

    def test_bulk_skips_already_sent_invoices(self):
        """Zaten gönderilmiş faturalar atlanmalı."""
        draft_inv = self._create_invoice()
        sent_inv = self._create_sent_invoice()

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            result = (draft_inv | sent_inv).action_send_efatura_bulk()

        self.assertEqual(sent_inv.x_efatura_status, 'sent')  # değişmedi
        self.assertIn('1', result['params']['message'])

    def test_bulk_empty_selection_raises_user_error(self):
        """Gönderilebilir fatura yoksa anlamlı UserError."""
        sent_inv = self._create_sent_invoice()
        with self.assertRaises(UserError) as cm:
            sent_inv.action_send_efatura_bulk()
        self.assertIn('taslak', str(cm.exception).lower())

    # ── Kısmi hata ───────────────────────────────────────────────────

    def test_bulk_partial_failure_others_continue(self):
        """
        3 faturadan 1'i başarısız olsa diğer 2'si işlenmeli.
        KRİTİK: İş sürekliliği.
        """
        invs = [self._create_invoice() for _ in range(3)]
        bulk = invs[0] | invs[1] | invs[2]
        call_count = {'n': 0}

        def alternate_fail(*args, **kwargs):
            call_count['n'] += 1
            if call_count['n'] == 2:
                raise Exception('Sovos geçici hata')
            return 'mock-envelope-uuid'

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             patch(
                 'l10n_tr_sovos_efatura.services.sovos_invoice_service'
                 '.SovosInvoiceService.send_ubl',
                 side_effect=alternate_fail,
             ):
            result = bulk.action_send_efatura_bulk()

        msg = result['params']['message']
        self.assertIn('2', msg)   # Gönderildi: 2
        self.assertIn('1', msg)   # Hata: 1
        self.assertEqual(result['params']['type'], 'warning')

    def test_bulk_validation_error_counted_separately(self):
        """
        Validasyon hatası ayrı sayılmalı.
        BUG: 'validasyon' string arama dil bağımlı (_() çevirisi varsa bozulur).
        Bu test mevcut kırılgan mantığı belgeler.
        """
        inv = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_xsd_fail():
            result = inv.action_send_efatura_bulk()

        msg = result['params']['message']
        # 'Validasyon Hatası' Türkçe'de çalışır, dil değişirse bozulur
        self.assertIn('Validasyon', msg,
            'BUG: "validasyon" string arama dil bağımlı — dil değişirse kırılır')

    def test_bulk_success_notification_type_is_success(self):
        """Tüm faturalar gönderilirse bildirim tipi 'success' olmalı."""
        inv = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            result = inv.action_send_efatura_bulk()

        self.assertEqual(result['params']['type'], 'success')
