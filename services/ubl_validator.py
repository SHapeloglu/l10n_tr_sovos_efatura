# -*- coding: utf-8 -*-
"""
UBL-TR İki Katmanlı Validasyon:
  Katman 1 → XSD (lxml.etree.XMLSchema)
  Katman 2 → Schematron (XSLT transform + SVRL)
"""
import logging
import os

from lxml import etree

_logger = logging.getLogger(__name__)

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), 'schemas')
XSD_PATH = os.path.join(SCHEMA_DIR, 'UBL-Invoice-2.1.xsd')
SCH_PATH = os.path.join(SCHEMA_DIR, 'UBL-TR_Main_Schematron.sch.xsl')  # Pre-compiled XSLT

SVRL_NS = 'http://purl.oclc.org/dsdl/svrl'


class UblValidator:
    """XSD + Schematron validasyon servisi."""

    def __init__(self):
        self._xsd = None
        self._sch_transform = None

    def _load_xsd(self):
        if self._xsd is None:
            if not os.path.exists(XSD_PATH):
                _logger.warning('XSD dosyası bulunamadı: %s (validasyon atlandı)', XSD_PATH)
                return None
            self._xsd = etree.XMLSchema(etree.parse(XSD_PATH))
        return self._xsd

    def _load_schematron(self):
        if self._sch_transform is None:
            if not os.path.exists(SCH_PATH):
                _logger.warning('Schematron XSLT bulunamadı: %s (katman 2 atlandı)', SCH_PATH)
                return None
            sch_doc = etree.parse(SCH_PATH)
            self._sch_transform = etree.XSLT(sch_doc)
        return self._sch_transform

    def validate(self, xml_bytes):
        """
        Returns: (valid: bool, layer: str|None, errors: list[str])
        """
        try:
            doc = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as e:
            return False, 'XML_PARSE', [str(e)]

        # ── Katman 1: XSD ──────────────────────────────────────────────
        xsd = self._load_xsd()
        if xsd is not None:
            if not xsd.validate(doc):
                errors = [str(e) for e in xsd.error_log]
                _logger.warning('XSD validasyon hatası: %s', errors[:3])
                return False, 'XSD', errors
        else:
            _logger.warning('XSD şema dosyası yok — katman 1 atlandı')

        # ── Katman 2: Schematron ───────────────────────────────────────
        sch_transform = self._load_schematron()
        if sch_transform is not None:
            try:
                svrl = sch_transform(doc)
                failures = svrl.xpath(
                    '//svrl:failed-assert',
                    namespaces={'svrl': SVRL_NS}
                )
                if failures:
                    errors = []
                    for f in failures:
                        test = f.get('test', '')
                        text_el = f.find('{%s}text' % SVRL_NS)
                        text = text_el.text.strip() if text_el is not None and text_el.text else ''
                        errors.append('%s: %s' % (test, text))
                    _logger.warning('Schematron validasyon hatası: %s', errors[:3])
                    return False, 'SCHEMATRON', errors
            except Exception as e:
                _logger.error('Schematron XSLT hatası: %s', e)
                # Schematron hatası gönderimi bloklamasın — sadece logla
        else:
            _logger.warning('Schematron XSLT dosyası yok — katman 2 atlandı')

        return True, None, []
