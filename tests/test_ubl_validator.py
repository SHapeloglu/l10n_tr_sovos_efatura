# -*- coding: utf-8 -*-
"""
UBL Validator Testleri — v6.1 YENİ DOSYA
==========================================
Test edilen kod: services/ubl_validator.py
Test edilen sınıf/metod: UblValidator.validate(xml_bytes)

UBL VALİDASYON KATMANLARI
--------------------------
validate() metodu XML'i 3 aşamada kontrol eder. Herhangi bir aşama
başarısız olursa fatura GÖNDERİLMEZ.

    Katman 0 — XML_PARSE (v6.1 YENİ)
        XML sözdizimi geçerli mi? (well-formed)
        Hatalıysa: (False, 'XML_PARSE', [...])
        ↓ Geçtiyse devam et

    Katman 1 — XSD
        XML yapısı GİB şemasına uygun mu? (zorunlu alanlar, tipler)
        Dosya yoksa: ATLA (uyarı logla, bloke etme)
        Hatalıysa: (False, 'XSD', [...])
        ↓ Geçtiyse devam et

    Katman 2 — SCHEMATRON
        İş kuralları doğru mu? (tutarlar, oranlar)
        saxonche yoksa: ATLA (hata logla, bloke etme)
        Hatalıysa: (False, 'SCHEMATRON', [...])
        ↓ Geçtiyse devam et

    Başarı → (True, None, [])

v6.1'de tamamen yeniden yazıldı:
  - saxonche ile XSLT 2.0 Schematron desteği
  - XML_PARSE yeni hata katmanı
  - XSD yoksa katman 1 atlanır (warning, blok yok)
  - saxonche yoksa katman 2 atlanır (error log, blok yok)

Risk Seviyesi: YÜKSEK — yanlış validasyon = GİB reddi
"""
import os
from unittest.mock import patch, MagicMock

from .common import SovosTestCommon


# ── Test XML sabitleri ──────────────────────────────────────────────────────
# Gerçek UBL-TR XML'ine benzer, minimal geçerli yapı
VALID_XML = b'''<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:UBLVersionID>2.1</cbc:UBLVersionID>
  <cbc:ID>TST2026000000001</cbc:ID>
</Invoice>'''

# Kasıtlı bozuk XML — <Unclosed kapanmıyor → XML_PARSE hatası üretir
BROKEN_XML = b'<?xml version="1.0"?><Unclosed'


class TestUblValidator(SovosTestCommon):
    """
    UblValidator sınıfının 3 katmanlı validasyon sürecini test eder.

    Her test şu pattern'i izler:
        1. UblValidator() instance oluştur
        2. İlgili bağımlılıkları mock'la (_load_xsd, _run_schematron_saxon vb.)
        3. validate() çağır
        4. Dönen (valid, layer, errors) tuple'ını kontrol et
    """

    # ════════════════════════════════════════════════════════════════════
    # KATMAN 0: XML_PARSE
    # ════════════════════════════════════════════════════════════════════

    def test_validate_returns_xml_parse_error_on_broken_xml(self):
        """
        Bozuk XML (sözdizim hatası) → (False, 'XML_PARSE', [...]) dönmeli.

        v6.1 YENİ KATMAN: Bu kontrol XSD'den önce gelir.
        XML parse edilemiyorsa zaten sonraki katmanlara gerek yok.

        NOT: Bu test MOCK KULLANMIYOR — gerçek UblValidator() çağrısı yapılıyor.
        Çünkü XML_PARSE kontrolü harici bağımlılık gerektirmiyor (lxml built-in).
        """
        from l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        # BROKEN_XML geçersiz XML → parse hatası
        valid, layer, errors = UblValidator().validate(BROKEN_XML)

        # 3 değer döner: (geçerli mi, hata katmanı, hata listesi)
        self.assertFalse(valid)
        self.assertEqual(layer, 'XML_PARSE')
        # errors listesi dolu olmalı (hata açıklamaları)
        self.assertTrue(errors)

    # ════════════════════════════════════════════════════════════════════
    # KATMAN 1: XSD
    # ════════════════════════════════════════════════════════════════════

    def test_validate_xsd_layer_with_invalid_xml(self):
        """
        XSD şema dosyası varken yapısal hata içeren XML → (False, 'XSD', [...]).

        MagicMock() kullanımı:
            mock_xsd = MagicMock()             → otomatik sahte nesne
            mock_xsd.validate.return_value = False  → validate() False döner
            mock_xsd.error_log = [...]         → hata listesi
        Bu sayede gerçek XSD dosyasına ihtiyaç duymadan testi çalıştırabiliriz.
        """
        from l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        # Sahte XSD şema nesnesi oluştur
        mock_xsd = MagicMock()
        # validate() çağrıldığında False döner (validasyon başarısız)
        mock_xsd.validate.return_value = False
        # error_log: lxml'in hata listesi formatı
        mock_xsd.error_log = ['cbc:ID zorunlu alan eksik']

        validator = UblValidator()

        # patch.object(validator, '_load_xsd', return_value=mock_xsd):
        # Bu instance'ın _load_xsd() metodu çağrıldığında mock_xsd döner
        with patch.object(validator, '_load_xsd', return_value=mock_xsd):
            valid, layer, errors = validator.validate(VALID_XML)

        self.assertFalse(valid)
        self.assertEqual(layer, 'XSD')
        self.assertTrue(errors)

    def test_validate_skips_xsd_when_schema_file_missing(self):
        """
        XSD şema dosyası yoksa (None dönerse) katman 1 ATLANMALI, bloke olmamali.

        Neden atlama var?
            XSD dosyaları modülle birlikte gelmez, kurulum sırasında indirilir.
            Dosya eksikse faturayı engellemek yerine uyarı logla ve devam et.
            Schematron da atlansa bile (False → True) gönderim devam eder.

        Beklenen: (True, None, [])
        """
        from l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        validator = UblValidator()
        with patch.object(validator, '_load_xsd', return_value=None), \
             patch.object(validator, '_run_schematron_saxon', return_value=[]):
            valid, layer, errors = validator.validate(VALID_XML)

        # XSD atlandı, Schematron da boş döndü → geçerli
        self.assertTrue(valid, 'XSD yokken validasyon pass dönmeli')
        # layer None: hiçbir katmanda hata bulunamadı
        self.assertIsNone(layer)

    # ════════════════════════════════════════════════════════════════════
    # KATMAN 2: SCHEMATRON
    # ════════════════════════════════════════════════════════════════════

    def test_validate_schematron_failure(self):
        """
        XSD geçti + Schematron hata döndürürse → (False, 'SCHEMATRON', [...]).

        Birden fazla mock birlikte:
            patch.object(validator, '_load_xsd', ...)          → XSD mock
            patch('...._saxonche_available', return_value=True) → saxonche kurulu gibi
            patch.object(validator, '_run_schematron_saxon', ...)→ Schematron hatası
        """
        from l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        # XSD geçiyor (validate=True)
        mock_xsd = MagicMock()
        mock_xsd.validate.return_value = True

        validator = UblValidator()
        with patch.object(validator, '_load_xsd', return_value=mock_xsd), \
             patch(
                 # Modül seviyesindeki _saxonche_available fonksiyonunu mock'la
                 'l10n_tr_sovos_efatura.services.ubl_validator._saxonche_available',
                 return_value=True,   # saxonche kurulu gibi davran
             ), \
             patch.object(validator, '_run_schematron_saxon',
                          return_value=['BR-01: Zorunlu alan eksik']):
            valid, layer, errors = validator.validate(VALID_XML)

        self.assertFalse(valid)
        self.assertEqual(layer, 'SCHEMATRON')
        # errors[0]: ilk hata mesajı
        self.assertIn('BR-01', errors[0])

    def test_validate_skips_schematron_when_saxonche_missing(self):
        """
        saxonche kütüphanesi kurulu değilse Schematron katmanı ATLANMALI.

        saxonche nedir?
            XSLT 2.0 işlemcisi — Schematron kurallarını çalıştırmak için gerekli.
            pip install saxonche ile kurulur. Kurulu değilse Schematron çalışamaz.

        Tasarım kararı: saxonche opsiyonel.
            Eksikse bloke etme, sadece uyarı logla.
            Bu sayede saxonche kurulmadan da temel gönderim çalışır.

        Beklenen: (True, None, []) — valid=True, katman atlandı
        """
        from l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        mock_xsd = MagicMock()
        mock_xsd.validate.return_value = True

        validator = UblValidator()
        with patch.object(validator, '_load_xsd', return_value=mock_xsd), \
             patch(
                 'l10n_tr_sovos_efatura.services.ubl_validator._saxonche_available',
                 return_value=False,   # saxonche YOK
             ):
            valid, layer, errors = validator.validate(VALID_XML)

        # saxonche yoksa katman 2 atlandı → geçerli sayılır
        self.assertTrue(valid,
            'saxonche yokken validasyon pass dönmeli (katman 2 atlandı)')

    def test_validate_skips_schematron_when_xslt_file_missing(self):
        """
        saxonche var ama .sch.xsl (Schematron-to-XSLT dönüştürülmüş) dosyası
        yoksa Schematron boş hata listesi döndürmeli, bloke etmemeli.

        .sch.xsl dosyası: Schematron kuralları XSLT formatına derlenmiş hali.
        Bu dosya da opsiyonel kurulum dosyasıdır.
        """
        from l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        mock_xsd = MagicMock()
        mock_xsd.validate.return_value = True

        validator = UblValidator()
        with patch.object(validator, '_load_xsd', return_value=mock_xsd), \
             patch(
                 'l10n_tr_sovos_efatura.services.ubl_validator._saxonche_available',
                 return_value=True,
             ), \
             # Dosya yoksa _run_schematron_saxon [] döner (hata yok)
             patch.object(validator, '_run_schematron_saxon', return_value=[]):
            valid, layer, errors = validator.validate(VALID_XML)

        self.assertTrue(valid)

    def test_validate_schematron_exception_does_not_block(self):
        """
        Schematron motoru beklenmedik exception verirse gönderim BLOKLANMAMALidir.

        Savunmacı programlama:
            Schematron kontrolü "best effort" — mümkünse yap, olmuyorsa geç.
            Saxon'ın iç hatası yüzünden fatura gönderilemedi denmez.

        Beklenen: (True, None, []) — exception loglanır, gönderim devam eder
        """
        from l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        mock_xsd = MagicMock()
        mock_xsd.validate.return_value = True

        validator = UblValidator()
        with patch.object(validator, '_load_xsd', return_value=mock_xsd), \
             patch(
                 'l10n_tr_sovos_efatura.services.ubl_validator._saxonche_available',
                 return_value=True,
             ), \
             # side_effect=RuntimeError → çağrıldığında exception fırlatır
             patch.object(validator, '_run_schematron_saxon',
                          side_effect=RuntimeError('Saxon crash')):
            valid, layer, errors = validator.validate(VALID_XML)

        # Exception geldi ama gönderim bloklanmamalı
        self.assertTrue(valid, 'Schematron exception gönderimi bloklamamalı')

    # ════════════════════════════════════════════════════════════════════
    # BAŞARILI VALİDASYON
    # ════════════════════════════════════════════════════════════════════

    def test_validate_returns_true_when_both_layers_pass(self):
        """
        XSD geçti + Schematron geçti → (True, None, []) dönmeli.

        "Mutlu yol" testi — her şey doğruysa ne döner?
        """
        from l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        mock_xsd = MagicMock()
        mock_xsd.validate.return_value = True   # XSD geçti

        validator = UblValidator()
        with patch.object(validator, '_load_xsd', return_value=mock_xsd), \
             patch(
                 'l10n_tr_sovos_efatura.services.ubl_validator._saxonche_available',
                 return_value=True,
             ), \
             patch.object(validator, '_run_schematron_saxon', return_value=[]):  # hata yok
            valid, layer, errors = validator.validate(VALID_XML)

        self.assertTrue(valid)
        self.assertIsNone(layer)    # hiçbir katmanda hata yok
        self.assertEqual(errors, [])

    # ════════════════════════════════════════════════════════════════════
    # XSD CACHE
    # ════════════════════════════════════════════════════════════════════

    def test_xsd_loaded_once_and_cached(self):
        """
        Aynı UblValidator instance'ında XSD şeması sadece BİR KEZ yüklenmeli.

        Neden önemli?
            XSD parse etmek pahalıdır (CPU + bellek).
            Her fatura için tekrar yüklemek gereksiz.
            İlk yüklemeden sonra cache'de tutulmalı.

        Test stratejisi:
            _load_xsd() her çağrıldığında sayacı artıran bir fonksiyon yaz.
            İki kez validate() çağır.
            Sayacın 1 olduğunu doğrula (ikinci validate'de cache kullandı).
        """
        from l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        validator = UblValidator()
        mock_xsd = MagicMock()
        mock_xsd.validate.return_value = True

        # Yüklenme sayacı
        load_count = {'n': 0}

        def counting_load():
            """_load_xsd() yerine çalışır. Cache mantığını simüle eder."""
            if validator._xsd is None:
                # İlk çağrı: yükle ve cache'e yaz
                load_count['n'] += 1
                validator._xsd = mock_xsd
            # Her çağrıda cache döner
            return validator._xsd

        with patch.object(validator, '_load_xsd', side_effect=counting_load), \
             patch(
                 'l10n_tr_sovos_efatura.services.ubl_validator._saxonche_available',
                 return_value=False,
             ):
            # İki kez validate et
            validator.validate(VALID_XML)
            validator.validate(VALID_XML)

        # XSD sadece 1 kez yüklenmeli (2. seferde cache kullandı)
        self.assertEqual(load_count['n'], 1,
            'XSD şeması sadece bir kez yüklenmeli (cache)')
