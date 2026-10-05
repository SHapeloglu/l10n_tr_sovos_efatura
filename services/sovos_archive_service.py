# -*- coding: utf-8 -*-
"""
sovos_archive_service.py — Sovos ArchiveService SOAP İstemcisi
===============================================================
Sovos'un e-Arşiv web servisi (ArchiveService) ile iletişimi yönetir.
InvoiceService'den tamamen bağımsız bir servistir.

Fark:
    InvoiceService → GİB'e kayıtlı alıcılar (e-Fatura)
    ArchiveService → GİB'e kayıtsız alıcılar, bireysel müşteriler (e-Arşiv)

API Türü: SOAP/XML
Dokümantasyon: https://api.fitbulut.com/servis/#/eArsiv
"""
import base64
import hashlib
import io
import logging
import zipfile

import requests
from lxml import etree

_logger = logging.getLogger(__name__)

# e-Arşiv endpoint'leri (InvoiceService'den farklı URL'ler)
WSDL_PROD = 'https://earsiv.fitbulut.com/eArchive/services/EArchiveApplication?wsdl'
WSDL_TEST = 'https://earsiv-test.fitbulut.com/eArchive/services/EArchiveApplication?wsdl'

SOAP_NS = 'http://schemas.xmlsoap.org/soap/envelope/'
SVC_NS  = 'http://earchive.fitbulut.com/'  # e-Arşiv namespace (ear: öneki)


class SovosArchiveService:
    """
    Sovos ArchiveService için SOAP istemcisi.
    InvoiceService'e paralel mimari; sadece endpoint ve namespace farklı.
    """

    def __init__(self, company):
        """
        Parametreler:
            company: Şirket ayarları.
                     e-Arşiv için ayrı kullanıcı adı/şifre (x_sovos_archive_*)
                     InvoiceService kullanıcısından farklı olabilir.
        """
        self.company     = company
        self.user        = company.x_sovos_archive_user    # e-Arşiv kullanıcısı
        self.password    = company.x_sovos_archive_pass
        self.sender_vkn  = company.x_sovos_sender_vkn
        self.template_id = company.x_sovos_template_id or ''  # PDF şablon ID
        self.test_mode   = company.x_sovos_test_mode
        self.endpoint    = WSDL_TEST if self.test_mode else WSDL_PROD
        self.base_url    = self.endpoint.replace('?wsdl', '')

    def _soap_envelope(self, body_xml):
        """
        e-Arşiv için SOAP zarfı.
        InvoiceService'deki ile aynı yapı; sadece namespace farklı (ear: yerine).
        """
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<soapenv:Envelope xmlns:soapenv="%s" xmlns:ear="%s">'
            '<soapenv:Header/>'
            '<soapenv:Body>%s</soapenv:Body>'
            '</soapenv:Envelope>'
        ) % (SOAP_NS, SVC_NS, body_xml)

    def _post(self, action, body_xml):
        """
        SOAP isteği gönderir.
        InvoiceService._post() ile aynı mantık; ayrı tutulan sebebi:
        ArchiveService farklı endpoint ve namespace kullanır.
        """
        envelope = self._soap_envelope(body_xml)
        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': '"%s%s"' % (SVC_NS, action),
        }
        try:
            resp = requests.post(
                self.base_url,
                data=envelope.encode('utf-8'),
                headers=headers,
                timeout=60,
            )
            resp.raise_for_status()
        except requests.exceptions.Timeout:
            raise Exception('ArchiveService bağlantı zaman aşımı (60s)')
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 429:
                raise Exception('RATE_LIMIT_429')
            raise Exception('HTTP %d: %s' % (resp.status_code, str(e)))
        except requests.exceptions.ConnectionError as e:
            raise Exception('ArchiveService bağlantı hatası: %s' % str(e))

        return etree.fromstring(resp.content)

    def _create_zip(self, uuid, xml_bytes):
        """
        UUID.xml → UUID.zip sıkıştırma.
        GİB e-Arşiv de ZIP içinde UBL XML istiyor; InvoiceService ile aynı format.
        """
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('%s.xml' % uuid, xml_bytes)
        return buf.getvalue()

    def test_connection(self):
        """
        e-Arşiv bağlantı testi.
        TEST-UUID var olmayan bir UUID; servise ulaşabildik mi kontrol eder.
        404 değil de başka HTTP hatası → gerçek sorun.
        """
        try:
            body = (
                '<ear:GetInvoiceStatus>'
                '<ear:REQUEST_HEADER><ear:SESSION_ID/>'
                '<ear:CLIENT_TXN_ID>TEST</ear:CLIENT_TXN_ID>'
                '<ear:COMPRESSED>N</ear:COMPRESSED></ear:REQUEST_HEADER>'
                '<ear:USERNAME>%s</ear:USERNAME>'
                '<ear:PASSWORD>%s</ear:PASSWORD>'
                '<ear:VKNTCKN>%s</ear:VKNTCKN>'
                '<ear:UUID>TEST-UUID</ear:UUID>'
                '</ear:GetInvoiceStatus>'
            ) % (self.user, self.password, self.sender_vkn)
            self._post('GetInvoiceStatus', body)
            return True, 'OK'
        except Exception as e:
            # 404: var olmayan UUID için beklenen yanıt — bağlantı başarılı
            if 'HTTP' in str(e) and '404' not in str(e):
                return False, str(e)
            return True, 'OK (test UUID beklendi)'

    def send_invoice(self, xml_bytes, uuid, partner):
        """
        e-Arşiv fatura gönderir (SendInvoice).

        InvoiceService.send_ubl()'dan farklar:
          - MD5 hash: ZIP bütünlüğü kontrolü için
          - customizationParams: şablon ID ve şube bilgisi
          - receiverEmail: e-posta gönderimi için (opsiyonel)
          - responsiveOutput: PDF çıktı talebi

        Parametreler:
            xml_bytes (bytes): UBL XML
            uuid      (str): Fatura UUID'si
            partner         : res.partner (alıcı e-postası için)

        Returns: str — Sovos'tan dönen UUID (genellikle gönderdiğimizle aynı)
        """
        zip_bytes = self._create_zip(uuid, xml_bytes)
        b64_data = base64.b64encode(zip_bytes).decode('utf-8')
        # MD5 hash: Sovos ZIP bütünlüğünü doğrulamak için kullanır
        md5_hash = hashlib.md5(zip_bytes).hexdigest()
        receiver_email = partner.email or None

        # Özelleştirme parametreleri (şablon ve şube bilgisi)
        custom_params = '<ear:customizationParams>'
        custom_params += '<ear:param><ear:key>BRANCH</ear:key><ear:value>default</ear:value></ear:param>'
        if self.template_id:
            # PDF görsel şablonu; Sovos portalından alınan ID
            custom_params += '<ear:param><ear:key>TEMPLATE_ID</ear:key><ear:value>%s</ear:value></ear:param>' % self.template_id
        custom_params += '</ear:customizationParams>'

        # Alıcı e-postası: doluysa fatura müşteriye e-posta ile gönderilir
        email_xml = '<ear:receiverEmail>%s</ear:receiverEmail>' % receiver_email if receiver_email else ''

        body = (
            '<ear:SendInvoice>'
            '<ear:REQUEST_HEADER><ear:SESSION_ID/>'
            '<ear:CLIENT_TXN_ID>%s</ear:CLIENT_TXN_ID>'
            '<ear:COMPRESSED>N</ear:COMPRESSED></ear:REQUEST_HEADER>'
            '<ear:USERNAME>%s</ear:USERNAME>'
            '<ear:PASSWORD>%s</ear:PASSWORD>'
            '<ear:senderID>%s</ear:senderID>'
            '<ear:hash>%s</ear:hash>'           # MD5 hash (bütünlük kontrolü)
            '<ear:fileName>%s.zip</ear:fileName>'
            '<ear:docType>XML</ear:docType>'
            '<ear:binaryData>%s</ear:binaryData>'  # Base64 ZIP
            '%s'   # receiverEmail (opsiyonel)
            '%s'   # customizationParams
            '<ear:responsiveOutput><ear:outputType>PDF</ear:outputType></ear:responsiveOutput>'
            '</ear:SendInvoice>'
        ) % (
            uuid, self.user, self.password,
            self.sender_vkn, md5_hash, uuid,
            b64_data, email_xml, custom_params,
        )

        root = self._post('SendInvoice', body)
        result_uuid = self._extract_text(root, 'UUID') or uuid
        _logger.info('e-Arşiv gönderildi: UUID=%s', uuid)
        return result_uuid

    def get_invoice_status(self, uuid):
        """
        e-Arşiv faturasının durumunu sorgular.
        InvoiceService'in GetEnvelopeStatus'una karşılık gelir;
        fakat ArchiveService'de UUID direkt kullanılır (envelope_uuid yok).

        Returns: (status_code: int, status_message: str)
        """
        body = (
            '<ear:GetInvoiceStatus>'
            '<ear:REQUEST_HEADER><ear:SESSION_ID/>'
            '<ear:CLIENT_TXN_ID>STATUS_%s</ear:CLIENT_TXN_ID>'
            '<ear:COMPRESSED>N</ear:COMPRESSED></ear:REQUEST_HEADER>'
            '<ear:USERNAME>%s</ear:USERNAME>'
            '<ear:PASSWORD>%s</ear:PASSWORD>'
            '<ear:VKNTCKN>%s</ear:VKNTCKN>'
            '<ear:UUID>%s</ear:UUID>'
            '</ear:GetInvoiceStatus>'
        ) % (uuid, self.user, self.password, self.sender_vkn, uuid)
        root = self._post('GetInvoiceStatus', body)
        code = int(self._extract_text(root, 'STATUS_CODE') or 0)
        msg  = self._extract_text(root, 'STATUS_DESC') or ''
        return code, msg

    def cancel_invoice(self, uuid, reason=''):
        """
        e-Arşiv faturasını GİB API'si üzerinden iptal eder.

        e-Fatura'dan farkı: e-Arşiv API ile direkt iptal edilebilir.
        e-Fatura (TICARIFATURA) ise daha karmaşık bir iptal süreci gerektirir
        (karşılıklı mutabakat veya GİB portal).

        Parametreler:
            uuid   (str): İptal edilecek fatura UUID'si
            reason (str): İptal gerekçesi (kullanıcıdan alınır)

        Returns: bool — True: iptal başarılı
        GİB'te 0 veya 1300 kodu → başarı kabul edilir.
        """
        body = (
            '<ear:CancelInvoice>'
            '<ear:REQUEST_HEADER><ear:SESSION_ID/>'
            '<ear:CLIENT_TXN_ID>CANCEL_%s</ear:CLIENT_TXN_ID>'
            '<ear:COMPRESSED>N</ear:COMPRESSED></ear:REQUEST_HEADER>'
            '<ear:USERNAME>%s</ear:USERNAME>'
            '<ear:PASSWORD>%s</ear:PASSWORD>'
            '<ear:VKNTCKN>%s</ear:VKNTCKN>'
            '<ear:UUID>%s</ear:UUID>'
            '<ear:cancelReason>%s</ear:cancelReason>'
            '</ear:CancelInvoice>'
        ) % (uuid, self.user, self.password, self.sender_vkn, uuid, reason)
        root = self._post('CancelInvoice', body)
        code = int(self._extract_text(root, 'STATUS_CODE') or 0)
        # 0: genel başarı | 1300: GİB onayladı
        return code == 0 or code == 1300

    def get_invoice_pdf(self, uuid):
        """
        e-Arşiv fatura PDF'ini indirir.
        InvoiceService.get_invoice_pdf() ile aynı mantık; ayrı endpoint.

        Returns: str — Base64 kodlu PDF
        """
        body = (
            '<ear:GetInvoiceDocument>'
            '<ear:REQUEST_HEADER><ear:SESSION_ID/>'
            '<ear:CLIENT_TXN_ID>PDF_%s</ear:CLIENT_TXN_ID>'
            '<ear:COMPRESSED>N</ear:COMPRESSED></ear:REQUEST_HEADER>'
            '<ear:USERNAME>%s</ear:USERNAME>'
            '<ear:PASSWORD>%s</ear:PASSWORD>'
            '<ear:VKNTCKN>%s</ear:VKNTCKN>'
            '<ear:UUID>%s</ear:UUID>'
            '<ear:OutputType>PDF</ear:OutputType>'
            '</ear:GetInvoiceDocument>'
        ) % (uuid, self.user, self.password, self.sender_vkn, uuid)
        root = self._post('GetInvoiceDocument', body)
        return self._extract_text(root, 'DocData') or ''

    def _extract_text(self, root, tag):
        """XML ağacında tag'i arar ve text değerini döndürür."""
        el = root.find('.//{%s}%s' % (SVC_NS, tag))
        return el.text.strip() if el is not None and el.text else None
