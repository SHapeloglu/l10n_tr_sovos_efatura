# -*- coding: utf-8 -*-
"""
UBL-TR İki Katmanlı Validasyon:
  Katman 1 → XSD   (lxml.etree.XMLSchema)
  Katman 2 → Schematron (Saxon HE / XSLT 2.0 + SVRL)

Neden saxonche?
  GİB'in UBL-TR_Main_Schematron.sch.xsl dosyası queryBinding="xslt2" ile
  üretilmiştir; lxml'in etree.XSLT() motoru yalnızca XSLT 1.0 çalıştırır ve
  XPath 2.0 ifadelerini (every/some/castable as vb.) sessizce atlar ya da
  çöker.  Saxon HE (HE = ücretsiz sürüm) XSLT 2.0/3.0 tam uyumludur.

Gereksinim:
  pip install saxonche
"""
import logging
import os
import tempfile

from lxml import etree

_logger = logging.getLogger(__name__)

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), 'schemas')
XSD_PATH   = os.path.join(SCHEMA_DIR, 'UBL-Invoice-2.1.xsd')
SCH_PATH   = os.path.join(SCHEMA_DIR, 'UBL-TR_Main_Schematron.sch.xsl')  # Pre-compiled XSLT 2.0

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

    # ── Katman 1: XSD ─────────────────────────────────────────────────────────

    def _load_xsd(self):
        if self._xsd is None:
            if not os.path.exists(XSD_PATH):
                _logger.warning('XSD dosyası bulunamadı: %s (katman 1 atlandı)', XSD_PATH)
                return None
            self._xsd = etree.XMLSchema(etree.parse(XSD_PATH))
        return self._xsd

    # ── Katman 2: Schematron (Saxon HE) ───────────────────────────────────────

    def _run_schematron_saxon(self, xml_bytes):
        """
        Saxon HE ile SVRL çıktısı üretir.
        Returns list[str] hata mesajları; boş liste = geçerli.
        Raises RuntimeError — caller hata yönetimini üstlenir.
        """
        import saxonche

        if not os.path.exists(SCH_PATH):
            _logger.warning('Schematron XSLT bulunamadı: %s (katman 2 atlandı)', SCH_PATH)
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
            test     = f.get('test', '')
            text_el  = f.find('{%s}text' % SVRL_NS)
            text     = text_el.text.strip() if text_el is not None and text_el.text else ''
            errors.append('%s: %s' % (test, text))
        return errors

    # ── Ana metot ─────────────────────────────────────────────────────────────

    def validate(self, xml_bytes):
        """
        Returns: (valid: bool, layer: str | None, errors: list[str])
        """
        # XML parse
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
            _logger.warning('XSD şema dosyası yok — katman 1 atlandı')

        # Katman 2: Schematron
        if not _saxonche_available():
            _logger.error(
                'saxonche kurulu değil — Schematron (XSLT 2.0) atlandı. '
                'Kurmak için: pip install saxonche'
            )
        else:
            try:
                sch_errors = self._run_schematron_saxon(xml_bytes)
                if sch_errors:
                    _logger.warning('Schematron hatası: %s', sch_errors[:3])
                    return False, 'SCHEMATRON', sch_errors
            except Exception as e:
                # Schematron motoru beklenmedik hata verirse gönderimi bloklama,
                # ancak hatayı açıkça kaydet.
                _logger.error(
                    'Schematron Saxon hatası (katman 2 atlandı): %s', e, exc_info=True
                )

        return True, None, []
