# architect.md — l10n_tr_sovos_efatura Mimarisi

## Katmanlar

| Katman | Bileşen | Rol |
|---|---|---|
| ERP | Odoo 18 Community (`account`, `mail`) | Fatura, muhasebe, dashboard |
| Adaptör | bu modül | UBL-TR üretimi, doğrulama, atomik numara, Sovos API, durum yönetimi |
| Entegratör | Sovos bulut (InvoiceService, ArchiveService) | İmza, GİB iletimi, e-posta, PDF, saklama |
| Otorite | GİB | Mükellef listesi, teslim, kabul/red |

## Satış Faturası Akışı

```
action_post() veya Toplu Gönder
 → ön kontroller (VKN, tarih, credentials, e-posta)
 → VKN cache (res.partner x_efatura_type; boş/30 günden eski → canlı sorgu)
 → senaryo (TEMELFATURA / TİCARİFATURA; kayıtsız alıcı → e-Arşiv)
 → ATOMİK NUMARA: ir.sequence rezerve + uuid4
 → ubl_builder.build() → ubl_validator (XSD + XPath tabanlı GİB iş kuralları)
      hata → numara serbest, form üstü hata bandı
 → {uuid}.xml → {uuid}.zip → base64
 → e-Fatura: InvoiceService.SendUBL   | e-Arşiv: ArchiveService.SendInvoice
 → başarı: UUID/EnvelopeUUID kaydet, status=sent, numara onay | hata: numara serbest
 → cron'lar durum takibi
```

## Modül Yapısı

| Klasör / dosya | İçerik |
|---|---|
| `models/account_move.py` | Gönderim, önizleme, toplu gönderim (rate limit + 429 backoff), `_process_gib_status`, PDF |
| `models/res_company.py` | Sovos credentials, test modu, bağlantı testi |
| `models/res_partner.py` | VKN cache alanları, varsayılan senaryo |
| `models/product_uom.py` | Birim → UBL-TR birim kodu eşlemesi |
| `models/sovos_sync.py` (`sovos.sync`) | Cron giriş noktaları; `_cron_run_for_all_companies` her şirketi ayrı dener, hata → `_notify_admin` |
| `services/ubl_builder.py`, `ubl_validator.py` | UBL-TR 2.1 XML üretimi ve doğrulama |
| `services/sovos_invoice_service.py`, `sovos_archive_service.py` | SOAP/HTTP istemcileri |
| `services/constants.py` | GİB durum kodu setleri (tek kaynak) |
| `models/efatura_product_mapping.py` (`efatura.product.mapping`) | Gelen faturada tedarikçi açıklaması → Odoo ürünü öğrenen eşleme tablosu |
| `services/ubl_parser.py` | Gelen UBL-TR XML → dict (XXE korumalı parser) |
| `services/incoming_matcher.py` | Gelen fatura partner/ürün eşleme motoru |
| `wizards/` | İptal, yeniden gönder (aynı UUID / yeni fatura), kur farkı, gelen fatura toplu eşleme/onay (`sovos.incoming.match.wizard`) |
| `data/ir_cron_data.xml` | Cron'lar (aşağıda) |
| `data/ir_sequence_data.xml` | Fatura numara serileri |
| `views/` | Şirket, cari, fatura formu ve liste/dashboard görünümleri |
| `tests/` | 11 test dosyası: account_move, accounting, atomic_number, cron, gib_status, multicompany, ubl_builder, ubl_validator, vkn_cache, wizards, extras |

## Zamanlanmış Görevler

| Cron | Sıklık |
|---|---|
| Gelen fatura senkronizasyonu | 15 dk |
| e-Fatura giden durum takibi (InvoiceService) | 30 dk |
| e-Arşiv giden durum takibi (ArchiveService) | 30 dk |
| TİCARİFATURA kabul/red takibi | 1 saat |
| 8 gün yanıt süresi uyarısı | günlük |
| VKN cache güncelleme (30 gün) | günlük |

## Mimari Kararlar

- **Gönderim öncesi yerel doğrulama**: GİB 1150/1160 reddini beklemeden hatayı kullanıcıya göstermek (Logo Tiger yaklaşımı).
- **Atomik numara rezervasyonu**: başarısız gönderimlerde numara boşluğu/çakışması olmasın.
- **VKN cache**: her faturada canlı mükellef sorgusu yapmamak; Sovos erişilemezse cache ile devam.
- **v6 → v8**: Saxon (XSLT 2.0) bağımlılığı yerine lxml XPath ile GİB iş kuralları; Schematron dosyaları yalnız referans.
- **GİB şemaları repoda değil**: `setup_schemas.sh` ile sunucuya kurulur, sürüm `services/schemas/VERSION` ile izlenir.
- **Gelen fatura eşleme**: VKN ile partner → öğrenen tablo / tedarikçi ürün kodu → difflib benzerliği (≥0.85 otomatik, 0.60–0.84 öneri, <0.60 manuel kuyruk).
