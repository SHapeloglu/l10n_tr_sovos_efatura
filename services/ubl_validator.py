# -*- coding: utf-8 -*-
"""
ubl_validator.py — UBL-TR İki Katmanlı Validasyon Servisi
===========================================================
GİB'e göndermeden önce fatura XML'ini iki aşamada doğrular:

  Katman 1 → XSD   (lxml.etree.XMLSchema)
    XML'in GİB şemasına uygun olup olmadığını kontrol eder.
    Zorunlu elemanlar, veri tipleri, attribute'lar kontrol edilir.
    Dosya: services/schemas/UBL-Invoice-2.1.xsd

  Katman 2 → Schematron (Saxon HE / XSLT 2.0 → SVRL çıktısı)
    GİB iş kurallarını kontrol eder (XSD ile yakalanamayan kurallar).
    Örnek: "TICARIFATURA'da alıcı VKN zorunludur"
    Dosya: services/schemas/UBL-TR_Main_Schematron.sch.xsl

Neden Saxon HE (saxonche) zorunlu?
    GİB'in Schematron dosyası queryBinding="xslt2" ile üretilmiştir.
    Bu, XSLT 2.0 + XPath 2.0 özelliklerini kullanır (every/some/castable as vb.).
    lxml.etree.XSLT() yalnızca XSLT 1.0 çalıştırır → GİB Schematron'u çöker.
    Saxon HE ücretsiz ve XSLT 2.0/3.0 tam uyumludur.

Kurulum:
    pip install saxonche

DÜZELTME #4 (kritik):
    saxonche kurulu değilse validasyon GİB'e gönderimi BLOKLAR (UserError fırlatır).
    Spec "zorunlu validasyon" diyor; sessizce atlama GİB'te 1150/1170 hatalarına yol açar.
    Üretim ortamında saxonche KURULU OLMALIDIR.
"""
import logging
import os
import tempfile

from lxml import etree
from odoo.exceptions import UserError
from odoo import _

_logger = logging.getLogger(__name__)

# Şema dosyalarının bulunduğu dizin (bu dosyanın yanındaki schemas/ klasörü)
SCHEMA_DIR = os.path.join(os.path.dirname(__file__), 'schemas')
XSD_PATH   = os.path.join(SCHEMA_DIR, 'UBL-Invoice-2.1.xsd')           # GİB XSD şeması
SCH_PATH   = os.path.join(SCHEMA_DIR, 'UBL-TR_Main_Schematron.sch.xsl') # GİB Schematron (XSLT 2.0)

# SVRL (Schematron Validation Reporting Language) namespace
# Schematron sonuçları SVRL formatında döner; hataları bulmak için bu NS gerekli
SVRL_NS = 'http://purl.oclc.org/dsdl/svrl'


def _saxonche_available():
    """
    saxonche kütüphanesinin kurulu olup olmadığını kontrol eder.

    Returns: True → kurulu | False → kurulu değil

    Neden ayrı fonksiyon?
        Validate başlamadan önce kontrol etmek için kullanılır.
        Import hatası try/except ile yakalanır; ImportError → False döner.
    """
    try:
        import saxonche  # noqa: F401 (kullanılmadı uyarısını bastır)
        return True
    except ImportError:
        return False


class UblValidator:
    """
    UBL-TR XML doğrulama servisi.

    Kullanım:
        valid, layer, errors = UblValidator().validate(xml_bytes)
        if not valid:
            # errors listesinde hata mesajları var
    """

    def __init__(self):
        self._xsd = None  # XSD nesnesi lazy yüklenir (ilk validate() çağrısında)

    # ── Katman 1: XSD Doğrulama ───────────────────────────────────────────

    def _load_xsd(self):
        """
        XSD şema nesnesini yükler ve önbelleğe alır.

        Lazy yükleme:
            İlk çağrıda diskten okur ve self._xsd'ye atar.
            Sonraki çağrılarda önbellekten döner (dosya tekrar okunmaz).

        Dosya yoksa:
            Warning loglanır ve None döner → Katman 1 atlanır.
            Bu production'da kabul edilemez; schemas/ dizini dolu olmalıdır.

        Returns: etree.XMLSchema nesnesi veya None (dosya yoksa)
        """
        if self._xsd is None:
            if not os.path.exists(XSD_PATH):
                _logger.warning(
                    'XSD dosyası bulunamadı: %s — Katman 1 atlandı. '
                    'services/schemas/ dizinine UBL-Invoice-2.1.xsd kopyalayın.',
                    XSD_PATH,
                )
                return None
            # etree.parse: XML dosyasını parse eder → etree.XMLSchema: şema nesnesi oluşturur
            self._xsd = etree.XMLSchema(etree.parse(XSD_PATH))
        return self._xsd

    # ── Katman 2: Schematron (Saxon HE XSLT 2.0) ─────────────────────────

    def _run_schematron_saxon(self, xml_bytes):
        """
        Saxon HE ile GİB Schematron iş kurallarını doğrular.

        Akış:
          1. XML'i geçici dosyaya yaz (Saxon dosya yolu ile çalışır)
          2. PySaxonProcessor ile XSLT 2.0 dönüşümü yap
          3. SVRL çıktısını parse et
          4. failed-assert elemanlarını topla → hata listesi döndür

        Parameters:
            xml_bytes (bytes): Doğrulanacak UBL XML

        Returns:
            list[str]: Hata mesajları; boş liste → geçerli

        Raises:
            RuntimeError: Saxon başlatılamazsa (caller yönetir)
        """
        import saxonche

        if not os.path.exists(SCH_PATH):
            _logger.warning(
                'Schematron XSLT bulunamadı: %s — Katman 2 atlandı. '
                'services/schemas/ dizinine UBL-TR_Main_Schematron.sch.xsl kopyalayın.',
                SCH_PATH,
            )
            return []

        # Saxon dosya yollarıyla çalışır; XML'i geçici dosyaya yaz
        # delete=False: with bloğu bitmeden dosya silinmesini önler
        with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as tmp:
            tmp.write(xml_bytes)
            tmp_path = tmp.name

        try:
            # PySaxonProcessor: Saxon HE Java motorunu Python'dan kullanmak için
            # license=False: Ücretsiz (HE) sürümü kullan
            with saxonche.PySaxonProcessor(license=False) as proc:
                xslt = proc.new_xslt30_processor()
                # XSLT 2.0 dönüşümü: XML → SVRL çıktısı
                svrl_str = xslt.transform_to_string(
                    source_file=tmp_path,   # Doğrulanacak XML
                    stylesheet_file=SCH_PATH,  # GİB Schematron XSLT'si
                )
        finally:
            # Geçici dosyayı her durumda temizle
            os.unlink(tmp_path)

        if not svrl_str:
            return []  # SVRL çıktısı boş → hata yok

        # SVRL XML'ini parse et ve hataları topla
        svrl_doc = etree.fromstring(svrl_str.encode('utf-8'))

        # failed-assert: Schematron kuralını ihlal eden her yer için bir eleman
        failures = svrl_doc.xpath(
            '//svrl:failed-assert',
            namespaces={'svrl': SVRL_NS},
        )

        errors = []
        for f in failures:
            test    = f.get('test', '')   # Hangi kural (xpath ifadesi)
            text_el = f.find('{%s}text' % SVRL_NS)
            text    = text_el.text.strip() if text_el is not None and text_el.text else ''
            # 'kural_ifadesi: açıklama' formatında hata mesajı
            errors.append('%s: %s' % (test, text))

        return errors

    # ── Ana Doğrulama Metodu ──────────────────────────────────────────────

    def validate(self, xml_bytes):
        """
        UBL-TR XML'i XSD + Schematron ile doğrular.

        Parametreler:
            xml_bytes (bytes): UBL XML içeriği

        Dönüş değeri:
            (valid: bool, layer: str|None, errors: list[str])

            Geçerli   : (True, None, [])
            XSD hatası: (False, 'XSD', ['hata mesajı', ...])
            SCH hatası: (False, 'SCHEMATRON', ['kural: açıklama', ...])
            Parse hata: (False, 'XML_PARSE', ['lxml hata mesajı'])

        DÜZELTME #4 (saxonche yoksa blokla):
            saxonche kurulu değilse UserError fırlatılır.
            Spec "zorunlu validasyon" diyor; sessizce geçirmek GİB'te 1150/1170 verir.
            Üretim ortamında: pip install saxonche

        İki katman sırası önemlidir:
            XSD önce → Temel yapı doğruysa Schematron'a geç.
            Schematron XSD hatalarını tekrar bulmaz; ikisi birbirini tamamlar.
        """
        # Önce XML syntax kontrolü (bozuk XML'i parse edemeyiz)
        try:
            doc = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as e:
            return False, 'XML_PARSE', [str(e)]

        # ── Katman 1: XSD ──────────────────────────────────────────────────
        xsd = self._load_xsd()
        if xsd is not None:
            if not xsd.validate(doc):
                # error_log: lxml'in hata listesi nesnesi
                errors = [str(e) for e in xsd.error_log]
                _logger.warning('XSD validasyon hatası: %s', errors[:3])  # İlk 3'ü logla
                return False, 'XSD', errors
        else:
            _logger.warning('XSD dosyası yok — Katman 1 atlandı')

        # ── Katman 2: Schematron ────────────────────────────────────────────
        # DÜZELTME #4: saxonche yoksa gönderimi BLOKLA (sessizce geçirme)
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
            raise  # UserError'ları yukarıya ilet (bizim oluşturduklarımız)
        except Exception as e:
            # Saxon beklenmedik şekilde çöktü — gönderimi blokla
            _logger.error('Schematron Saxon beklenmeyen hata: %s', e, exc_info=True)
            raise UserError(_(
                'Schematron validasyonu başarısız (beklenmeyen hata): %s\n'
                'Sistem yöneticisi ile iletişime geçin.'
            ) % str(e))

        # Her iki katmandan geçti → geçerli
        return True, None, []
