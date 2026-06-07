# -*- coding: utf-8 -*-
"""
Sovos InvoiceService WS API v2.3
https://api.fitbulut.com/servis/#/eFatura
"""
import base64
import hashlib
import io
import logging
import zipfile
from datetime import datetime

import requests
from lxml import etree

_logger = logging.getLogger(__name__)

WSDL_PROD = 'https://efatura.fitbulut.com/eInvoice/services/EInvoiceApplication?wsdl'
WSDL_TEST = 'https://efatura-test.fitbulut.com/eInvoice/services/EInvoiceApplication?wsdl'

SOAP_NS = 'http://schemas.xmlsoap.org/soap/envelope/'
SVC_NS = 'http://einvoice.fitbulut.com/'


class SovosInvoiceService:
    """Sovos InvoiceService SOAP wrapper."""

    def __init__(self, company):
        self.company = company
        self.user = company.x_sovos_invoice_user
        self.password = company.x_sovos_invoice_pass
        self.sender_vkn = company.x_sovos_sender_vkn
        self.identifier = company.x_sovos_identifier
        self.test_mode = company.x_sovos_test_mode
        self.endpoint = WSDL_TEST if self.test_mode else WSDL_PROD
        self.base_url = self.endpoint.replace('?wsdl', '')

    def _soap_envelope(self, body_xml):
        """SOAP zarfı oluştur."""
        envelope = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<soapenv:Envelope xmlns:soapenv="%s" xmlns:ein="%s">'
            '<soapenv:Header/>'
            '<soapenv:Body>%s</soapenv:Body>'
            '</soapenv:Envelope>'
        ) % (SOAP_NS, SVC_NS, body_xml)
        return envelope

    def _post(self, action, body_xml):
        """SOAP isteği gönderir, yanıtı parse eder."""
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
            raise Exception('Sovos bağlantı zaman aşımı (60s)')
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 429:
                raise Exception('RATE_LIMIT_429')
            raise Exception('HTTP %d: %s' % (resp.status_code, str(e)))
        except requests.exceptions.ConnectionError as e:
            raise Exception('Sovos bağlantı hatası: %s' % str(e))

        return etree.fromstring(resp.content)

    def _create_zip(self, uuid, xml_bytes):
        """UUID.xml → UUID.zip."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('%s.xml' % uuid, xml_bytes)
        return buf.getvalue()

    def test_connection(self):
        """Kimlik doğrulama testi — GİB'e iletim yapılmaz."""
        try:
            body = (
                '<ein:GetUserList>'
                '<ein:REQUEST_HEADER>'
                '<ein:SESSION_ID/>'
                '<ein:CLIENT_TXN_ID>TEST</ein:CLIENT_TXN_ID>'
                '<ein:COMPRESSED>N</ein:COMPRESSED>'
                '</ein:REQUEST_HEADER>'
                '<ein:USERNAME>%s</ein:USERNAME>'
                '<ein:PASSWORD>%s</ein:PASSWORD>'
                '<ein:VKNTCKN>%s</ein:VKNTCKN>'
                '<ein:REGISTERED_EMAIL_FLAG>Y</ein:REGISTERED_EMAIL_FLAG>'
                '</ein:GetUserList>'
            ) % (self.user, self.password, self.sender_vkn)
            self._post('GetUserList', body)
            return True, 'OK'
        except Exception as e:
            return False, str(e)

    def check_vkn_registered(self, vkn):
        """VKN'in GİB e-Fatura sistemine kayıtlı olup olmadığını kontrol eder."""
        body = (
            '<ein:GetUserList>'
            '<ein:REQUEST_HEADER>'
            '<ein:SESSION_ID/>'
            '<ein:CLIENT_TXN_ID>VKN_CHECK_%s</ein:CLIENT_TXN_ID>'
            '<ein:COMPRESSED>N</ein:COMPRESSED>'
            '</ein:REQUEST_HEADER>'
            '<ein:USERNAME>%s</ein:USERNAME>'
            '<ein:PASSWORD>%s</ein:PASSWORD>'
            '<ein:VKNTCKN>%s</ein:VKNTCKN>'
            '<ein:REGISTERED_EMAIL_FLAG>Y</ein:REGISTERED_EMAIL_FLAG>'
            '</ein:GetUserList>'
        ) % (vkn, self.user, self.password, vkn)

        try:
            root = self._post('GetUserList', body)
            # Kullanıcı listesi dolu ise kayıtlı
            users = root.findall('.//{%s}User' % SVC_NS)
            return len(users) > 0
        except Exception as e:
            _logger.warning('VKN sorgusu başarısız (%s): %s', vkn, e)
            raise

    def send_ubl(self, xml_bytes, uuid, partner, scenario):
        """
        e-Fatura GİB'e gönderir.
        Returns: envelope_uuid (str)
        """
        zip_bytes = self._create_zip(uuid, xml_bytes)
        b64_data = base64.b64encode(zip_bytes).decode('utf-8')
        receiver = partner.x_efatura_alias or partner.vat or ''

        body = (
            '<ein:SendUBL>'
            '<ein:REQUEST_HEADER>'
            '<ein:SESSION_ID/>'
            '<ein:CLIENT_TXN_ID>%s</ein:CLIENT_TXN_ID>'
            '<ein:COMPRESSED>N</ein:COMPRESSED>'
            '</ein:REQUEST_HEADER>'
            '<ein:USERNAME>%s</ein:USERNAME>'
            '<ein:PASSWORD>%s</ein:PASSWORD>'
            '<ein:SENDER>%s</ein:SENDER>'
            '<ein:RECEIVER>%s</ein:RECEIVER>'
            '<ein:VKNTCKN>%s</ein:VKNTCKN>'
            '<ein:DocType>INVOICE</ein:DocType>'
            '<ein:ReceiverIdentifier>%s</ein:ReceiverIdentifier>'
            '<ein:SenderIdentifier>%s</ein:SenderIdentifier>'
            '<ein:DocData>%s</ein:DocData>'
            '</ein:SendUBL>'
        ) % (
            uuid, self.user, self.password,
            self.sender_vkn, receiver, self.sender_vkn,
            receiver, self.identifier, b64_data,
        )

        root = self._post('SendUBL', body)
        envelope_uuid = self._extract_text(root, 'ENVELOPE_UUID') or uuid
        _logger.info('SendUBL başarılı: UUID=%s EnvelopeUUID=%s', uuid, envelope_uuid)
        return envelope_uuid

    def get_envelope_status(self, envelope_uuid):
        """
        e-Fatura durum sorgular (InvoiceService — SADECE e-Fatura).
        Returns: (status_code: int, status_message: str)
        """
        body = (
            '<ein:GetEnvelopeStatus>'
            '<ein:REQUEST_HEADER>'
            '<ein:SESSION_ID/>'
            '<ein:CLIENT_TXN_ID>STATUS_%s</ein:CLIENT_TXN_ID>'
            '<ein:COMPRESSED>N</ein:COMPRESSED>'
            '</ein:REQUEST_HEADER>'
            '<ein:USERNAME>%s</ein:USERNAME>'
            '<ein:PASSWORD>%s</ein:PASSWORD>'
            '<ein:VKNTCKN>%s</ein:VKNTCKN>'
            '<ein:EnvelopeUUID>%s</ein:EnvelopeUUID>'
            '</ein:GetEnvelopeStatus>'
        ) % (envelope_uuid, self.user, self.password, self.sender_vkn, envelope_uuid)

        root = self._post('GetEnvelopeStatus', body)
        code = int(self._extract_text(root, 'STATUS_CODE') or 0)
        msg = self._extract_text(root, 'STATUS_DESC') or ''
        return code, msg

    def get_inv_responses_outbound(self):
        """TICARIFATURA KABUL/RED yanıtlarını getirir."""
        body = (
            '<ein:GetInvResponses>'
            '<ein:REQUEST_HEADER>'
            '<ein:SESSION_ID/>'
            '<ein:CLIENT_TXN_ID>RESP_%s</ein:CLIENT_TXN_ID>'
            '<ein:COMPRESSED>N</ein:COMPRESSED>'
            '</ein:REQUEST_HEADER>'
            '<ein:USERNAME>%s</ein:USERNAME>'
            '<ein:PASSWORD>%s</ein:PASSWORD>'
            '<ein:VKNTCKN>%s</ein:VKNTCKN>'
            '<ein:Type>OUTBOUND</ein:Type>'
            '</ein:GetInvResponses>'
        ) % (
            datetime.now().strftime('%Y%m%d%H%M%S'),
            self.user, self.password, self.sender_vkn,
        )
        root = self._post('GetInvResponses', body)
        responses = []
        for resp_el in root.findall('.//{%s}RESPONSE' % SVC_NS):
            responses.append({
                'uuid': self._el_text(resp_el, 'UUID'),
                'status_code': int(self._el_text(resp_el, 'STATUS_CODE') or 0),
            })
        return responses

    def get_inbound_list(self):
        """Gelen faturaları listeler."""
        body = (
            '<ein:GetUblList>'
            '<ein:REQUEST_HEADER>'
            '<ein:SESSION_ID/>'
            '<ein:CLIENT_TXN_ID>INBOUND_%s</ein:CLIENT_TXN_ID>'
            '<ein:COMPRESSED>N</ein:COMPRESSED>'
            '</ein:REQUEST_HEADER>'
            '<ein:USERNAME>%s</ein:USERNAME>'
            '<ein:PASSWORD>%s</ein:PASSWORD>'
            '<ein:VKNTCKN>%s</ein:VKNTCKN>'
            '<ein:Type>INBOUND</ein:Type>'
            '</ein:GetUblList>'
        ) % (
            datetime.now().strftime('%Y%m%d%H%M%S'),
            self.user, self.password, self.sender_vkn,
        )
        root = self._post('GetUblList', body)
        invoices = []
        for inv_el in root.findall('.//{%s}INVOICE' % SVC_NS):
            invoices.append({
                'uuid': self._el_text(inv_el, 'UUID'),
                'sender_vkn': self._el_text(inv_el, 'SENDER_VKN'),
                'invoice_date': self._el_text(inv_el, 'INVOICE_DATE'),
            })
        return invoices

    def get_invoice_pdf(self, uuid):
        """Fatura PDF'ini indirir. Returns: base64 encoded bytes."""
        body = (
            '<ein:GetInvoiceDocument>'
            '<ein:REQUEST_HEADER><ein:SESSION_ID/>'
            '<ein:CLIENT_TXN_ID>PDF_%s</ein:CLIENT_TXN_ID>'
            '<ein:COMPRESSED>N</ein:COMPRESSED></ein:REQUEST_HEADER>'
            '<ein:USERNAME>%s</ein:USERNAME>'
            '<ein:PASSWORD>%s</ein:PASSWORD>'
            '<ein:VKNTCKN>%s</ein:VKNTCKN>'
            '<ein:UUID>%s</ein:UUID>'
            '<ein:OutputType>PDF</ein:OutputType>'
            '</ein:GetInvoiceDocument>'
        ) % (uuid, self.user, self.password, self.sender_vkn, uuid)
        root = self._post('GetInvoiceDocument', body)
        b64 = self._extract_text(root, 'DocData') or ''
        return b64

    # ── Yardımcılar ───────────────────────────────────────────────────
    def _extract_text(self, root, tag):
        el = root.find('.//{%s}%s' % (SVC_NS, tag))
        return el.text.strip() if el is not None and el.text else None

    def _el_text(self, parent, tag):
        el = parent.find('{%s}%s' % (SVC_NS, tag))
        return el.text.strip() if el is not None and el.text else None
