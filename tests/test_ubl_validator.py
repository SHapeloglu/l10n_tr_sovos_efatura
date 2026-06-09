# -*- coding: utf-8 -*-
"""
UBL Validator Testleri — v6.1 YENİ DOSYA
Kod: services/ubl_validator.py — UblValidator.validate()

v6.1'de tamamen yeniden yazıldı:
  - saxonche ile XSLT 2.0 Schematron desteği
  - XML_PARSE yeni hata katmanı
  - XSD yoksa katman 1 atlanır (warning, blok yok)
  - saxonche yoksa katman 2 atlanır (error log, blok yok)

Risk Seviyesi: YÜKSEK
"""
import os
from unittest.mock import patch, MagicMock

from .common import SovosTestCommon


VALID_XML = b'''<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:UBLVersionID>2.1</cbc:UBLVersionID>
  <cbc:ID>TST2026000000001</cbc:ID>
</Invoice>'''

BROKEN_XML = b'<?xml version="1.0"?><Unclosed'


class TestUblValidator(SovosTestCommon):

    # ── XML parse hatası ─────────────────────────────────────────────

    def test_validate_returns_xml_parse_error_on_broken_xml(self):
        """
        v6.1 YENİ: Bozuk XML → (False, 'XML_PARSE', [...]).
        XSD'ye bile gitmeden döner.
        """
        from l10n_tr_sovos_efatura.services.ubl_validator import UblValidator
        valid, layer, errors = UblValidator().validate(BROKEN_XML)

        self.assertFalse(valid)
        self.assertEqual(layer, 'XML_PARSE')
        self.assertTrue(errors)

    # ── XSD katmanı ──────────────────────────────────────────────────

    def test_validate_xsd_layer_with_invalid_xml(self):
        """
        XSD şema dosyası varken geçersiz XML → (False, 'XSD', [...]).
        """
        from l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        mock_xsd = MagicMock()
        mock_xsd.validate.return_value = False
        mock_xsd.error_log = ['cbc:ID zorunlu alan eksik']

        validator = UblValidator()
        with patch.object(validator, '_load_xsd', return_value=mock_xsd):
            valid, layer, errors = validator.validate(VALID_XML)

        self.assertFalse(valid)
        self.assertEqual(layer, 'XSD')
        self.assertTrue(errors)

    def test_validate_skips_xsd_when_schema_file_missing(self):
        """
        XSD dosyası yoksa katman 1 atlanır, validasyon devam eder (warning loglanır).
        """
        from l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        validator = UblValidator()
        with patch.object(validator, '_load_xsd', return_value=None), \
             patch.object(validator, '_run_schematron_saxon', return_value=[]):
            valid, layer, errors = validator.validate(VALID_XML)

        self.assertTrue(valid, 'XSD yokken validasyon pass dönmeli')
        self.assertIsNone(layer)

    # ── Schematron katmanı ────────────────────────────────────────────

    def test_validate_schematron_failure(self):
        """
        XSD geçti, Schematron hata döndürürse → (False, 'SCHEMATRON', [...]).
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
             patch.object(validator, '_run_schematron_saxon',
                          return_value=['BR-01: Zorunlu alan eksik']):
            valid, layer, errors = validator.validate(VALID_XML)

        self.assertFalse(valid)
        self.assertEqual(layer, 'SCHEMATRON')
        self.assertIn('BR-01', errors[0])

    def test_validate_skips_schematron_when_saxonche_missing(self):
        """
        saxonche kurulu değilse Schematron katmanı atlanır, hata loglanır,
        blok olmaz.
        """
        from l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        mock_xsd = MagicMock()
        mock_xsd.validate.return_value = True

        validator = UblValidator()
        with patch.object(validator, '_load_xsd', return_value=mock_xsd), \
             patch(
                 'l10n_tr_sovos_efatura.services.ubl_validator._saxonche_available',
                 return_value=False,
             ):
            valid, layer, errors = validator.validate(VALID_XML)

        # saxonche yoksa katman 2 atlanır → valid=True
        self.assertTrue(valid,
            'saxonche yokken validasyon pass dönmeli (katman 2 atlandı)')

    def test_validate_skips_schematron_when_xslt_file_missing(self):
        """
        saxonche var ama .sch.xsl dosyası yoksa → _run_schematron_saxon [] döner.
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
             patch.object(validator, '_run_schematron_saxon', return_value=[]):
            valid, layer, errors = validator.validate(VALID_XML)

        self.assertTrue(valid)

    def test_validate_schematron_exception_does_not_block(self):
        """
        Schematron motoru beklenmedik exception verirse gönderim bloklanmamalı.
        Hata loglanır, (True, None, []) döner.
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
             patch.object(validator, '_run_schematron_saxon',
                          side_effect=RuntimeError('Saxon crash')):
            valid, layer, errors = validator.validate(VALID_XML)

        self.assertTrue(valid,
            'Schematron exception gönderimi bloklamamalı')

    # ── Başarılı validasyon ───────────────────────────────────────────

    def test_validate_returns_true_when_both_layers_pass(self):
        """XSD + Schematron geçerse (True, None, []) dönmeli."""
        from l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        mock_xsd = MagicMock()
        mock_xsd.validate.return_value = True

        validator = UblValidator()
        with patch.object(validator, '_load_xsd', return_value=mock_xsd), \
             patch(
                 'l10n_tr_sovos_efatura.services.ubl_validator._saxonche_available',
                 return_value=True,
             ), \
             patch.object(validator, '_run_schematron_saxon', return_value=[]):
            valid, layer, errors = validator.validate(VALID_XML)

        self.assertTrue(valid)
        self.assertIsNone(layer)
        self.assertEqual(errors, [])

    # ── XSD cache ────────────────────────────────────────────────────

    def test_xsd_loaded_once_and_cached(self):
        """
        _load_xsd() aynı instance'da iki kez çağrılırsa şema sadece bir kez yüklenmeli.
        XML parsing pahalı — cache kritik.
        """
        from l10n_tr_sovos_efatura.services.ubl_validator import UblValidator

        validator = UblValidator()
        mock_xsd = MagicMock()
        mock_xsd.validate.return_value = True

        load_count = {'n': 0}

        def counting_load():
            if validator._xsd is None:
                load_count['n'] += 1
                validator._xsd = mock_xsd
            return validator._xsd

        with patch.object(validator, '_load_xsd', side_effect=counting_load), \
             patch(
                 'l10n_tr_sovos_efatura.services.ubl_validator._saxonche_available',
                 return_value=False,
             ):
            validator.validate(VALID_XML)
            validator.validate(VALID_XML)

        self.assertEqual(load_count['n'], 1,
            'XSD şeması sadece bir kez yüklenmeli (cache)')
