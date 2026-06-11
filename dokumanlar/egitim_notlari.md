# l10n_tr_sovos_efatura — Junior Odoo Developer Eğitim Notları

---

## 0. Mimari Sorumluluk Tablosu

Bu modülde kim ne yapıyor? Sovos sadece bir taşıyıcı; geriye kalan her şey
bizim tarafımızda:

```
Bizim tarafımız (bu modül):
    Odoo verisi → UBL XML üret         (services/ubl_builder.py)
    XML doğrula (XSD + Schematron)     (services/ubl_validator.py)
    ZIP'e sıkıştır                     (services/sovos_invoice_service.py)
    Base64 encode                       (services/sovos_invoice_service.py)
    SOAP zarfı oluştur                  (services/sovos_invoice_service.py)
    Durum kodunu yorumla                (services/constants.py + models/account_move.py)
    Odoo durumunu güncelle              (models/account_move.py)
    Hata yönetimi                       (models/account_move.py)
    VKN cache yönetimi                  (models/res_partner.py)
    Cron takibi                         (models/sovos_sync.py)
    İptal akışı                         (wizards/cancel_invoice_wizard.py)
    Tekrar gönderim                     (wizards/resend_invoice_wizard.py)

Sovos'un yaptığı (sadece bunlar):
    Dijital imza atar (sertifika Sovos'ta, biz yapamayız)
    GİB'e iletir
    GİB durumunu bize bildirir

GİB'in yaptığı:
    Faturayı kabul/reddeder
    Alıcıya iletir
    Durum kodu döndürür
```

Sovos'u başka bir sağlayıcıyla değiştirmek isteseydin sadece
`sovos_invoice_service.py` ve `sovos_archive_service.py` değişirdi,
geri kalan her şey aynı kalırdı.

---


---

## 1. Odoo Standart Modelleri

Bu modüldeki 5 dosyadan 4'ü Odoo'nun mevcut modellerini genişletir (`_inherit`),
1'i sıfırdan yeni bir model tanımlar (`_name`).

### res.company — Şirket
Odoo'da her şey bir şirkete bağlıdır. Kullanıcının hangi şirkette çalıştığı,
para birimi, adresi, muhasebe ayarları hep burada tutulur. Multi-company
kurulumda her şirket ayrı bir kayıttır.

Bu modülde ne ekledik:
- Sovos kullanıcı adı / şifre (e-Fatura ve e-Arşiv için ayrı ayrı)
- Gönderici VKN, GB kodu (posta kutusu)
- Test modu bayrağı (True iken GİB'e iletim olmaz)
- Admin hata bildirim e-postası

### res.partner — Müşteri / Tedarikçi / Kişi
Odoo'nun en merkezi modellerinden biri. Müşteriler, tedarikçiler, çalışanlar,
şirket adresleri hepsi res.partner'da tutulur.
- `customer_rank > 0` → müşteri
- `supplier_rank > 0` → tedarikçi
Bir faturanın `partner_id` alanı buraya bağlıdır.

Bu modülde ne ekledik:
- VKN cache (`x_efatura_type`: efatura / earsiv)
- Cache tarihi (`x_efatura_type_updated`)
- Vergi dairesi, GB kodu (alias)
- Varsayılan senaryo (TICARIFATURA / TEMELFATURA)

### uom.uom — Ölçü Birimi
Ürün ve fatura kalemlerinde kullanılan birimler. Adet, Kg, Metre, Litre gibi.
`uom` modülü aktif olmazsa bu model görünmez.

Bu modülde ne ekledik:
- `x_ubl_code`: GİB UN/CEFACT birim kodu (C62=Adet, KGM=Kg, MTR=Metre...)

### account.move — Fatura / Muhasebe Fişi
Odoo muhasebesinin kalbi. `move_type` alanıyla ayrılır:

| move_type   | Açıklama         |
|-------------|------------------|
| out_invoice | Satış faturası   |
| in_invoice  | Alış faturası    |
| out_refund  | Satış kredi notu |
| in_refund   | Alış kredi notu  |
| entry       | Muhasebe fişi    |

Bu modülde ne ekledik:
- `action_post()` override → "Onayla" butonuna e-Fatura akışı bağlandı
- GİB durum alanları (x_efatura_status, x_gib_status_code vb.)
- TICARIFATURA 8 günlük yanıt süresi takibi

### sovos.sync — Cron Görevi Modeli (YENİ)
Tamamen bu modüle özgü, Odoo'da karşılığı yok. Sadece cron (zamanlı görev)
metodlarını barındırmak için oluşturuldu. account.move'a da yazılabilirdi
ama sorumlulukları ayırmak için ayrı tutuldu.

---

## 2. Modül Dosya Yapısı

```
l10n_tr_sovos_efatura_fix/
├── __manifest__.py          # Modül tanımı (isim, bağımlılıklar, dosya listesi)
├── __init__.py              # Python paketi; alt klasörleri import eder
│
├── models/                  # Kalıcı veritabanı modelleri
│   ├── __init__.py
│   ├── res_company.py       # Şirket ayarları genişletmesi
│   ├── res_partner.py       # Müşteri/tedarikçi genişletmesi
│   ├── product_uom.py       # Birim kodu genişletmesi
│   ├── account_move.py      # Fatura ana model + e-Fatura akışı
│   └── sovos_sync.py        # Cron görevleri (yeni model)
│
├── services/                # Dış servis katmanı (SOAP istemcileri, XML üretici)
│   ├── constants.py         # GİB durum kod setleri (tek kaynak)
│   ├── ubl_builder.py       # UBL-TR 2.1 XML üretici
│   ├── ubl_validator.py     # XSD + Schematron validasyon
│   ├── sovos_invoice_service.py   # e-Fatura SOAP istemcisi
│   ├── sovos_archive_service.py   # e-Arşiv SOAP istemcisi
│   └── schemas/             # GİB şema dosyaları (XSD, Schematron XSLT)
│
├── wizards/                 # Geçici modeller (kullanıcı girdisi toplama)
│   ├── cancel_invoice_wizard.py   # İptal akışı
│   ├── resend_invoice_wizard.py   # Tekrar gönderim akışı
│   └── kur_farki_wizard.py        # Kur farkı faturası oluşturma
│
├── views/                   # XML arayüz tanımları
├── data/                    # Cron ve seri tanımları (XML)
└── security/                # Erişim yetkileri (CSV)
```

---

## 3. GİB Durum Kodları (constants.py)

GİB'ten dönen durum kodları 7 kategoriye ayrılmıştır. Her kategori farklı
aksiyon gerektirir.

| Set | Kodlar (örnek) | Yapılması gereken |
|-----|---------------|-------------------|
| GIB_PENDING | 1000, 1100 | Bekle, cron takip eder |
| GIB_SUCCESS | 1300 | accepted yap |
| GIB_ACCEPTED_BY_RECEIVER | 1305 | accepted + inv_response=kabul |
| GIB_REJECTED | 1310 | rejected + inv_response=red |
| GIB_RETRY_SAME_UUID | 1101, 1103, 1150... | error yap, aynı UUID ile düzelt+tekrar gönder |
| GIB_CANCEL_AND_NEW | 1104, 1163 | error yap, iptal + yeni fatura kes |
| GIB_SOVOS_SUPPORT | 1161, 1171, 1172 | error yap, Sovos teknik destek |
| GIB_NOTIFY_ADMIN | 1215 | sent KALIR (cron devam), admin bildir |

Neden tek kaynak (constants.py)?
Eskiden account_move.py ve resend_wizard.py'de ayrı ayrı set tanımı vardı.
Biri güncellenince diğeri unutulabiliyordu. Şimdi constants.py'yi değiştirmek
her yeri otomatik günceller.

---

## 4. e-Fatura Gönderim Akışı (account_move.py)

Kullanıcı "Onayla" butonuna bastığında `action_post()` devreye girer.

```
action_post()
    └── _efatura_post_single()
            1. Ön kontroller        → VKN, tarih, credentials boş mu?
            2. VKN cache            → efatura mı earsiv mi? (30 gün cache)
            3. Senaryo kontrolü     → earsiv + TICARIFATURA → hata
            4. Numara rezervasyonu  → PostgreSQL savepoint ile atomik
            5. UUID üret            → uuid4()
            6. UBL-TR XML üret      → UblBuilder.build()
            7. Validasyon           → XSD → Schematron (Saxon HE)
            8. Odoo POST            → super().action_post() (muhasebe fişi)
            9. Sovos gönder         → SendUBL veya SendInvoice
           10. Başarı               → status=sent, envelope_uuid kaydet
```

Hata durumunda:
- 7. adımda hata → numara serbest bırak, draft'ta kal
- 9. adımda hata → numara serbest bırak, Odoo'yu draft'a döndür

---

## 5. VKN Cache Mekanizması (res_partner.py)

Her faturada Sovos'a "bu VKN GİB'e kayıtlı mı?" diye sormak yerine
partner kartında önbellek tutulur.

```
Fatura gönderiminde:
  efatura_type_needs_refresh()
      ├── x_efatura_type boş    → True (yenile)
      ├── güncelleme tarihi yok → True (yenile)
      ├── 30+ gün geçmiş        → True (yenile)
      └── güncel               → False (cache kullan)

  Eğer yenileme gerekiyorsa:
      refresh_efatura_type(company)
          ├── Sovos GetUserList → VKN kayıtlı mı?
          ├── Başarı: x_efatura_type = 'efatura' veya 'earsiv'
          └── Hata:   cache değeri korunur (iş durmasın)
```

Cache boş + Sovos erişilemez → UserError (iş bloke, Spec Bölüm 5)
Cache dolu + Sovos erişilemez → cache kullan (iş devam)

---

## 6. UBL-TR XML Yapısı (ubl_builder.py)

GİB'in zorunlu kıldığı UBL 2.1 / TR1.2 profili formatı:

```xml
<Invoice>
  <ext:UBLExtensions>          → Dijital imza placeholder (Sovos doldurur)
  <cbc:UBLVersionID>2.1
  <cbc:CustomizationID>TR1.2
  <cbc:ProfileID>TICARIFATURA  → Senaryo
  <cbc:ID>ABC2024000000001     → Fatura numarası
  <cbc:UUID>xxxxxxxx-...       → Benzersiz tanımlayıcı
  <cbc:IssueDate>2024-01-15
  <cac:AccountingSupplierParty> → Gönderici (şirket)
  <cac:AccountingCustomerParty> → Alıcı (müşteri)
  <cac:LegalMonetaryTotal>      → Para toplamları
  <cac:TaxTotal>                → Vergi kırılımları
  <cac:InvoiceLine>             → Her kalem için tekrar
```

Namespace sistemi:
- `cbc:` → Temel elemanlar (ID, Name, Amount...)
- `cac:` → Bileşik elemanlar (Party, Address, TaxTotal...)
- `ext:` → Uzantılar (dijital imza)

---

## 7. Validasyon Katmanları (ubl_validator.py)

İki aşamalı doğrulama GİB'e göndermeden önce çalışır:

**Katman 1 — XSD**
- XML'in şemaya uygun olup olmadığını kontrol eder
- Zorunlu elemanlar, veri tipleri, attribute'lar
- lxml.etree.XMLSchema ile çalışır

**Katman 2 — Schematron**
- GİB iş kurallarını kontrol eder (XSD'nin yakalayamadıkları)
- Örnek: "TICARIFATURA'da alıcı VKN zorunludur"
- XSLT 2.0 gerektirir → saxonche (Saxon HE) zorunlu
- lxml yalnızca XSLT 1.0 çalıştırır, bu yüzden yeterli değil

saxonche kurulu değilse gönderim BLOKLANIR (sessizce geçirilmez).

---

## 8. SOAP İstemcileri (sovos_invoice_service / sovos_archive_service)

İki ayrı Sovos web servisi:

| | InvoiceService | ArchiveService |
|---|---|---|
| Alıcı | GİB'e kayıtlı (efatura) | GİB'e kayıtsız (earsiv) |
| Gönderim metodu | SendUBL | SendInvoice |
| Durum sorgusu | GetEnvelopeStatus (envelope_uuid ile) | GetInvoiceStatus (uuid ile) |
| İptal | Desteklenmiyor (portal veya mutabakat) | CancelInvoice() API |
| PDF indirme | GetInvoiceDocument | GetInvoiceDocument |

Her iki servis de:
- XML ZIP içinde gönderilir (UUID.xml → UUID.zip)
- ZIP Base64 encode edilerek SOAP body'ye eklenir
- Timeout: 60 saniye

---

## 9. İptal Matris Tablosu (cancel_invoice_wizard.py)

| Tür | Durum | İptal Edilebilir mi? | Yöntem |
|-----|-------|----------------------|--------|
| e-Arşiv | herhangi | EVET | CancelInvoice() API |
| TEMELFATURA | herhangi | EVET (portal onayı ile) | GİB portal + checkbox |
| TICARIFATURA | draft / error | EVET | Odoo statüsü güncelle |
| TICARIFATURA | sent | HAYIR | Karşılıklı mutabakat gerekli |
| TICARIFATURA | accepted | HAYIR | — |
| TICARIFATURA | rejected | HAYIR | Yeni fatura kes |
| TICARIFATURA | 8 gün dolmuş | HAYIR | Hukuki danışman |

---

## 10. Cron Görevleri (sovos_sync.py)

| Cron | Sıklık | Ne yapar |
|------|--------|----------|
| cron_sync_incoming_invoices | 15 dk | Gelen faturaları Sovos'tan çekip Odoo'ya kaydeder |
| cron_sync_efatura_status | 30 dk | Bekleyen e-Faturaların GİB durumunu sorgular |
| cron_sync_earsiv_status | 30 dk | Bekleyen e-Arşiv durumlarını sorgular |
| cron_sync_inv_responses | 1 saat | TICARIFATURA KABUL/RED yanıtları |
| cron_check_8day_warnings | Günlük | 8 gün dolmak üzere olan faturalar için uyarı |
| cron_refresh_vkn_cache | Günlük | 30 günden eski VKN cache'lerini yeniler |

Multi-company: Her cron tüm şirketler için döngü yapar.
Bir şirkette hata olursa diğerleri etkilenmez (try/except + continue).

---

## 11. Önemli Düzeltmeler (Bug Fix Notları)

**DÜZELTME #1 — 1215 cron kilitlenmesi**
1215 alındığında x_efatura_status 'error'a GEÇİRİLMEZ; 'sent' KALIR.
Neden? 'error'a geçirilseydi cron bu faturayı bir daha sorgulamazdı.
'sent' kalınca cron takip etmeye devam eder.

**DÜZELTME #2 — Kod setleri tek kaynaktan**
GIB_RETRY_SAME_UUID ve diğer setler artık sadece constants.py'de tanımlı.
Eskiden account_move.py ve resend_wizard.py'de ayrı ayrı tanım vardı;
senkronizasyon kayması riski ortadan kalktı.

**DÜZELTME #3 — 'sent' durumundaki TICARIFATURA iptal bloğu**
Önceki versiyonda 'sent' durumundaki fatura iptal edilebiliyordu.
Alıcıya iletilmiş fatura tek taraflı iptal edilemez (GİB kuralı).
Şimdi UserError fırlatılıyor: karşılıklı mutabakat gerekli mesajı.

**DÜZELTME #4 — saxonche yoksa sessizce geçirme**
saxonche kurulu değilse validasyon atlanmıyordu.
Şimdi UserError fırlatılıyor. Sessizce geçirmek GİB'te 1150/1170 verir.

---

## 12. Odoo Geliştirici Terimleri Sözlüğü

| Terim | Açıklama |
|-------|----------|
| `_inherit` | Mevcut modeli genişlet (yeni tablo açmaz) |
| `_name` | Yeni model tanımla (yeni tablo açar) |
| `TransientModel` | Geçici model; wizard kapanınca DB'den silinir |
| `@api.model` | Belirli kayda değil modele ait metod |
| `@api.depends` | Alan değişince computed alanı yeniden hesapla |
| `@api.onchange` | Alan değişince client-side tetiklenir (kaydedilmez) |
| `ensure_one()` | Tek kayıt bekleniyor; birden fazlaysa hata ver |
| `with_company()` | Multi-company bağlamını değiştir |
| `copy=False` | Fatura kopyalanınca bu alan kopyalanmasın |
| `tracking=True` | Alan değişikliklerini chatter'a logla |
| `store=False` | Computed alan DB'de saklanmaz |
| `(0, 0, vals)` | Many2many/One2many'e yeni kayıt ekle |
| `(4, id)` | Many2many'e mevcut kaydı bağla |
| `(5, 0, 0)` | Many2many/One2many'deki tüm kayıtları sil |
| `message_post()` | Fatura chatter'ına not ekle |
| `mail.mt_note` | İç not subtype'ı (dışarıya gönderilmez) |

---

## 13. Standart Dışı Kütüphaneler ve Kavramlar

Bu bölüm Odoo'nun standart kütüphanesinde olmayan, services/ klasöründe
kullanılan kütüphane ve kavramları açıklar.

### 13.1 requests — HTTP İstemcisi

Python'un standart `urllib` yerine kullanılan üçüncü parti kütüphane.
Sovos SOAP API'sine HTTP POST isteği göndermek için kullanılır.

```python
import requests

resp = requests.post(
    url,
    data=envelope.encode('utf-8'),  # SOAP zarfı
    headers={'Content-Type': 'text/xml; charset=utf-8'},
    timeout=60,                      # Sovos yanıt vermezse 60 saniyede pes et
)
resp.raise_for_status()  # HTTP 4xx/5xx → HTTPError fırlatır
```

Yakalanabilecek hatalar:
- `requests.exceptions.Timeout`      → 60 saniye doldu
- `requests.exceptions.HTTPError`    → 4xx/5xx HTTP hatası
- `requests.exceptions.ConnectionError` → ağa ulaşılamıyor

Neden timeout zorunlu?
    Timeout olmadan Sovos cevap vermezse Odoo worker sonsuza kadar bekler,
    yeni isteklere cevap veremez, sistem kilitlenir.

---

### 13.2 lxml — XML İşleme

Python'un standart `xml.etree.ElementTree` yerine kullanılan C tabanlı
hızlı XML kütüphanesi. UBL XML üretimi ve SOAP yanıtı parse için kullanılır.

**XML üretimi (UblBuilder):**
```python
from lxml import etree

# Kök eleman oluştur
root = etree.Element('{namespace}Invoice', nsmap=NS)

# Alt eleman ekle
child = etree.SubElement(root, '{namespace}ID')
child.text = 'ABC001'

# XML'i bytes olarak al
xml_bytes = etree.tostring(root, xml_declaration=True, encoding='UTF-8', pretty_print=True)
```

**XML parse (SOAP yanıtı):**
```python
root = etree.fromstring(resp.content)  # bytes → Element nesnesi
el = root.find('.//{namespace}STATUS_CODE')  # XPath ile ara
text = el.text if el is not None else None
```

**XSD validasyon:**
```python
xsd = etree.XMLSchema(etree.parse('schema.xsd'))
xsd.validate(doc)          # True/False
xsd.error_log              # hata listesi
```

**Clark notation:**
    lxml'de namespace'li elementler `{uri}local` formatında ifade edilir.
    Örnek: `{urn:...:CommonBasicComponents-2}ID`
    `_tag()` yardımcısı bu formatı üretir.

---

### 13.3 SOAP — Web Servis Protokolü

REST'in aksine XML tabanlı eski nesil web servis protokolü.
Sovos hem e-Fatura hem e-Arşiv için SOAP kullanıyor.

**SOAP zarfı yapısı:**
```xml
<soapenv:Envelope>      ← Dış kap
  <soapenv:Header/>     ← Başlık (boş)
  <soapenv:Body>        ← İçerik
    <ein:SendUBL>       ← Servis metodu
      <ein:USERNAME>... ← Parametreler
    </ein:SendUBL>
  </soapenv:Body>
</soapenv:Envelope>
```

**SOAPAction header:**
    Her SOAP isteğinde hangi metodun çağrıldığını belirtir.
    `'SOAPAction': '"http://einvoice.fitbulut.com/SendUBL"'`

**WSDL:**
    Web servisin tüm metodlarını, parametrelerini ve dönüş tiplerini
    tanımlayan XML dosyası. URL'in sonuna `?wsdl` eklenerek görüntülenir.
    Bu modülde WSDL sadece endpoint adresi için kullanılır;
    otomatik istemci üretimi yapılmıyor (manuel SOAP zarfı yazılıyor).

---

### 13.4 base64 — Binary → Text Dönüşümü

Binary veriyi (ZIP, PDF) SOAP/XML içinde text olarak taşımak için kullanılır.

```python
import base64

# Binary → Base64 string (göndermek için)
zip_bytes = b'\x50\x4b...'
b64_str = base64.b64encode(zip_bytes).decode('utf-8')
# → 'UEsDBBQAAAAI...'

# Base64 string → Binary (almak için)
pdf_bytes = base64.b64decode(b64_str)
```

Neden gerekli?
    XML text tabanlıdır; binary veri içeremez.
    base64 binary'yi sadece ASCII karakterlerle ifade eder (A-Z, a-z, 0-9, +, /).

---

### 13.5 zipfile + io.BytesIO — Bellekte ZIP Oluşturma

GİB fatura XML'ini ZIP içinde istiyor. Diske yazmadan bellekte ZIP oluşturmak için:

```python
import io
import zipfile

buf = io.BytesIO()          # Bellekte dosya tamponu (disk yok)
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('UUID.xml', xml_bytes)  # XML'i ZIP'e ekle
zip_bytes = buf.getvalue()  # ZIP içeriğini bytes olarak al
```

`io.BytesIO`: Diske yazmadan bellekte binary dosya gibi çalışan nesne.
`ZIP_DEFLATED`: Standart sıkıştırma algoritması (DEFLATE).

---

### 13.6 hashlib — MD5 Hash

e-Arşiv gönderiminde ZIP bütünlüğü kontrolü için Sovos MD5 hash istiyor:

```python
import hashlib

md5_hash = hashlib.md5(zip_bytes).hexdigest()
# → 'a3f4c8d2e1b9f7...' (32 karakter hex string)
```

MD5 ne işe yarar?
    Sovos gelen ZIP'in MD5'ini hesaplar, bizim gönderdiğimizle karşılaştırır.
    Eşleşmezse veri iletimde bozulmuş demektir.
    NOT: MD5 güvenlik için değil, bütünlük kontrolü için kullanılıyor.
    Şifreleme amaçlı kullanım için MD5 güvensizdir.

---

### 13.7 saxonche — XSLT 2.0 İşlemcisi (Saxon HE)

GİB'in Schematron dosyası XSLT 2.0 gerektirir. lxml sadece XSLT 1.0 çalıştırır.
Saxon HE (ücretsiz Java tabanlı) Python wrapper'ı ile kullanılır.

```python
import saxonche

with saxonche.PySaxonProcessor(license=False) as proc:  # HE = ücretsiz
    xslt = proc.new_xslt30_processor()
    svrl_str = xslt.transform_to_string(
        source_file='fatura.xml',       # Doğrulanacak XML
        stylesheet_file='schematron.xsl' # GİB Schematron XSLT
    )
```

Kurulum: `pip install saxonche`

Neden Java tabanlı?
    Saxon orijinal olarak Java ile yazılmış endüstri standardı XSLT işlemcisi.
    saxonche Python wrapper'ı JVM'i arka planda çalıştırır.
    Bu yüzden Java kurulu olması gerekebilir.

---

### 13.8 SVRL — Schematron Doğrulama Raporu

Schematron çalıştırıldığında SVRL (Schematron Validation Reporting Language)
formatında XML çıktısı üretir. Hatalar `failed-assert` elemanlarında:

```xml
<svrl:failed-assert test="cbc:UUID">
    <svrl:text>UUID zorunludur</svrl:text>
</svrl:failed-assert>
```

lxml ile parse edilir:
```python
failures = svrl_doc.xpath(
    '//svrl:failed-assert',
    namespaces={'svrl': 'http://purl.oclc.org/dsdl/svrl'}
)
for f in failures:
    test = f.get('test')    # hangi kural
    text = f.find(...)      # hata açıklaması
```

---

### 13.9 tempfile — Geçici Dosya

Saxon dosya yoluyla çalışır, BytesIO kabul etmez.
XML'i geçici dosyaya yazıp Saxon'a vermek için:

```python
import tempfile
import os

with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as tmp:
    tmp.write(xml_bytes)
    tmp_path = tmp.name     # /tmp/tmpXXXXXX.xml

try:
    # Saxon burada tmp_path'i okur
    result = xslt.transform_to_string(source_file=tmp_path, ...)
finally:
    os.unlink(tmp_path)     # Her durumda geçici dosyayı sil
```

`delete=False`: with bloğu bitince dosya silinmesin (Saxon okuyacak).
`os.unlink`: İşim bitti, şimdi sil.
`finally`: Hata olsa bile geçici dosya temizlenir.

---

### 13.10 UBL-TR Namespace Sistemi

UBL-TR XML'inde beş farklı namespace kullanılır. Her namespace farklı
element kategorisini temsil eder:

```
cbc: → CommonBasicComponents  → Temel elemanlar  (ID, Name, Amount)
cac: → CommonAggregateComponents → Bileşik elemanlar (Party, Address, TaxTotal)
ext: → CommonExtensionComponents → Uzantılar (dijital imza)
ubl: → Invoice-2               → Kök eleman
xsi: → XMLSchema-instance      → Şema referansı
```

Clark notation (lxml formatı):
```python
# Namespace + local isim birleşimi
'{urn:...:CommonBasicComponents-2}ID'

# _tag() yardımcısı bunu üretir:
_tag('cbc', 'ID') → '{urn:...:CommonBasicComponents-2}ID'
```

---

### 13.11 Log Seviyeleri — Ne Zaman Ne Kullanılır

```python
_logger.debug(...)    # Geliştirme ortamı detay (üretimde görünmez)
_logger.info(...)     # Rutin bilgi — fatura gönderildi, cache güncellendi
_logger.warning(...)  # Beklenmedik ama iş devam ediyor — VKN sorgusu başarısız
_logger.error(...)    # Ciddi hata, müdahale gerekebilir
_logger.critical(...) # Sistem çöküyor (Odoo'da nadiren kullanılır)
```

Üretim ortamında genellikle WARNING seviyesi ayarlanır:
- INFO mesajları görünmez (çok fazla gürültü)
- WARNING ve üstü görünür (dikkat gerektiren şeyler)

Kural:
```
Kullanıcı tetikledi + hata    → UserError (ekranda popup)
Cron/arka plan + hata         → _logger.warning veya _logger.error
İkisi birlikte de olabilir    → logla + UserError fırlat
```

---

## 14. Tespit Edilen Eksikler

**1. Şifre alanları düz metin**
`x_sovos_invoice_pass`, `x_sovos_archive_pass` DB'de şifrelenmeden duruyor.
Odoo Enterprise Vault veya DB seviyesi şifreleme yok.

**2. `size` parametreleri tutarsız**
VKN/TCKN için `size=11` yorum yok, fatura numarası `size=50` ama GİB formatı
sabit 16 karakter. Yanlış format girişi DB seviyesinde engellenemiyor.

**3. GİB durum kodları hardcoded**
`_gib_msg()` dict Python dosyasında gömülü. Yeni kod eklemek için deploy
gerekiyor. DB modeli (`gib.status.code`) olmalıydı; ekrandan yönetilebilir,
çeviri destekli, audit izli olurdu.

**4. e-Fatura alanları `account.move` tablosunu şişiriyor**
10+ alan eklendi, muhasebe fişi kayıtlarında hepsi NULL kalıyor.
Ayrı `efatura.log` modeli olmalıydı.

**5. Gelen fatura eşleme altyapısı yok**
Sadece başlık bilgisi alınıyor. Ürün, birim, vergi, muhasebe hesabı
eşlemesi yok. Bekletme kuyruğu yok.

**6. Gelen fatura cari ve ürün eşleme ekranı yok**
Şunlar geliştirilmeli:
- VKN ile otomatik cari eşleme; bulunamazsa önce ticari unvana fuzzy match,
  sonra "Cari Kart Aç" butonu ile gelen fatura bilgileri forma dolu gelsin
- Alt cari / şube seçimi: Ana cari bulununca fatura adresli alt cariler
  listelenmeli, kullanıcı seçmeli
- VKN unique constraint: Ana carilerde VKN tekrarı engellenmeli (`@api.constrains`),
  alt cariler (parent_id dolu) aynı VKN'i taşıyabilmeli
- Birden fazla ana cari aynı VKN ile kayıtlıysa eşleme ekranına düşmeli,
  `limit=1` ile sessizce ilki alınmamalı
- `rapidfuzz` / `difflib` ile skor bazlı otomatik ürün eşleme
  (%85+ otomatik, %60-85 öneri, <%60 manuel)
- Öğrenen eşleme tablosu (`efatura.product.mapping`) — bir kez eşlendi mi
  bir daha sorulmasın
- Toplu onay ekranı
- Tedarikçi bazlı kural motoru (ör: "TR- önekini kaldır, sonra eşleştir")
- Eşleme istatistikleri (tedarikçi bazlı otomatik eşleşme oranı)

**7. Kredi notu (iade faturası) e-Fatura akışına dahil değil**
`out_refund` kayıtları `super().action_post()` ile normal Odoo akışına
gönderiliyor. GİB'te iade faturası ayrı bir süreç; `action_post()` override'ına
`out_refund` dahil edilmeli, UBL'de `InvoiceTypeCode` olarak `IADE` gönderilmeli.

**8. Savepoint sonrası Sovos gönderim başarılı ama Odoo DB yazımı başarısız**
Sovos'a gönderildikten sonra Odoo DB yazımında hata olursa savepoint geri alınır,
numara serbest kalır. Ama GİB artık o numarayı biliyor. Bir sonraki gönderimde
aynı numara → 1104 hatası. Bu edge case yönetilmiyor.

**9. VKN format kontrolü yok**
`vat` alanına harf veya yanlış uzunlukta değer girilebiliyor. VKN için 10 hane
sayısal, TCKN için 11 hane sayısal kontrolü (`@api.constrains`) eklenmeli.

**10. XML önizlemesi `ir.attachment` olarak saklanmıyor**
Validasyon hatalarında XML chatter'a düz metin olarak yazılıyor.
`ir.attachment` olarak saklanmalı; kullanıcı isterse indirebilmeli, DB şişmemeli.

**11. `x_sovos_test_mode` alan adı yanıltıcı**
`True` = test ortamı, `False` = üretim. Alan adı `x_sovos_live_mode` veya
`x_sovos_production_ready` olmalıydı. Yeni developer yanlış anlayabilir.
