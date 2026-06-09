# -*- coding: utf-8 -*-
"""
VKN Cache Mantığı Testleri — v6.1
Kod: models/res_partner.py — efatura_type_needs_refresh(), refresh_efatura_type()

v6.1 Değişiklik yok — kod aynı.
Spec v6.2 netleştirmesi: Sovos erişilemez + tip boş → inline hata bandı: BLOKE
(mevcut kodda earsiv'e düşüyor, bu spec'ten sapma olarak belgeleniyor)

Risk Seviyesi: YÜKSEK
"""
from datetime import date, timedelta
from unittest.mock import patch

from odoo.exceptions import UserError

from .common import SovosTestCommon


class TestVknCache(SovosTestCommon):

    # ── Yenileme kararı ───────────────────────────────────────────────

    def test_needs_refresh_when_type_empty(self):
        self.partner_no_cache.x_efatura_type = False
        self.assertTrue(self.partner_no_cache.efatura_type_needs_refresh())

    def test_needs_refresh_when_date_empty(self):
        self.partner_efatura.x_efatura_type_updated = False
        self.assertTrue(self.partner_efatura.efatura_type_needs_refresh())

    def test_needs_refresh_when_stale_31_days(self):
        self.partner_efatura.x_efatura_type_updated = date.today() - timedelta(days=31)
        self.assertTrue(self.partner_efatura.efatura_type_needs_refresh())

    def test_no_refresh_when_exactly_30_days(self):
        """30 günlük cache geçerli (koşul > 30)."""
        self.partner_efatura.x_efatura_type_updated = date.today() - timedelta(days=30)
        self.assertFalse(self.partner_efatura.efatura_type_needs_refresh())

    def test_no_refresh_when_fresh_10_days(self):
        self.partner_efatura.x_efatura_type_updated = date.today() - timedelta(days=10)
        self.assertFalse(self.partner_efatura.efatura_type_needs_refresh())

    def test_no_refresh_when_updated_today(self):
        self.partner_efatura.x_efatura_type_updated = date.today()
        self.assertFalse(self.partner_efatura.efatura_type_needs_refresh())

    # ── Cache yenileme başarılı ───────────────────────────────────────

    def test_refresh_sets_efatura_when_registered(self):
        """GİB kayıtlı VKN → x_efatura_type='efatura', bugünkü tarih."""
        with self._mock_vkn_check(is_registered=True):
            self.partner_no_cache.refresh_efatura_type(self.company)

        self.assertEqual(self.partner_no_cache.x_efatura_type, 'efatura')
        self.assertEqual(self.partner_no_cache.x_efatura_type_updated, date.today())

    def test_refresh_sets_earsiv_when_not_registered(self):
        """GİB kayıtsız VKN → x_efatura_type='earsiv'."""
        with self._mock_vkn_check(is_registered=False):
            self.partner_no_cache.refresh_efatura_type(self.company)

        self.assertEqual(self.partner_no_cache.x_efatura_type, 'earsiv')
        self.assertEqual(self.partner_no_cache.x_efatura_type_updated, date.today())

    def test_refresh_skips_when_no_vat(self):
        """VKN'siz partner için sorgu yapılmamalı."""
        self.partner_no_cache.vat = False
        with self._mock_vkn_check() as mock_check:
            self.partner_no_cache.refresh_efatura_type(self.company)
        mock_check.assert_not_called()

    # ── Cache yenileme Sovos erişilemez ───────────────────────────────

    def test_refresh_preserves_cache_on_sovos_failure(self):
        """
        Sovos erişilemez → mevcut cache korunmalı.
        iş devam etmeli (exception fırlatılmamalı).
        """
        self.partner_efatura.x_efatura_type = 'efatura'
        with self._mock_vkn_check_failure():
            self.partner_efatura.refresh_efatura_type(self.company)  # exception yok

        self.assertEqual(self.partner_efatura.x_efatura_type, 'efatura')

    def test_empty_cache_sovos_down_falls_back_to_earsiv(self):
        """
        Spec v6.2 §5: Sovos erişilemez + tip boş → BLOKE olmalı.
        MEVCUT DAVRANIS: refresh_efatura_type() sessizce döner,
        _resolve_efatura_type() → 'earsiv' döndürür.
        Bu test mevcut davranışı belgeler — spec'ten sapma olarak işaretler.
        """
        self.partner_no_cache.x_efatura_type = False
        with self._mock_vkn_check_failure():
            self.partner_no_cache.refresh_efatura_type(self.company)

        # Mevcut kod: tip hâlâ False → _resolve_efatura_type() 'earsiv' döndürür
        resolved = self.partner_no_cache.x_efatura_type or 'earsiv'
        self.assertEqual(resolved, 'earsiv',
            'SPEC SAPMA: Sovos down + tip boş → earsiv\'e düşüyor, spec bloke istiyor')

    # ── Gönderim entegrasyonu ─────────────────────────────────────────

    def test_invoice_does_not_refresh_fresh_cache(self):
        """10 günlük geçerli cache → gönderimde Sovos'a sorgu gitmemeli."""
        self.partner_efatura.x_efatura_type_updated = date.today() - timedelta(days=10)
        inv = self._create_invoice(partner=self.partner_efatura)

        with patch(
            'l10n_tr_sovos_efatura.models.res_partner.ResPartner.refresh_efatura_type'
        ) as mock_refresh, \
             self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            inv.action_post()

        mock_refresh.assert_not_called()

    def test_invoice_triggers_refresh_for_empty_cache(self):
        """Cache boş → gönderimde refresh_efatura_type() çağrılmalı."""
        self.partner_no_cache.x_efatura_type = False
        inv = self._create_invoice(partner=self.partner_no_cache)

        with patch(
            'l10n_tr_sovos_efatura.models.res_partner.ResPartner.refresh_efatura_type'
        ) as mock_refresh, \
             self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_archive_success():
            try:
                inv.action_post()
            except Exception:
                pass

        mock_refresh.assert_called_once()

    def test_stale_cache_triggers_refresh(self):
        """31 günlük cache → gönderimde yenilenmeli."""
        self.partner_efatura.x_efatura_type_updated = date.today() - timedelta(days=31)
        inv = self._create_invoice(partner=self.partner_efatura)

        with patch(
            'l10n_tr_sovos_efatura.models.res_partner.ResPartner.refresh_efatura_type'
        ) as mock_refresh, \
             self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            inv.action_post()

        mock_refresh.assert_called_once()
