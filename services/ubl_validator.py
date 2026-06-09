# -*- coding: utf-8 -*-
"""
ubl_validator.py — UBL-TR İki Katmanlı Validasyon
===================================================
Katman 1 → XSD   (lxml.etree.XMLSchema)
Katman 2 → Schematron (Saxon HE / XSLT 2.0 + SVRL)

Neden Saxon HE (saxonche)?
  GİB'in UBL-TR_Main_Schematron.sch.xsl dosyası queryBinding="xslt2" ile
  üretilmiştir. lxml.etree.XSLT() yalnızca XSLT 1.0 çalıştırır; XPath 2.0
  ifadelerini (every/some/castable as vb.) sessizce atlar veya çöker.
  Saxon HE (ücretsiz) XSLT 2.0/3.0 tam uyumludur.

Kurulum:
  pip install saxonche

DÜZELTME #4: saxonche yoksa validasyon GİB'e gönderimi bloklar (UserError).
  Spec "zorunlu validasyon" diyor; sessizce atlama kabul edilemez.
  Üretim ortamında saxonche kurulu OLMALIDIR.
"""
import logging
import os
import tempfile

from lxml import etree
from odoo.exceptions import UserError
from odoo import _

_logger = logging.getLogger(__name__)

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), 'schemas')
XSD_PATH   = os.path.join(SCHEMA_DIR, 'UBL-Invoice-2.1.xsd')
SCH_PATH   = os.path.join(SCHEMA_DIR, 'UBL-TR_Main_Schematron.sch.xsl')

SVRL_NS = 'http://purl.oclc.org/dsdl/svrl'


def _saxonche_available():
    try:
        import saxonche  # noqa: F401
        return True
    except ImportError:
        return False


class UblValidator:
    """XSD + Schematron (Saxon HE) validasyon servisi."""

    def __init__(self):
        self._xsd = None

    # ── Katman 1: XSD ────────────────────────────────────────────────────

    def _load_xsd(self):
        """XSD şemasını yükler. Dosya yoksa None döner (atlama logu ile)."""
        if self._xsd is None:
            if not os.path.exists(XSD_PATH):
                _logger.warning(
                    'XSD dosyası bulunamadı: %s — Katman 1 atlandı. '
                    'services/schemas/ dizinine UBL-Invoice-2.1.xsd kopyalayın.',
                    XSD_PATH,
                )
                return None
            self._xsd = etree.XMLSchema(etree.parse(XSD_PATH))
        return self._xsd

    # ── Katman 2: Schematron (Saxon HE) ─────────────────────────────────

    def _run_schematron_saxon(self, xml_bytes):
        """
        Saxon HE ile SVRL çıktısı üretir.
        Returns: list[str] hata mesajları; boş liste = geçerli.
        Raises: RuntimeError — caller yönetir.
        """
        import saxonche

        if not os.path.exists(SCH_PATH):
            _logger.warning(
                'Schematron XSLT bulunamadı: %s — Katman 2 atlandı. '
                'services/schemas/ dizinine UBL-TR_Main_Schematron.sch.xsl kopyalayın.',
                SCH_PATH,
            )
            return []

        # Saxon dosya yolu üzerinden çalışır; XML'i geçici dosyaya yaz
        with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as tmp:
            tmp.write(xml_bytes)
            tmp_path = tmp.name

        try:
            with saxonche.PySaxonProcessor(license=False) as proc:
                xslt = proc.new_xslt30_processor()
                svrl_str = xslt.transform_to_string(
                    source_file=tmp_path,
                    stylesheet_file=SCH_PATH,
                )
        finally:
            os.unlink(tmp_path)

        if not svrl_str:
            return []

        svrl_doc = etree.fromstring(svrl_str.encode('utf-8'))
        failures = svrl_doc.xpath(
            '//svrl:failed-assert',
            namespaces={'svrl': SVRL_NS},
        )
        errors = []
        for f in failures:
            test    = f.get('test', '')
            text_el = f.find('{%s}text' % SVRL_NS)
            text    = text_el.text.strip() if text_el is not None and text_el.text else ''
            errors.append('%s: %s' % (test, text))
        return errors

    # ── Ana Metot ────────────────────────────────────────────────────────

    def validate(self, xml_bytes):
        """
        UBL-TR XML'i iki katmanda doğrular.

        Returns:
            (valid: bool, layer: str | None, errors: list[str])
            Geçerli: (True, None, [])
            Hatalı:  (False, 'XSD'|'SCHEMATRON'|'XML_PARSE', ['hata1', ...])

        DÜZELTME #4: saxonche kurulu değilse UserError fırlatılır.
          Spec "zorunlu validasyon" diyor; sessizce atlama GİB'te 1150/1170
          hatalarına yol açar. Üretim ortamında 'pip install saxonche' zorunludur.
        """
        # XML parse kontrolü
        try:
            doc = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as e:
            return False, 'XML_PARSE', [str(e)]

        # Katman 1: XSD
        xsd = self._load_xsd()
        if xsd is not None:
            if not xsd.validate(doc):
                errors = [str(e) for e in xsd.error_log]
                _logger.warning('XSD validasyon hatası: %s', errors[:3])
                return False, 'XSD', errors
        else:
            _logger.warning('XSD dosyası yok — Katman 1 atlandı')

        # Katman 2: Schematron (Saxon HE)
        # DÜZELTME #4: saxonche yoksa gönderimi blokla
        if not _saxonche_available():
            raise UserError(_(
                'Schematron validasyonu (Katman 2) çalıştırılamıyor: saxonche kurulu değil.\n\n'
                'GİB UBL-TR Schematron şeması XSLT 2.0 gerektirir; lxml bu standardı '
                'desteklemez. Saxon HE kurmak için:\n\n'
                '  pip install saxonche\n\n'
                'Kurulum tamamlandıktan sonra tekrar deneyin.'
            ))

        try:
            sch_errors = self._run_schematron_saxon(xml_bytes)
            if sch_errors:
                _logger.warning('Schematron hatası: %s', sch_errors[:3])
                return False, 'SCHEMATRON', sch_errors
        except UserError:
            raise
        except Exception as e:
            # Saxon çöküşü: beklenmeyen hata — gönderimi blokla, logla
            _logger.error('Schematron Saxon beklenmeyen hata: %s', e, exc_info=True)
            raise UserError(_(
                'Schematron validasyonu başarısız (beklenmeyen hata): %s\n'
                'Sistem yöneticisi ile iletişime geçin.'
            ) % str(e))

        return True, None, []
