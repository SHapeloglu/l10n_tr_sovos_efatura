# -*- coding: utf-8 -*-
"""
sovos_invoice_service.py — Sovos InvoiceService SOAP İstemcisi
===============================================================
Sovos'un GİB e-Fatura web servisi (InvoiceService) ile iletişimi yönetir.

API Türü: SOAP/XML (REST değil)
Dokümantasyon: https://api.fitbulut.com/servis/#/eFatura
WS Versiyonu: v2.3

Bu servis yalnızca e-Fatura içindir (GİB'e kayıtlı alıcılar).
e-Arşiv için sovos_archive_service.py kullanılır.

SOAP Nedir?
    Eski nesil bir web servisi protokolüdür. Her istek XML zarfı (envelope)
    içinde gönderilir; yanıt da XML döner.
    Endpoint: WSDL URL'si (wsdl parametresi olmadan base URL)

Desteklenen İşlemler:
    GetUserList         → VKN GİB'te kayıtlı mı? (VKN cache için)
    SendUBL             → e-Fatura GİB'e gönder
    GetEnvelopeStatus   → Gönderilen faturanın GİB durumunu sorgula
    GetInvResponses     → TICARIFATURA KABUL/RED yanıtları
    GetUblList          → Gelen faturaları listele
    GetInvoiceDocument  → Fatura PDF'ini indir
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

# SOAP endpoint'leri — test ve üretim ortamı
WSDL_PROD = 'https://efatura.fitbulut.com/eInvoice/services/EInvoiceApplication?wsdl'
WSDL_TEST = 'https://efatura-test.fitbulut.com/eInvoice/services/EInvoiceApplication?wsdl'

# SOAP standart namespace
SOAP_NS = 'http://schemas.xmlsoap.org/soap/envelope/'
# Sovos InvoiceService namespace (XML elementlerinde ein: öneki)
SVC_NS = 'http://einvoice.fitbulut.com/'


class SovosInvoiceService:
    """
    Sovos InvoiceService için SOAP istemcisi.

    Kullanım:
        svc = SovosInvoiceService(company)
        envelope_uuid = svc.send_ubl(xml_bytes, uuid, partner, scenario)
    """

    def __init__(self, company):
        """
        Parametreler:
            company (res.company): Bağlantı bilgileri bu nesneden alınır.

        test_mode=True iken test endpoint kullanılır; GİB'e iletim yapılmaz.
        """
        self.company = company
        self.user         = company.x_sovos_invoice_user
        self.password     = company.x_sovos_invoice_pass
        self.sender_vkn   = company.x_sovos_sender_vkn
        self.identifier   = company.x_sovos_identifier   # Posta kutusu (GB kodu)
        self.test_mode    = company.x_sovos_test_mode
        self.endpoint     = WSDL_TEST if self.test_mode else WSDL_PROD
        # WSDL URL'sinden ?wsdl kaldır → base URL (POST hedefi)
        self.base_url = self.endpoint.replace('?wsdl', '')

    # ── Düşük Seviye SOAP Yardımcıları ────────────────────────────────────

    def _soap_envelope(self, body_xml):
        """
        SOAP zarfı oluşturur.

        SOAP zarfı yapısı:
          <soapenv:Envelope>      ← Dış kap
            <soapenv:Header/>     ← Başlık (boş bırakıyoruz)
            <soapenv:Body>        ← İçerik; servis metoduna özel XML buraya girer
              {body_xml}
          </soapenv:Envelope>

        Parametreler:
            body_xml (str): Servis metoduna özgü XML parçası

        Dönüş: Tam SOAP zarfı (str)
        """
        envelope = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<soapenv:Envelope xmlns:soapenv="%s" xmlns:ein="%s">'
            '<soapenv:Header/>'
            '<soapenv:Body>%s</soapenv:Body>'
            '</soapenv:Envelope>'
        ) % (SOAP_NS, SVC_NS, body_xml)
        return envelope

    def _post(self, action, body_xml):
        """
        SOAP isteği gönderir ve yanıt XML'ini döndürür.

        Parametreler:
            action   (str): SOAPAction header değeri (ör: 'SendUBL')
            body_xml (str): İstek body'si

        Dönüş: etree.Element — yanıt XML kök elemanı

        Hata yönetimi:
            Timeout   → 60 saniye bekler, sonra exception
            429       → Rate limit aşıldı (RATE_LIMIT_429 mesajı)
            HTTP hata → HTTP durum kodu ile exception
            Bağlantı  → ConnectionError ile exception

        Neden requests kullanılıyor?
            Python'un standart urllib yerine daha kolay API.
            timeout parametresi kritik; aksi halde Odoo cron'u askıya alabilir.
        """
        envelope = self._soap_envelope(body_xml)
        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            # SOAPAction: hangi metodun çağrıldığını belirtir
            'SOAPAction': '"%s%s"' % (SVC_NS, action),
        }
        try:
            resp = requests.post(
                self.base_url,
                data=envelope.encode('utf-8'),  # str → bytes
                headers=headers,
                timeout=60,  # 60 saniye; GİB bazen yavaş yanıt verebilir
            )
            resp.raise_for_status()  # HTTP 4xx/5xx → HTTPError fırlatır
        except requests.exceptions.Timeout:
            raise Exception('Sovos bağlantı zaman aşımı (60s)')
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 429:
                # Rate limit: çok sık istek atıldı → toplu gönderimde 0.5s bekleme yeterli
                raise Exception('RATE_LIMIT_429')
            raise Exception('HTTP %d: %s' % (resp.status_code, str(e)))
        except requests.exceptions.ConnectionError as e:
            raise Exception('Sovos bağlantı hatası: %s' % str(e))

        # Yanıt XML'ini parse et
        return etree.fromstring(resp.content)

    def _create_zip(self, uuid, xml_bytes):
        """
        UUID.xml içeriğini UUID.zip formatında sıkıştırır.

        GİB zorunluluğu: Fatura XML'i ZIP içinde gönderilmelidir.
        ZIP içinde tam olarak 1 dosya olmalı ve UUID.xml adını taşımalıdır.

        Parametreler:
            uuid      (str): Dosya adı için kullanılır
            xml_bytes (bytes): Sıkıştırılacak UBL XML

        Dönüş: bytes — ZIP dosyası içeriği

        BytesIO: Diske yazmadan bellekte ZIP oluşturmak için kullanılır.
        """
        buf = io.BytesIO()  # Bellekte dosya tamponu
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            # ZIP_DEFLATED: standart sıkıştırma algoritması
            zf.writestr('%s.xml' % uuid, xml_bytes)
        return buf.getvalue()

    # ── Servis Metodları ──────────────────────────────────────────────────

    def test_connection(self):
        """
        Sovos bağlantısını test eder — GİB'e iletim yapmaz.
        GetUserList çağrısı kimlik doğrulama için yeterlidir.

        Returns: (ok: bool, message: str)
        """
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
        """
        Belirtilen VKN'in GİB e-Fatura sistemine kayıtlı olup olmadığını sorgular.

        Çalışma prensibi:
            GetUserList ile VKN sorgulanır.
            Yanıtta <User> elemanı var → kayıtlı (efatura)
            Yanıtta <User> elemanı yok → kayıtsız (earsiv)

        Parametreler:
            vkn (str): Sorgulanacak VKN/TCKN

        Returns: bool — True: GİB'te kayıtlı | False: kayıtsız

        Raises: Exception — Sovos erişilemiyorsa (caller yönetir)
        """
        body = (
            '<ein:GetUserList>'
            '<ein:REQUEST_HEADER>'
            '<ein:SESSION_ID/>'
            # CLIENT_TXN_ID: istek izleme için benzersiz değer; sorgu tipini belirtir
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
            # Yanıtta User elemanı var mı? → Kayıtlı
            users = root.findall('.//{%s}User' % SVC_NS)
            return len(users) > 0
        except Exception as e:
            _logger.warning('VKN sorgusu başarısız (%s): %s', vkn, e)
            raise  # Caller (res_partner.py) ele alır

    def send_ubl(self, xml_bytes, uuid, partner, scenario):
        """
        e-Fatura GİB'e gönderir (SendUBL).

        Akış:
          1. XML → ZIP sıkıştır
          2. ZIP → Base64 encode (SOAP text içinde göndermek için)
          3. SOAP isteği oluştur ve gönder
          4. Yanıttan ENVELOPE_UUID'yi çıkar

        Parametreler:
            xml_bytes (bytes): Doğrulanmış UBL XML
            uuid      (str): Fatura UUID'si
            partner         : res.partner kaydı (alıcı bilgisi)
            scenario  (str): 'TICARIFATURA' vb.

        Returns: envelope_uuid (str) — GİB tarafından atanan zarf UUID'si

        Neden envelope_uuid önemli?
            GİB durum sorgularında (GetEnvelopeStatus) bu UUID kullanılır.
            invoice UUID'sinden farklı olabilir.
        """
        zip_bytes = self._create_zip(uuid, xml_bytes)
        # base64: Binary ZIP'i XML-güvenli metin haline getirir
        b64_data = base64.b64encode(zip_bytes).decode('utf-8')
        # Alıcı posta kutusu: alias varsa kullan, yoksa VKN
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
            '<ein:SENDER>%s</ein:SENDER>'               # Gönderici VKN
            '<ein:RECEIVER>%s</ein:RECEIVER>'           # Alıcı posta kutusu/VKN
            '<ein:VKNTCKN>%s</ein:VKNTCKN>'            # Gönderici VKN (tekrar)
            '<ein:DocType>INVOICE</ein:DocType>'
            '<ein:ReceiverIdentifier>%s</ein:ReceiverIdentifier>'
            '<ein:SenderIdentifier>%s</ein:SenderIdentifier>'
            '<ein:DocData>%s</ein:DocData>'             # Base64 ZIP içeriği
            '</ein:SendUBL>'
        ) % (
            uuid, self.user, self.password,
            self.sender_vkn, receiver, self.sender_vkn,
            receiver, self.identifier, b64_data,
        )

        root = self._post('SendUBL', body)
        # ENVELOPE_UUID: GİB'in zarfa atadığı tanımlayıcı; durum sorgusu için gerekli
        # Yoksa fallback: kendi UUID'mizi kullan
        envelope_uuid = self._extract_text(root, 'ENVELOPE_UUID') or uuid
        _logger.info('SendUBL başarılı: UUID=%s EnvelopeUUID=%s', uuid, envelope_uuid)
        return envelope_uuid

    def get_envelope_status(self, envelope_uuid):
        """
        Gönderilmiş faturanın GİB durum kodunu sorgular.

        Bu metod SADECE e-Fatura (InvoiceService) içindir.
        e-Arşiv için SovosArchiveService.get_invoice_status() kullanılır.

        Parametreler:
            envelope_uuid (str): SendUBL'den dönen zarf UUID'si

        Returns: (status_code: int, status_message: str)
        Dönen kodlar constants.py'deki setlerle eşleşir.
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
        msg  = self._extract_text(root, 'STATUS_DESC') or ''
        return code, msg

    def get_inv_responses_outbound(self):
        """
        TICARIFATURA'lara gelen alıcı KABUL/RED yanıtlarını çeker.

        Type=OUTBOUND: Bizim gönderdiğimiz faturaların yanıtları.
        Alıcı ApplicationResponse mesajı ile yanıt verir:
          1305 → Kabul, 1310 → Red

        Returns: list[dict] — [{'uuid': '...', 'status_code': 1305}, ...]
        """
        body = (
            '<ein:GetInvResponses>'
            '<ein:REQUEST_HEADER>'
            '<ein:SESSION_ID/>'
            # İstek ID'si benzersiz olmalı; timestamp yeterince benzersiz
            '<ein:CLIENT_TXN_ID>RESP_%s</ein:CLIENT_TXN_ID>'
            '<ein:COMPRESSED>N</ein:COMPRESSED>'
            '</ein:REQUEST_HEADER>'
            '<ein:USERNAME>%s</ein:USERNAME>'
            '<ein:PASSWORD>%s</ein:PASSWORD>'
            '<ein:VKNTCKN>%s</ein:VKNTCKN>'
            '<ein:Type>OUTBOUND</ein:Type>'   # Bizim gönderdiklerimize gelen yanıtlar
            '</ein:GetInvResponses>'
        ) % (
            datetime.now().strftime('%Y%m%d%H%M%S'),
            self.user, self.password, self.sender_vkn,
        )
        root = self._post('GetInvResponses', body)
        responses = []
        # Her RESPONSE elemanını işle
        for resp_el in root.findall('.//{%s}RESPONSE' % SVC_NS):
            responses.append({
                'uuid':        self._el_text(resp_el, 'UUID'),
                'status_code': int(self._el_text(resp_el, 'STATUS_CODE') or 0),
            })
        return responses

    def get_inbound_list(self):
        """
        Sovos posta kutusuna gelen faturaları listeler.

        Type=INBOUND: Bize gönderilen (alış) faturalar.
        sovos_sync.py'de gelen faturaları Odoo'ya aktarmak için kullanılır.

        Returns: list[dict] — [{'uuid': '...', 'sender_vkn': '...', 'invoice_date': '...'}, ...]
        """
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
                'uuid':         self._el_text(inv_el, 'UUID'),
                'sender_vkn':   self._el_text(inv_el, 'SENDER_VKN'),
                'invoice_date': self._el_text(inv_el, 'INVOICE_DATE'),
            })
        return invoices

    def get_invoice_pdf(self, uuid):
        """
        Sovos'tan fatura PDF'ini indirir.

        Returns: str — Base64 kodlanmış PDF içeriği
        Kullanım: account_move.py → action_download_efatura_pdf()
        """
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
        # DocData: Base64 kodlu PDF verisi
        b64 = self._extract_text(root, 'DocData') or ''
        return b64

    # ── XML Yardımcıları ──────────────────────────────────────────────────

    def _extract_text(self, root, tag):
        """
        Tüm XML ağacında belirtilen tag'i arar ve text değerini döndürür.
        '//' XPath: root'tan itibaren tüm alt elemanlara bak.
        Bulamazsa veya boşsa None döner.
        """
        el = root.find('.//{%s}%s' % (SVC_NS, tag))
        return el.text.strip() if el is not None and el.text else None

    def _el_text(self, parent, tag):
        """
        Sadece parent'ın direkt çocukları arasında tag arar.
        _extract_text'ten farkı: '//' yerine direkt child araması.
        Belirli bir eleman içindeki alt elemanlara erişmek için.
        """
        el = parent.find('{%s}%s' % (SVC_NS, tag))
        return el.text.strip() if el is not None and el.text else None
