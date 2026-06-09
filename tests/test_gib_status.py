# -*- coding: utf-8 -*-
"""
GİB Durum Kodu İşleme Testleri — v6.1
Kod: models/account_move.py — _process_gib_status()

v6.1 Değişiklikler:
  - GIB_SUCCESS = {1300}, GIB_ACCEPTED_BY_RECEIVER = {1305} ayrı set
  - GIB_RETRY_SAME_UUID set ↔ resend_wizard.py RETRY_SAME_UUID eşleşmesi teyit edildi
  - 1215 → hâlâ _set_error() (status='error') → cron kilitlenmesi bug DEVAM EDİYOR

Risk Seviyesi: KRİTİK
"""
from datetime import date, timedelta
from unittest.mock import patch, call

from .common import SovosTestCommon


class TestGibStatusCodes(SovosTestCommon):

    def setUp(self):
        super().setUp()
        self.inv = self._create_sent_invoice()

    # ── Başarı kodları ────────────────────────────────────────────────

    def test_1300_sets_accepted_clears_error(self):
        """
        1300 → x_efatura_status='accepted', hata mesajı temizlenir.
        v6.1: GIB_SUCCESS = {1300} — 1305 artık bu setde değil.
        """
        self.inv.write({'x_efatura_error_msg': 'önceki hata'})
        self.inv._process_gib_status(1300)

        self.assertEqual(self.inv.x_efatura_status, 'accepted')
        self.assertFalse(self.inv.x_efatura_error_msg)
        self.assertEqual(self.inv.x_gib_status_code, 1300)

    def test_1300_accepted_cannot_be_resent(self):
        """
        1300 alındıktan sonra tekrar gönderim wizard'ı bloke etmeli.
        Spec: 'kesinlikle tekrar gönderme'.
        """
        from odoo.exceptions import UserError
        self.inv._process_gib_status(1300)
        self.assertEqual(self.inv.x_efatura_status, 'accepted')

        with self.assertRaises(UserError) as cm:
            wizard = self.env['sovos.resend.invoice.wizard'].create({
                'invoice_id': self.inv.id,
                'resend_type': 'same_uuid',
            })
            wizard.action_resend()
        self.assertIn('hatalı', str(cm.exception).lower())

    def test_1305_sets_accepted_and_kabul(self):
        """
        v6.1: 1305 → GIB_ACCEPTED_BY_RECEIVER (ayrı set).
        x_efatura_status='accepted', x_inv_response_status='kabul'.
        """
        self.inv._process_gib_status(1305)

        self.assertEqual(self.inv.x_efatura_status, 'accepted')
        self.assertEqual(self.inv.x_inv_response_status, 'kabul')
        self.assertFalse(self.inv.x_efatura_error_msg)
        self.assertEqual(self.inv.x_gib_status_code, 1305)

    def test_1305_is_not_in_gib_success_set(self):
        """
        v6.1 DÜZELTİLDİ: 1305 artık GIB_SUCCESS setinde değil.
        Bu ayrımın korunduğunu doğrular.
        """
        from l10n_tr_sovos_efatura.models.account_move import GIB_SUCCESS, GIB_ACCEPTED_BY_RECEIVER
        self.assertNotIn(1305, GIB_SUCCESS,
            '1305 GIB_SUCCESS içinde olmamalı (v6.1 düzeltmesi)')
        self.assertIn(1305, GIB_ACCEPTED_BY_RECEIVER)

    def test_1310_sets_rejected(self):
        """1310 → x_efatura_status='rejected', x_inv_response_status='red'."""
        self.inv._process_gib_status(1310)

        self.assertEqual(self.inv.x_efatura_status, 'rejected')
        self.assertEqual(self.inv.x_inv_response_status, 'red')
        self.assertTrue(self.inv.x_efatura_error_msg)
        self.assertEqual(self.inv.x_gib_status_code, 1310)

    # ── Teknik hata kodları (aynı UUID ile tekrar gönder) ─────────────

    def test_1101_sets_error(self):
        self.inv._process_gib_status(1101)
        self.assertEqual(self.inv.x_efatura_status, 'error')
        self.assertTrue(self.inv.x_efatura_error_msg)

    def test_1103_sets_error(self):
        self.inv._process_gib_status(1103)
        self.assertEqual(self.inv.x_efatura_status, 'error')

    def test_1150_sets_error_schematron(self):
        self.inv._process_gib_status(1150)
        self.assertEqual(self.inv.x_efatura_status, 'error')

    def test_1160_sets_error_xsd(self):
        self.inv._process_gib_status(1160)
        self.assertEqual(self.inv.x_efatura_status, 'error')

    def test_1210_sets_error_receiver_unreachable(self):
        """1210 → Alıcıya ulaşılamadı — iptal gerekmez, tekrar gönderilebilir."""
        self.inv._process_gib_status(1210)
        self.assertEqual(self.inv.x_efatura_status, 'error')
        self.assertIn('iptal gerekmez', self.inv.x_efatura_error_msg)

    # ── İptal + yeni fatura gerektiren durumlar ───────────────────────

    def test_1104_sets_error_and_notifies_admin(self):
        """
        1104 → _set_error() + _notify_admin_gib_error() çağrılmalı.
        Admin'e mail.message oluşturulmalı.
        """
        with patch.object(self.inv, '_notify_admin_gib_error') as mock_notify:
            self.inv._process_gib_status(1104)
            mock_notify.assert_called_once()
            args = mock_notify.call_args[0]
            self.assertEqual(args[0], 1104)

        self.assertEqual(self.inv.x_efatura_status, 'error')
        self.assertTrue(self.inv.x_efatura_error_msg)

    def test_1163_sets_error_and_notifies_admin(self):
        """1163 → Mükerrer UUID — admin bildirim."""
        with patch.object(self.inv, '_notify_admin_gib_error') as mock_notify:
            self.inv._process_gib_status(1163)
            mock_notify.assert_called_once()
        self.assertEqual(self.inv.x_efatura_status, 'error')

    # ── Sovos destek gerektiren durumlar ──────────────────────────────

    def test_1161_sets_error_sovos_support(self):
        """1161 → İmza hatası — Sovos teknik destek."""
        self.inv._process_gib_status(1161)
        self.assertEqual(self.inv.x_efatura_status, 'error')
        self.assertIn('Sovos', self.inv.x_efatura_error_msg)

    def test_1171_sets_error_sovos_support(self):
        self.inv._process_gib_status(1171)
        self.assertEqual(self.inv.x_efatura_status, 'error')

    # ── Bekleme kodları ───────────────────────────────────────────────

    def test_1000_no_status_change(self):
        """1000 → Kuyrukta. Durum değişmemeli — cron bir sonraki döngüde tekrar sorgular."""
        original = self.inv.x_efatura_status
        self.inv._process_gib_status(1000)
        self.assertEqual(self.inv.x_efatura_status, original)

    def test_1100_no_status_change(self):
        """1100 → İşleniyor. Bekle."""
        original = self.inv.x_efatura_status
        self.inv._process_gib_status(1100)
        self.assertEqual(self.inv.x_efatura_status, original)

    # ── KRİTİK BUG: 1215 sonrası cron kilitlenmesi ───────────────────

    def test_1215_sets_error_and_notifies_admin(self):
        """
        1215 → _set_error() + admin bildirim.
        MEVCUT BUG: status='error' yapılıyor.
        Cron sadece 'sent'/'sending' durumları sorguluyor →
        bu fatura bir daha sorgulanmaz → kilitlenir.
        Bu test mevcut davranışı belgeler.
        """
        with patch.object(self.inv, '_notify_admin_gib_error') as mock_notify:
            self.inv._process_gib_status(1215)
            mock_notify.assert_called_once()

        self.assertEqual(self.inv.x_efatura_status, 'error',
            '1215 sonrası status=error → cron bir daha bulamaz (bilinen bug)')
        # TODO: Düzeltme sonrası:
        # self.assertIn(self.inv.x_efatura_status, ('sent', 'sending'))
        # veya self.assertTrue(self.inv.x_gib_pending_retry)

    # ── KRİTİK: İki set senkronizasyonu ──────────────────────────────

    def test_retry_sets_are_identical(self):
        """
        GIB_RETRY_SAME_UUID (account_move.py) ile RETRY_SAME_UUID (resend_wizard.py)
        tam aynı olmalı. Biri güncellenip diğeri unutulursa bu test kırılır.
        """
        from l10n_tr_sovos_efatura.models.account_move import GIB_RETRY_SAME_UUID
        from l10n_tr_sovos_efatura.wizards.resend_invoice_wizard import RETRY_SAME_UUID

        diff = GIB_RETRY_SAME_UUID.symmetric_difference(RETRY_SAME_UUID)
        self.assertEqual(diff, set(),
            'Set farkı bulundu: %s\n'
            'account_move.py: %s\n'
            'resend_wizard.py: %s' % (diff, GIB_RETRY_SAME_UUID, RETRY_SAME_UUID))

    # ── 8 Gün hesaplama ───────────────────────────────────────────────

    def test_ticarifatura_deadline_set_to_8_days(self):
        """TICARIFATURA gönderiminde deadline = bugün + 8 gün."""
        self.assertEqual(
            self.inv.x_inv_response_deadline,
            date.today() + timedelta(days=8)
        )

    def test_show_8day_warning_when_deadline_today(self):
        """Deadline bugünse uyarı gösterilmeli (deadline <= today+1)."""
        self.inv.x_inv_response_deadline = date.today()
        self.assertTrue(self.inv.x_show_8day_warning)

    def test_show_8day_warning_when_deadline_tomorrow(self):
        """Deadline yarınsa uyarı gösterilmeli."""
        self.inv.x_inv_response_deadline = date.today() + timedelta(days=1)
        self.assertTrue(self.inv.x_show_8day_warning)

    def test_no_8day_warning_when_deadline_in_5_days(self):
        """Deadline 5 gün sonraysa uyarı yok."""
        self.inv.x_inv_response_deadline = date.today() + timedelta(days=5)
        self.assertFalse(self.inv.x_show_8day_warning)

    def test_no_8day_warning_when_kabul(self):
        """Kabul alındıktan sonra uyarı gösterilmemeli."""
        self.inv.write({
            'x_inv_response_deadline': date.today(),
            'x_inv_response_status': 'kabul',
        })
        self.assertFalse(self.inv.x_show_8day_warning)

    # ── Tip güvenliği ─────────────────────────────────────────────────

    def test_string_status_code_accepted(self):
        """SOAP string olarak gelebilir — int dönüşümü çalışmalı."""
        self.inv._process_gib_status('1300')
        self.assertEqual(self.inv.x_efatura_status, 'accepted')

    def test_none_status_code_no_crash(self):
        """None → 0 → hiçbir gruba girmez → durum değişmez."""
        original = self.inv.x_efatura_status
        self.inv._process_gib_status(None)
        self.assertEqual(self.inv.x_efatura_status, original)

    def test_unknown_code_does_not_crash(self):
        """Bilinmeyen kod sessizce geçmeli (9999 gibi)."""
        original = self.inv.x_efatura_status
        self.inv._process_gib_status(9999)
        # GIB kodu kayıt edilmeli
        self.assertEqual(self.inv.x_gib_status_code, 9999)

    # ── Hata mesajı dil çevirisi ──────────────────────────────────────

    def test_gib_msg_returns_localized_string(self):
        """
        v6.1: _gib_msg() lazy dict — her çağrıda aktif dil context'inde çeviri.
        Her kod için mesaj dönmeli.
        """
        from l10n_tr_sovos_efatura.models.account_move import _gib_msg
        for code in [1101, 1103, 1104, 1150, 1160, 1215, 1300, 1305, 1310]:
            msg = _gib_msg(code)
            self.assertTrue(msg, '_gib_msg(%d) boş string döndürdü' % code)
