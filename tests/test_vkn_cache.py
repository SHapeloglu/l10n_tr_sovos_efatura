# -*- coding: utf-8 -*-
"""
VKN Cache Mantığı Testleri — v6.1
===================================
Test edilen kod: models/res_partner.py
Test edilen metodlar:
  • efatura_type_needs_refresh()  → yenileme gerekiyor mu?
  • refresh_efatura_type()        → Sovos'a sorarak tipi güncelle

VKN CACHE NEDİR?
----------------
Bir müşterinin GİB'e kayıtlı olup olmadığı (efatura/earsiv) değişebilir.
Bu bilgiyi her fatura gönderiminde Sovos'a sormak hem yavaş hem de
gereksizdir. Bunun yerine:

    1. İlk sorguda sonucu DB'ye kaydet (x_efatura_type + x_efatura_type_updated)
    2. 30 gün geçmemişse DB'deki değeri kullan (cache hit)
    3. 30 gün geçtiyse Sovos'a tekrar sor (cache miss → refresh)

Cache taze eşiği: 30 gün (> 30 gün = stale/bayat)

v6.1 Değişiklik yok — kod aynı.
Spec v6.2 netleştirmesi: Sovos erişilemez + tip boş → BLOKE olmalı
(mevcut kodda earsiv'e düşüyor — bilinen spec sapması belgeleniyor)

Risk Seviyesi: YÜKSEK — yanlış tip = yanlış servise gönderim
"""
from datetime import date, timedelta
from unittest.mock import patch

from odoo.exceptions import UserError

from .common import SovosTestCommon


class TestVknCache(SovosTestCommon):
    """
    VKN cache karar mantığı ve yenileme akışı testleri.

    self.partner_efatura  → taze cache (bugün güncellendi)
    self.partner_no_cache → boş cache (hiç sorgulanmamış)
    """

    # ════════════════════════════════════════════════════════════════════
    # YENİLEME KARARI: efatura_type_needs_refresh()
    # Ne zaman yenileme gerekir?
    # ════════════════════════════════════════════════════════════════════

    def test_needs_refresh_when_type_empty(self):
        """
        x_efatura_type boşsa yenileme gerekir.

        Yeni müşteri veya daha önce hiç sorgulanmamış → tip bilinmiyor →
        Sovos'a sor.
        """
        self.partner_no_cache.x_efatura_type = False
        # True dönmesi = yenileme GEREKİYOR
        self.assertTrue(self.partner_no_cache.efatura_type_needs_refresh())

    def test_needs_refresh_when_date_empty(self):
        """
        Güncelleme tarihi boşsa yenileme gerekir.

        Tip dolu olsa bile "ne zaman sorgulandı" bilgisi yoksa
        ne kadar eskimiş bilinmez → yenile.
        """
        self.partner_efatura.x_efatura_type_updated = False
        self.assertTrue(self.partner_efatura.efatura_type_needs_refresh())

    def test_needs_refresh_when_stale_31_days(self):
        """
        Son güncelleme 31 gün önceyse cache bayatlamış → yenile.

        30 < 31 → koşul (günler > 30) sağlanıyor → yenileme gerekiyor.
        """
        # timedelta(days=31): bugünden 31 gün önce
        self.partner_efatura.x_efatura_type_updated = date.today() - timedelta(days=31)
        self.assertTrue(self.partner_efatura.efatura_type_needs_refresh())

    def test_no_refresh_when_exactly_30_days(self):
        """
        Son güncelleme tam 30 gün önceyse cache HÂLÂ GEÇERLİ.

        Sınır koşulu testi: koşul "> 30" (büyüktür) = 30 dahil değil.
        30 gün = taze, 31 gün = bayat.

        Bu "edge case" (sınır durumu) testi önemlidir:
        "> 30" ile ">= 30" farkı burada belirir.
        """
        self.partner_efatura.x_efatura_type_updated = date.today() - timedelta(days=30)
        # False dönmesi = yenileme GEREK YOK
        self.assertFalse(self.partner_efatura.efatura_type_needs_refresh())

    def test_no_refresh_when_fresh_10_days(self):
        """10 gün önce güncellendi → taze, yenileme gerekmez."""
        self.partner_efatura.x_efatura_type_updated = date.today() - timedelta(days=10)
        self.assertFalse(self.partner_efatura.efatura_type_needs_refresh())

    def test_no_refresh_when_updated_today(self):
        """Bugün güncellendi → en taze hali, kesinlikle yenileme gerekmez."""
        self.partner_efatura.x_efatura_type_updated = date.today()
        self.assertFalse(self.partner_efatura.efatura_type_needs_refresh())

    # ════════════════════════════════════════════════════════════════════
    # BAŞARILI CACHE YENİLEME: refresh_efatura_type()
    # ════════════════════════════════════════════════════════════════════

    def test_refresh_sets_efatura_when_registered(self):
        """
        Sovos: "Bu VKN GİB'e kayıtlı" → x_efatura_type='efatura', bugünkü tarih.

        _mock_vkn_check(is_registered=True): check_vkn_registered() → True döner
        Bu sayede gerçek Sovos çağrısı olmadan "kayıtlı" senaryosunu test ederiz.
        """
        with self._mock_vkn_check(is_registered=True):
            # Cache boş müşteri için yenileme yap
            self.partner_no_cache.refresh_efatura_type(self.company)

        # Tip güncellendi mi?
        self.assertEqual(self.partner_no_cache.x_efatura_type, 'efatura')
        # Güncelleme tarihi bugün olarak set edildi mi?
        self.assertEqual(self.partner_no_cache.x_efatura_type_updated, date.today())

    def test_refresh_sets_earsiv_when_not_registered(self):
        """
        Sovos: "Bu VKN GİB'e kayıtsız" → x_efatura_type='earsiv'.

        Bireyler veya GİB'e kaydolmamış küçük işletmeler için.
        """
        with self._mock_vkn_check(is_registered=False):
            self.partner_no_cache.refresh_efatura_type(self.company)

        self.assertEqual(self.partner_no_cache.x_efatura_type, 'earsiv')
        self.assertEqual(self.partner_no_cache.x_efatura_type_updated, date.today())

    def test_refresh_skips_when_no_vat(self):
        """
        VKN'i olmayan partner için Sovos sorgusu yapılmamalı.

        VKN olmadan Sovos'a ne sorulacak? Boş sorgu anlamsız.
        assert_not_called(): mock hiç çağrılmadı → Sovos'a gidilmedi.
        """
        self.partner_no_cache.vat = False
        # mock_check: check_vkn_registered'ı izle
        with self._mock_vkn_check() as mock_check:
            self.partner_no_cache.refresh_efatura_type(self.company)
        # VKN yoksa Sovos sorgusu hiç yapılmamalı
        mock_check.assert_not_called()

    # ════════════════════════════════════════════════════════════════════
    # SOVOS ERİŞİLEMEZ SENARYOLARI
    # ════════════════════════════════════════════════════════════════════

    def test_refresh_preserves_cache_on_sovos_failure(self):
        """
        Sovos'a bağlanılamıyorsa mevcut cache KORUNMALI, exception fırlatılmamalı.

        İş sürekliliği:
            Sovos geçici olarak kapalıysa mevcut bilgiyle devam et.
            "Efatura tipini bilmiyorum çünkü Sovos kapalı" diye faturayı
            engellemek kabul edilemez.

        Test: exception fırlatılmadığını doğrular (try/except yok → crash yok).
        """
        # Partner'ın tipi dolu
        self.partner_efatura.x_efatura_type = 'efatura'

        with self._mock_vkn_check_failure():
            # Exception fırlatılmamalı — sessizce devam etmeli
            self.partner_efatura.refresh_efatura_type(self.company)

        # Cache değişmedi — eski değer korundu
        self.assertEqual(self.partner_efatura.x_efatura_type, 'efatura')

    def test_empty_cache_sovos_down_falls_back_to_earsiv(self):
        """
        Sovos kapalı + cache boş → mevcut kod 'earsiv'e düşüyor.

        SPEC SAPMASI (v6.2 §5):
            Spec: Bu durumda BLOKE et, fatura gönderilemesin.
            Mevcut kod: 'earsiv' varsayımı yapıyor → fatura gönderiliyor.

        Bu test mevcut (yanlış) davranışı belgeler.
        Düzeltme yapılana kadar bu davranış bekleniyor.
        """
        self.partner_no_cache.x_efatura_type = False

        with self._mock_vkn_check_failure():
            self.partner_no_cache.refresh_efatura_type(self.company)

        # Mevcut kod: tip hâlâ False → _resolve_efatura_type() 'earsiv' döndürür
        resolved = self.partner_no_cache.x_efatura_type or 'earsiv'
        self.assertEqual(resolved, 'earsiv',
            "SPEC SAPMA: Sovos down + tip boş → earsiv'e düşüyor, spec bloke istiyor")

    # ════════════════════════════════════════════════════════════════════
    # GÖNDERİM ENTEGRASYONu
    # Cache, fatura gönderimini nasıl etkiliyor?
    # ════════════════════════════════════════════════════════════════════

    def test_invoice_does_not_refresh_fresh_cache(self):
        """
        Taze cache (10 gün) varsa fatura gönderiminde Sovos'a VKN sorgusu YAPILMAMALI.

        Performans testi:
            Taze cache → yenileme gerekmiyor → refresh_efatura_type() çağrılmamalı.
            assert_not_called() ile doğrulanır.
        """
        # Cache 10 gün önce güncellendi (taze)
        self.partner_efatura.x_efatura_type_updated = date.today() - timedelta(days=10)
        inv = self._create_invoice(partner=self.partner_efatura)

        with patch(
            'l10n_tr_sovos_efatura.models.res_partner.ResPartner.refresh_efatura_type'
        ) as mock_refresh, \
             self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            inv.action_post()

        # Taze cache → refresh hiç çağrılmamalı
        mock_refresh.assert_not_called()

    def test_invoice_triggers_refresh_for_empty_cache(self):
        """
        Cache boş → fatura gönderiminde refresh_efatura_type() ÇAĞRILMALI.

        Yeni müşteriye ilk fatura gönderiminde tip bilinmiyor → Sovos'a sor.
        """
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
                # Tip boşken gönderim başarısız olabilir — bu testte önemli değil
                # Önemli olan: refresh çağrıldı mı?
                pass

        # Cache boş → refresh çağrılmış olmalı
        mock_refresh.assert_called_once()

    def test_stale_cache_triggers_refresh(self):
        """
        Bayat cache (31 gün) → fatura gönderiminde cache yenilenmeli.

        31 gün önce kayıtlı değildi → şimdi kayıt yaptırmış olabilir.
        Kontrol et.
        """
        self.partner_efatura.x_efatura_type_updated = date.today() - timedelta(days=31)
        inv = self._create_invoice(partner=self.partner_efatura)

        with patch(
            'l10n_tr_sovos_efatura.models.res_partner.ResPartner.refresh_efatura_type'
        ) as mock_refresh, \
             self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            inv.action_post()

        # Bayat cache → refresh çağrılmalı
        mock_refresh.assert_called_once()
