# 🧾 l10n_tr_sovos_efatura

**Odoo 18 Community × Sovos e-Fatura / e-Arşiv Entegrasyon Modülü**

[![Odoo](https://img.shields.io/badge/Odoo-18.0%20Community-714B67?logo=odoo)](https://www.odoo.com)
[![Versiyon](https://img.shields.io/badge/Versiyon-6.0--Final-brightgreen)](.)
[![Lisans](https://img.shields.io/badge/Lisans-LGPL--3-blue)](LICENSE)
[![GİB](https://img.shields.io/badge/GİB-UBL--TR%202.1-orange)](https://ebelge.gib.gov.tr)

> **Teknik Entegrasyon Spesifikasyonu v6.0 — Haziran 2026 — Final**  
> Satış + Alış + Muhasebe + PDF Arşivi + Kur Farkı + XSD/Schematron Validasyon + Atomik Fatura Numarası

---

## 📋 İçindekiler

- [Genel Bakış](#-genel-bakış)
- [Özellikler](#-özellikler)
- [Kapsam Dışı](#-kapsam-dışı)
- [Sistem Mimarisi](#-sistem-mimarisi)
- [Kurulum](#-kurulum)
- [Yapılandırma](#-yapılandırma)
- [Modül Yapısı](#-modül-yapısı)
- [UBL-TR Validasyon](#-ubl-tr-validasyon)
- [Atomik Fatura Numarası](#-atomik-fatura-numarası)
- [Toplu Gönderim](#-toplu-gönderim)
- [Fatura Önizleme](#-fatura-önizleme)
- [e-Fatura Dashboard](#-e-fatura-dashboard)
- [GİB Durum Kodları](#-gib-durum-kodları)
- [İptal ve Yeniden Gönderim](#-i̇ptal-ve-yeniden-gönderim)
- [Zamanlanmış Görevler](#-zamanlanmış-görevler)
- [Güvenlik](#-güvenlik)
- [Test Planı](#-test-planı)
- [Referanslar](#-referanslar)

---

## 🌟 Genel Bakış

Bu modül, **Odoo 18 Community** üzerinde çalışan işletmelerin **Sovos** (GİB Özel Entegratörü) üzerinden yasal e-Fatura ve e-Arşiv yükümlülüklerini eksiksiz yerine getirmesini sağlar.

| Özellik | Detay |
|---|---|
| **Odoo Sürümü** | 18.0-20260528 Community (self-hosted) |
| **Entegratör** | Sovos — GİB Özel Entegratörü |
| **Modül Adı** | `l10n_tr_sovos_efatura` |
| **Spesifikasyon** | v6.0 — Haziran 2026 — Final |
| **v5 → v6 Yenilikleri** | XSD/Schematron validasyon, tam GİB durum kodu listesi, atomik fatura numarası, 1103/1104 akışı, cron başarısızlık bildirimi |

> **Sektör Referansları:** Logo Tiger, Mikro, ETA ve Vega kapsamlı araştırılmış; kritik alanlarda (Schematron validasyon, atomik numara, cron bildirimi) sektörden daha güvenli yaklaşımlar benimsenmiştir.

---

## ✅ Özellikler

| # | Özellik | Açıklama |
|---|---|---|
| 1 | **e-Fatura Gönderme** | `out_invoice` → Sovos → GİB — TİCARİFATURA / TEMELFATURA |
| 2 | **e-Arşiv Gönderme** | GİB kayıtsız alıcı → ArchiveService + e-posta |
| 3 | **Alış Fatura Alma** | GİB → Sovos → Odoo `in_invoice` + muhasebe fişi |
| 4 | **Toplu Gönderim** | Alıcıya göre sıralı + ardışık güvenli gönderim |
| 5 | **PDF Arşivi** | Sovos'tan PDF + toplu ZIP indirme |
| 6 | **Fatura Tasarımı** | Sovos portal şablonu — şirket bazlı |
| 7 | **Kur Farkı Faturası** | Wizard — manuel tetikli |
| 8 | **TİCARİFATURA KABUL/RED** | Uygulama yanıtı + 8 gün uyarısı |
| 9 | **Çok Şirket** | Her şirket kendi credentials — tek cron döngüsü |
| 10 | **VKN Cache** | Akıllı güncelleme — 30 günden eski veya boş |
| 11 | **İptal Akışları** | e-Arşiv API, TEMELFATURA portal, statü matrisi |
| 12 | **Tekrar Gönderim** | Teknik: aynı UUID — İçerik: iptal + yeni fatura |
| 13 | **e-Fatura Dashboard** | Durum bazlı filtrelenmiş görünümler |
| 14 | **Fatura Önizleme** | Gönderim öncesi HTML render + validasyon |
| 15 | **Bağlantı Testi** | InvoiceService + ArchiveService test butonu |
| 16 | **UBL-TR Validasyon** | Gönderim öncesi XSD + Schematron — Logo Tiger yaklaşımı |
| 17 | **Atomik Fatura Numarası** | Numara çakışma riski sıfır — rezervasyon mekanizması |
| 18 | **Cron Başarısızlık Bildirimi** | Cron çökmesi → admin bildirimi |

---

## 🚫 Kapsam Dışı

Aşağıdaki özellikler farklı GİB servisi veya farklı yasal süreç gerektirdiğinden bu modül kapsamında **değildir**:

| Kapsam Dışı | Neden |
|---|---|
| e-İrsaliye | Ayrı GİB uygulaması, sevkiyat UBL şeması farklı |
| e-SMM | Farklı belge türü, ayrı GİB servisi |
| e-Defter | Aylık XBrl gönderimi, tamamen ayrı süreç |
| e-Mutabakat / Ba-Bs | Ayrı GİB servisi, beyanname bağlantısı |
| e-Beyanname | KDV, muhtasar — tamamen farklı GİB sistemi |
| e-Müstahsil Makbuzu | Tarımsal alım, ayrı belge türü |
| Otomatik TCMB Kur Çekimi | Ayrı API entegrasyonu |
| e-Ticaret / Pazaryeri | Otomatik sipariş→fatura akışı ayrı kapsam |

---

## 🏗 Sistem Mimarisi

### Katmanlar

| Katman | Bileşen | Rol |
|---|---|---|
| ERP | Odoo 18 Community | Fatura, muhasebe, VKN cache, dashboard, validasyon |
| Adaptör | `l10n_tr_sovos_efatura` | UBL-TR, API, XSD/Schematron, atomik numara, durum |
| Entegratör | Sovos Bulut | İmzalama, GİB iletimi, e-posta, PDF, 10 yıl saklama |
| Yasal Otorite | GİB | Mükellef listesi, teslim, onay/red |

### Satış Faturası Akışı

```
action_post() (tekil) VEYA 'Toplu Gönder' (çoklu)
  → Ön kontroller: VKN, tarih, credentials, email
  → VKN Cache: dolu → cari karttan / boş → canlı sorgu
  → Senaryo: cari x_default_scenario / kullanıcı seçimi
     GİB kayıtsız + TİCARİFATURA → uyarı → onay
  ── ATOMİK NUMARA REZERVASYONU ──
  → ir.sequence.next_by_id() → numara REZERVE edilir
  → uuid4() üret
  ── UBL-TR VALİDASYON ──
  → ubl_builder.build(invoice, uuid, numara)
  → xsd_validate(xml)        → hata varsa numara SERBEST, inline bant, dur
  → schematron_validate(xml) → hata varsa numara SERBEST, inline bant, dur
  ────────────────────────────────
  → {uuid}.xml → {uuid}.zip → base64
  → e-Fatura:  InvoiceService.SendUBL()
     e-Arşiv:  ArchiveService.SendInvoice(email=partner.email)
  → BAŞARILI:  UUID + EnvelopeUUID kaydet, status='sent', numara ONAY
  → BAŞARISIZ: numara SERBEST bırak, inline bant, hata logu
  → ir.cron:   akıllı sıklıkla durum takibi
```

---

## 🚀 Kurulum

### Gereksinimler

- Odoo 18.0 Community (self-hosted)
- Python 3.10+
- `lxml` kütüphanesi (XSD + Schematron validasyon)

### Adımlar

1. Modülü `addons` dizinine kopyalayın:
   ```bash
   cp -r l10n_tr_sovos_efatura /opt/odoo/addons/
   ```

2. GİB şema dosyalarını yerleştirin (`services/schemas/` dizinine):
   - `UBL-Invoice-2.1.xsd`
   - `UBL-TR_Main_Schematron.xml`
   - `VERSION` (şema versiyon takibi)

   > Şema dosyaları: https://ebelge.gib.gov.tr/dosyalar/kilavuzlar/e-FaturaPaket.zip

3. Odoo'yu yeniden başlatın ve modülü yükleyin:
   ```bash
   ./odoo-bin -u l10n_tr_sovos_efatura -d <veritabani_adi>
   ```

---

## ⚙️ Yapılandırma

**Ayarlar → Muhasebe → Sovos Yapılandırma** bölümünden:

- **e-Fatura credentials**: `x_sovos_invoice_user` / `x_sovos_invoice_pass`
- **e-Arşiv credentials**: `x_sovos_archive_user` / `x_sovos_archive_pass`
- **Test modu**: `x_sovos_test_mode = True` (GİB'e gerçek iletim yapılmaz)
- **Şablon ID**: `x_sovos_template_id` (Sovos portal şablonu, şirket bazlı)

### Bağlantı Testi

Yapılandırma sayfasında iki ayrı **"Test Et"** butonu mevcuttur:

- 🟢 **e-Fatura Bağlantısını Test Et** → InvoiceService kimlik doğrulama
- 🟢 **e-Arşiv Bağlantısını Test Et** → ArchiveService kimlik doğrulama

---

## 📁 Modül Yapısı

```
l10n_tr_sovos_efatura/
├── __manifest__.py
├── models/
│   ├── account_move.py         # action_post, atomik numara, toplu gönderim, önizleme
│   ├── res_company.py          # Sovos credentials + ayarlar + bağlantı testi
│   ├── res_partner.py          # x_efatura_type, x_default_scenario, x_vergi_dairesi
│   ├── product_uom.py          # x_ubl_code
│   └── sovos_sync.py           # ir.cron + başarısızlık bildirimi
├── services/
│   ├── sovos_invoice_service.py
│   ├── sovos_archive_service.py
│   ├── ubl_builder.py
│   ├── ubl_validator.py        # XSD + Schematron validasyon
│   └── schemas/                # GİB şema dosyaları
│       ├── UBL-Invoice-2.1.xsd
│       ├── UBL-TR_Main_Schematron.xml
│       └── VERSION             # Şema versiyon takibi
├── wizards/
│   ├── resend_invoice_wizard.py
│   ├── cancel_invoice_wizard.py
│   └── kur_farki_wizard.py
├── views/
│   ├── account_move_views.xml
│   ├── account_move_list_views.xml
│   ├── res_company_views.xml
│   └── res_partner_views.xml
├── data/
│   ├── ir_cron_data.xml
│   └── ir_sequence_data.xml
└── security/ir.model.access.csv
```

### `account.move` Özel Alanlar

| Alan | Tip | Açıklama |
|---|---|---|
| `x_sovos_uuid` | Char(36) | UUID — satış/alış ayrı unique constraint |
| `x_sovos_envelope_uuid` | Char(36) | Zarf UUID |
| `x_efatura_status` | Selection | `draft/sending/sent/accepted/rejected/cancelled/error` |
| `x_efatura_type` | Char | `efatura/earsiv` — gönderimde cari karttan kopyalanır |
| `x_efatura_scenario` | Selection | `TICARIFATURA/TEMELFATURA/EARSIVFATURA` |
| `x_efatura_send_date` | Datetime | GİB iletim tarihi |
| `x_efatura_error_msg` | Text | Kullanıcı dostu hata mesajı |
| `x_cust_inv_id` | Char(50) | Odoo fatura no → Sovos CUST_INV_ID |
| `x_inv_response_status` | Selection | `beklemede/kabul/red` |
| `x_inv_response_deadline` | Date | `invoice_date + 8 gün` |
| `x_kur_farki` | Boolean | Kur farkı faturası işareti |
| `x_reserved_number` | Char(50) | Rezerve edilen fatura numarası |
| `x_number_status` | Selection | `reserved/confirmed/released` |
| `x_validation_errors` | Text | Son XSD/Schematron hata detayları |

---

## 🔍 UBL-TR Validasyon

GİB'e göndermeden önce **iki katmanlı zorunlu validasyon** uygulanır.

### Validasyon Katmanları

| Katman | Araç | Ne Yakalar? |
|---|---|---|
| 1. XSD | `lxml.etree.XMLSchema` | Zorunlu alan eksikliği, veri tipi hatası, hatalı namespace, tag hiyerarşisi |
| 2. Schematron | `lxml` + GİB Schematron dosyası | İş kuralı ihlalleri: tutar tutarsızlığı, oranlar, senaryo uyumsuzluğu |

```python
# services/ubl_validator.py
from lxml import etree
import os

XSD_PATH = os.path.join(os.path.dirname(__file__), 'schemas/UBL-Invoice-2.1.xsd')
SCH_PATH = os.path.join(os.path.dirname(__file__), 'schemas/UBL-TR_Main_Schematron.xml')

def validate(xml_bytes):
    # Katman 1: XSD
    xsd = etree.XMLSchema(etree.parse(XSD_PATH))
    doc = etree.fromstring(xml_bytes)
    if not xsd.validate(doc):
        errors = [str(e) for e in xsd.error_log]
        return False, 'XSD', errors

    # Katman 2: Schematron
    sch = etree.parse(SCH_PATH)
    transform = etree.XSLT(sch)
    result = transform(doc)
    failures = result.xpath('//svrl:failed-assert',
                           namespaces={'svrl': '...'})
    if failures:
        errors = [f.get('test') + ': ' + f.text for f in failures]
        return False, 'SCHEMATRON', errors

    return True, None, []
```

### Validasyon Hata Yönetimi

| Hata Türü | GİB Kodu Karşılığı | Odoo Davranışı |
|---|---|---|
| XSD hatası | 1101, 1132, 1160 | Numara serbest, inline kırmızı bant, teknik detay logda |
| Schematron hatası | 1150, 1170 | Numara serbest, inline kırmızı bant, kural adı gösterilir |
| Validasyon geçti | — | Sovos'a iletim başlar |

> **Şema Güncellemeleri:** GİB XSD ve Schematron dosyaları `services/schemas/` dizininde saklanır. GİB şema güncellemelerinde (yılda 1-2 kez) modül versiyonu yükseltilir ve Odoo güncelleme süreciyle otomatik dağıtılır.

---

## 🔒 Atomik Fatura Numarası

Ağ kesintisi senaryolarında numara çakışmasını (GİB hata kodu 1104) önlemek için **rezervasyon + commit** mekanizması kullanılır.

```python
# models/account_move.py — action_post() override
def action_post(self):
    # 1. Numara REZERVE et (DB'de kilitli)
    with self.env.cr.savepoint():  # PostgreSQL savepoint
        invoice_number = self.env['ir.sequence'].next_by_id(
            self.company_id.x_invoice_sequence_id.id
        )
        self.write({'x_reserved_number': invoice_number,
                    'x_number_status': 'reserved'})

    # 2. UUID üret + UBL oluştur + validasyon
    uuid = str(uuid4())
    xml = ubl_builder.build(self, uuid, invoice_number)
    valid, layer, errors = ubl_validator.validate(xml)
    if not valid:
        self._release_number(invoice_number)  # SERBEST bırak
        raise UserError(f'UBL validasyon hatası [{layer}]: {errors[0]}')

    # 3. Sovos'a gönder
    try:
        result = self._send_to_sovos(xml, uuid)
        self.write({'name': invoice_number,       # ONAY
                    'x_sovos_uuid': uuid,
                    'x_number_status': 'confirmed'})
    except Exception as e:
        self._release_number(invoice_number)      # SERBEST bırak
        raise UserError(f'Sovos gönderim hatası: {e}')
```

### Numara Durumları

| Durum | Açıklama | Sonraki Adım |
|---|---|---|
| `reserved` | Numara alındı, henüz gönderilmedi | Validasyon veya gönderim başarısız → `released` |
| `confirmed` | Sovos'a başarıyla iletildi | Kalıcı — değiştirilemez |
| `released` | Hata nedeniyle serbest bırakıldı | Sequence sayacı geri alınır* |

> **Not:** PostgreSQL sequence monoton artar — geri alınamaz. Serbest bırakılan numara "boş" kalır (VUK md.231 uyarınca normaldir). Sistem bu boşluğu loglar ve admin raporuna ekler.

---

## 📦 Toplu Gönderim

1. Fatura listesinden seçim → **"e-Fatura Olarak Gönder"**
2. Ön filtre: `POSTED` + henüz gönderilmemiş
3. Alıcı VKN'e göre sırala (cache avantajı)
4. Her fatura için: ön kontroller → VKN cache → atomik numara rezervasyonu → UBL üret → validasyon → Sovos gönder
5. Hata durumunda: numara serbest, bu fatura hata listesi, **diğerleriyle devam**
6. `500ms` bekleme (Sovos rate limit) | HTTP 429 → exponential backoff `2s→4s→8s`
7. Özet rapor: Gönderildi / Validasyon Hatası / Gönderim Hatası / Atlandı

---

## 👁 Fatura Önizleme

- Fatura formunda **"Faturayı Önizle"** butonu (POSTED, henüz gönderilmemiş)
- `ubl_builder.build()` çalışır — geçici UUID, GİB'e iletim yok
- XSD + Schematron validasyon çalışır — hata varsa **önizlemede gösterilir**
- UBL-TR XML → HTML render → Odoo modal içinde gösterilir
- "Kapat" veya "Gönder" butonu

> **Sektörden İyi:** Logo Tiger'da önizleme portal bağlantısı gerektirir. Bu modülde internet bağlantısı olmadan Odoo içinde çalışır; validasyon hataları önizlemede gösterilir.

---

## 📊 e-Fatura Dashboard

| Görünüm | Filtre Kriteri |
|---|---|
| Gönderildi — Yanıt Bekliyor | `x_efatura_status=sent` |
| Hata Var — Aksiyon Gerekli | `x_efatura_status=error` |
| Validasyon Hatası | `x_number_status=released AND x_validation_errors!=False` |
| 8 Gün Uyarısı | `x_inv_response_deadline <= today+1 AND x_inv_response_status=beklemede` |
| Red Edildi | `x_efatura_status=rejected` |
| Gelen — Partner Eşlenecek | `move_type=in_invoice AND partner_id=False` |
| Bu Ay Gönderildi | `x_efatura_status=accepted AND ay içinde` |

---

## 🚦 GİB Durum Kodları

### Zarf / Yapı Hataları — Tekrar Gönder (Aynı UUID)

| Kod | Açıklama | Akış |
|---|---|---|
| 1000 | Zarf kuyruğa eklendi | Bekle — cron takip |
| 1100 | Zarf işleniyor | Bekle |
| 1101 | XML/Yapı hatası | Aynı UUID düzelt + tekrar gönder |
| 1103 | Zorunlu alan boş | Fatura düzelt + aynı UUID tekrar gönder |
| 1104 | Numara tekrarı / benzersiz değil | ⚠️ İptal + yeni fatura |
| 1110 | ZIP dosyası değil | Aynı UUID tekrar gönder |
| 1130 | ZIP açılamadı | ZIP yeniden oluştur + tekrar gönder |
| 1133 | Zarf ID ve XML adı uyuşmuyor | UUID kontrolü + tekrar gönder |
| 1143 | Geçersiz versiyon | UBLVersionID kontrol (2.1) + tekrar gönder |
| 1150 | Schematron kontrol hatalı | Schematron log + fatura düzelt + tekrar gönder |
| 1160 | XML şema kontrolünden geçemedi | XSD log + fatura düzelt + tekrar gönder |
| 1163 | Zarf sistemde kayıtlı — mükerrer UUID | ⚠️ İptal + yeni fatura |
| 1210 | Alıcıda işlenemedi (1. deneme) | Aynı UUID tekrar gönder — iptal gerekmez |
| 1215 | 4 deneme başarısız | Admin bildirimi + manuel müdahale |
| 1230 | Alıcıda işlenemedi (devam) | Aynı UUID tekrar gönder |

### Başarı Kodları

| Kod | Açıklama | Odoo Davranışı |
|---|---|---|
| 1300 | Başarıyla tamamlandı | `status=accepted`, yeşil bant — **kesinlikle tekrar gönderme** |
| 1305 | Alıcı kabul etti | `x_inv_response_status=kabul` |
| 1310 | Alıcı reddetti | `x_inv_response_status=red`, turuncu bant |

### Hata Grupları Özeti

| Grup | GİB Kodları | Akış |
|---|---|---|
| Teknik hata | 1101,1103,1110–1132,1140–1143,1150,1160–1162,1170–1175,1210,1230 | Aynı UUID düzelt + tekrar gönder |
| İçerik hatası | 1104, 1163, RED | İptal + yeni fatura |
| İmza/Yetki | 1161, 1171, 1172 | Sovos teknik destek |
| Başarı | 1300, 1305 | Kesinlikle tekrar gönderme |

---

## 🔄 İptal ve Yeniden Gönderim

### e-Arşiv — Sovos API

```
Wizard → CancelInvoice(UUID) → başarılı → status='cancelled'
```
GİB portala gitme yok.

### TEMELFATURA — GİB Portal

```
Wizard: GİB portalı linki + 'GİB'de iptali tamamladım' checkbox zorunlu
Onay → status='cancelled' — sorumluluk kullanıcıya ait
```

### TİCARİFATURA İptal Matrisi

| Statü | İptal? |
|---|---|
| GİB'e Gönderilecek / İşlenemedi / Teknik Hata | ✅ Evet |
| Alıcıya Gönderildi (8 gün dolmamış) | ❌ Hayır — karşılıklı mutabakat |
| Kabul Edildi | ❌ Hayır |
| 8 gün geçmiş | ❌ Hayır — modül bloklar + hukuki uyarı |

---

## ⏰ Zamanlanmış Görevler

| Görev | Sıklık | Başarısız → | Gerekçe |
|---|---|---|---|
| Gelen Fatura Senkronizasyonu | 15 dk | Admin bildirim | Muhasebeci güncel bilgi bekler |
| e-Fatura Durum (InvoiceService) | 30 dk | Admin bildirim | Durum değişimi 15 dk'dan hızlı olmaz |
| e-Arşiv Durum (ArchiveService) | 30 dk | Admin bildirim | Ayrı servis — karıştırılmaz |
| TİCARİFATURA KABUL/RED | 1 saat | Admin bildirim | Yanıt günler içinde gelir |
| 8 Gün Uyarısı | Günlük | Admin bildirim | Günlük kontrol yeterli |
| VKN Cache Güncelleme | Günlük | Admin bildirim | 30 gün filtreli |

> **Sektörden İyi:** Logo Tiger'da cron hataları ayrı log ekranında gösterilir. Bu modülde cron hatası anında Odoo admin bildirimine düşer.

---

## 🔐 Güvenlik

- Sovos credentials: `password` widget — logda maskelenir
- TLS 1.2 minimum zorunlu
- UBL-TR XML: `/tmp`'de üretilir, gönderim sonrası silinir
- PDF + gelen XML: `ir.attachment`'ta saklanır
- Çok şirket: `with_company()` izolasyonu
- KVKK: staging ortamında VKN/ad-soyad anonimleştirilmeli
- API hata yanıtları: özet loglanır, kimlik bilgisi loglanmaz
- Schematron hata detayları: `x_validation_errors` alanında — sadece admin görür
- Atomik numara rezervasyon logu: admin raporuna dahil

---

## 🧪 Test Planı

Test ortamında `x_sovos_test_mode=True` — GİB iletimi yapılmaz. VKN'ler KVKK kapsamında anonimleştirilmeli.

<details>
<summary>34 Test Senaryosunu Görüntüle</summary>

| # | Senaryo | Beklenen | Doğrulama |
|---|---|---|---|
| 1 | Bağlantı testi — doğru credentials | Yeşil bildirim | Bildirim rengi |
| 2 | XSD validasyon — zorunlu alan eksik | Hata bandı, numara serbest | `x_number_status=released` |
| 3 | Schematron validasyon — kural ihlali | Hata bandı + kural adı | `x_validation_errors` |
| 4 | Validasyon geçen fatura | Sovos'a iletilir | `x_sovos_uuid` dolu |
| 5 | Fatura önizleme — validasyon hatası | Önizlemede hata gösterilir | Modal hata içeriği |
| 6 | Atomik numara — ağ kesintisi sim | Numara serbest, hata bandı | `x_number_status=released` |
| 7 | GİB kayıtlı alıcı satış | e-fatura, SendUBL | `x_sovos_uuid` |
| 8 | GİB kayıtsız alıcı satış | e-arşiv, ArchiveService | ArchiveService log |
| 9 | GİB kayıtsız + TİCARİFATURA | Uyarı kutusu | Uyarı gösterildi |
| 10 | `x_efatura_type` boş — yeni müşteri | Canlı sorgu → cache | `x_efatura_type_updated` |
| 11 | Sovos erişilemez + tip dolu | Cari karttan oku, devam | İş devam |
| 12 | Sovos erişilemez + tip boş | Inline hata bandı: bloke | Bant |
| 13 | Toplu 5 fatura | 5 UUID, 500ms bekleme, özet | Bekleme logu |
| 14 | Toplu — 1 validasyon hatası | Hata raporla, diğerleri devam | Özet rapor |
| 15 | HTTP 429 | Exponential backoff | Bekleme logu |
| 16 | 1103 hatası → düzelt → tekrar gönder | Aynı UUID, düzeltilmiş XML | UUID aynı |
| 17 | 1104 hatası | Admin bildirim, iptal + yeni | Bildirim |
| 18 | Cron başarısız — Odoo worker restart | Admin Odoo bildirimi | Bildirim alındı |
| 19 | VKN cache 30 gün eski | Yeniden sorgu | `x_efatura_type_updated` |
| 20 | VKN cache 10 günlük | Sorgulanmaz | Log |
| 21 | PDF indirme | `ir.attachment` PDF | Attachment dolu |
| 22 | Toplu PDF ZIP | ZIP | Tüm PDF'ler |
| 23 | Kur farkı wizard | Taslak, `x_kur_farki=True` | Alan |
| 24 | e-Arşiv iptali | `CancelInvoice → cancelled` | Sovos log |
| 25 | TEMELFATURA iptali | Wizard + checkbox + cancelled | Status |
| 26 | 8 gün geçmiş TİCARİFATURA iptal | Bloke + hukuki bant | Bant |
| 27 | TİCARİFATURA KABUL | ApplicationResponse | `x_inv_response_status` |
| 28 | 8 gün uyarısı cron | 7. gün e-posta | E-posta logu |
| 29 | Gelen fatura — partner bulundu | `in_invoice` + muhasebe fişi | TDHP |
| 30 | Gelen fatura — partner yok | Draft, partner boş | `partner_id` |
| 31 | Cron sıklığı | e-Fatura 30dk, KABUL/RED 1saat | `ir.cron interval` |
| 32 | Çok şirket cron | Her şirket ayrı + bildirim | Şirket A,B log |
| 33 | XSD şema doğrulaması | GİB XSD'ye uygun | lxml validate |
| 34 | Dashboard filtresi: Validasyon Hatası | Hatalı fatura listesi | Filtre |

</details>

---

## 📚 Referanslar

| Kaynak | URL |
|---|---|
| Sovos API | https://api.fitbulut.com/servis/#/eFatura |
| Sovos e-Fatura WS v2.3 | https://api.fitbulut.com/servis/assets/docs/Sovos%20Bulut%20e-Fatura%20WS%20API%20v2.3.zip |
| Sovos e-Arşiv WS v2.3 | https://api.fitbulut.com/servis/assets/docs/Sovos%20Bulut%20e-Arsiv%20Fatura%20WS%20API%20v2.3.zip |
| GİB e-Fatura Paketi (XSD+Schematron) | https://ebelge.gib.gov.tr/dosyalar/kilavuzlar/e-FaturaPaket.zip |
| 589 Sıra VUK Tebliği | 31.12.2025 tarih 33124 sayılı RG — e-Arşiv 2026 sınırları |
| GİB e-Belge | https://ebelge.gib.gov.tr |
| Logo Tiger Durum Kodları | https://www.logohizmetmerkezi.com/destek-dokumanlari/logo-e-fatura-hatasi-ve-cozumu.html |
| Sovos SDK (PHP) | https://github.com/ahmeti/sovos |
| Odoo 18 Dış API | https://www.odoo.com/documentation/18.0/developer/reference/external_api.html |

---

<div align="center">

**Odoo 18 Community × Sovos e-Fatura Entegrasyon Modülü**  
v6.0 — Haziran 2026 — Final  

*Logo Tiger, Mikro, ETA ve Vega karşılaştırması + tam GİB durum kodu listesi + XSD/Schematron validasyon + atomik numara*

</div>
