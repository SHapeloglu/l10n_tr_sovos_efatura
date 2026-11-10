# task.md — l10n_tr_sovos_efatura Görevleri

## 🔜 Sıradaki

- [ ] **DNS + SSL sertifika yenileme (sunucu, modül dışı)** — 7 sertifika süresi dolmuş/dolacak; sebep: alt alan adlarının A kaydı yok (NXDOMAIN). 2026-10-06'da `certbot renew` denendi → 7 hata (beklenen; DNS henüz eklenmedi)
  - [ ] Hangi alt alan adlarının hâlâ kullanıldığına karar ver (özellikle eski `odoo-test.olap.com.tr`)
  - [ ] **mirahosting** paneli (`olap.com.tr`): A kaydı `odoo18-prod` → 95.111.242.96, `odoo18-test` → 95.111.242.96
  - [ ] **Wix** paneli (`dehateknikservis.com`, Domains → DNS Records → A): `api`, `fretflow` → 95.111.242.96
  - [ ] **webdehasi** paneli (`powerbiegitimi.com`): `erpopenpy`, `nexmeet` → 95.111.242.96
  - [ ] Yayılımı doğrula — her satırda 95.111.242.96 görünmeli (görünmeden certbot çalıştırma; Let's Encrypt saatte 5 başarısız doğrulama sınırı):
        `for d in odoo18-prod.olap.com.tr odoo18-test.olap.com.tr api.dehateknikservis.com fretflow.dehateknikservis.com erpopenpy.powerbiegitimi.com nexmeet.powerbiegitimi.com; do printf "%-34s %s\n" $d "$(dig +short A $d @8.8.8.8)"; done`
  - [ ] Sertifikaları yenile: `certbot renew && systemctl reload nginx && certbot certificates | grep -E "Certificate Name|Expiry"`
  - [ ] Kullanılmayan alan adları: `certbot delete --cert-name <ad>` + ilgili nginx site dosyasını `sites-enabled`'dan kaldır → `nginx -t && systemctl reload nginx`
  - [ ] Tarayıcıdan `https://odoo18-prod.olap.com.tr` girişini doğrula (sertifika uyarısı olmamalı)
- [ ] **Güvenlik (sunucu, modül dışı):** VNC 5901 tüm arayüzlerde dinliyor (UFW ile dışarıdan kapalı) — durdurulsun mu, yoksa yalnızca localhost'a mı bağlansın, kullanıcı kararı bekleniyor (2026-11-10). Ollama 11434 artık dışarıya dinlemiyor; 8090 ve 8080 kuralı/dinleyicisi yok.
- [ ] `odoo18-test` autosleep: 5 dk boşta kalınca durduruluyor (`/opt/autosleep`). Otomatik uyandırma mı, istisna mı, yoksa kapalı mı kalsın — kullanıcı kararı
- [x] `sovos_ci_test` geçici DB'sini sil (2026-11-09 silindi; test sonrası temizlik)
- [x] Gelen fatura testleri temiz DB'de geçiyor: `setUp`'ta TRY aktifleştirildi → 302 test, 0 hata (2026-11-09, PR #6)
- [x] Sunucu güvenliği (2026-11-09/10): 1433 ve 8090 kuralları silindi; fail2ban sshd aktif (ban yok). `odoo18-test`'in durmasının nedeni autosleep olarak doğrulandı (5 dk boşta). Root `claude` süreçleri kullanıcıya ait, dokunulmuyor. Disk %88 (2026-11-10)
- [ ] SOAP şema karşılaştırması (2026-11-09, yalnızca analiz — kod değişmedi): resmi örnek XSD (`ClientEInvoiceServicesTypes-2.xsd`) `targetNamespace="http:/fitcons.com/eInvoice/"`, operasyonlar `getUBLListRequest`, `sendUBLRequest`, `getInvoiceStatusRequest`, `getEnvelopeStatusRequest`, `getInvResponsesRequest`, `getUBLRequest`… Kod (`services/sovos_invoice_service.py`) `http://einvoice.fitbulut.com/` ad alanı ve `GetUblList`, `SendUBL`, `GetEnvelopeStatus`, `GetInvResponses` adlarını kullanıyor; `sovos_archive_service.py` da farklı ad alanı. Hangisinin gerçek Sovos servisi olduğu test hesabıyla WSDL alınarak doğrulanmadan kod değiştirilmemeli. Doğrulama sonrası ya kodu XSD'ye göre güncelle ya da örnek istemcinin hangi ürüne ait olduğunu netleştir.
- [ ] Prod Sovos kurulumu: test sonuçlarından ve gerçek Sovos testinden sonra karar (`olap_prod` boş Odoo kurulumu; yedek `/opt/odoo/backups/olap_prod_pre_sovos_install_20261108_1247.dump`)

- [ ] **Prod DB'de modül durumu:** `olap_prod`'da `l10n_tr_sovos_efatura` `uninstalled` (2026-11-10 doğrulandı); prod'da kullanılacaksa önce `olap_prod` yedeği, sonra `-i l10n_tr_sovos_efatura` (kullanıcı onayıyla, Sovos şirket ayarları + test modu açık başla)
- [ ] Prod'da ilk gerçek gönderim + cron çalışmalarını logdan izle; sunucu kopyasını git ile yönetilir hale getir
- [ ] (İsteğe bağlı) Hata yolunda doğrulama XML eki / `x_validation_errors` rollback'te kayboluyor; kalıcı olması istenirse hata sonrası ayrı bir 'hata raporu' adımı tasarla (ayrı cursor kilitlenme riski nedeniyle reddedildi)
- [ ] **⚠ SOAP katmanı resmi şemayla uyuşmuyor (prod öncesi şart):** `kaynaklar/turkey-cloud-sample-api-client-main.zip` → `ClientEInvoiceServicesTypes-2.xsd`: ad alanı `http:/fitcons.com/eInvoice/`, `getUBLListRequest(Identifier, VKN_TCKN, UUID*, DocType, Type, Parameters*, FromDate, ToDate)`, `getUBLRequest`, `sendUBLRequest(VKN_TCKN, SenderIdentifier, ReceiverIdentifier, DocType, Parameters*, DocData)`, kimlik HTTP Basic. `sovos_invoice_service.py` farklı ad alanı (`http://einvoice.fitbulut.com/`) ve gövdede `REQUEST_HEADER`/`USERNAME`/`PASSWORD` kullanıyor; gerçek servisle hiç denenmedi (`odoo18-test`'te Sovos kullanıcısı / Sovos UUID'li fatura yok). Sovos test hesabı + güncel doküman al → `test_connection` → gerekirse tüm SOAP metodlarını şemaya göre yeniden yaz (e-Arşiv servisi de kontrol edilmeli)
- [x] 18.0.8.0.7 sunucuya kuruldu: `odoo18-test` DB `installed|18.0.8.0.7`, imaj içeriği 2026-11-08 incelemesinde repoyla aynı bulundu (2026-11-10'da tekrar kontrol edilmedi). Canlı `/opt/odoo/custom_addons` kopyası Odoo tarafından kullanılmıyor, md kopyalarını güncellemek gerekmiyor
- [ ] (Küçük) `efatura.product.mapping.find_mapping` `=ilike` kullanıyor: açıklamadaki `%`/`_` joker gibi davranır, Türkçe `ı/I`–`i/İ` harf eşlemesi yapılmaz. Joker karakterleri kaçışla veya Python'da `casefold` karşılaştırması yap
- [ ] `l10n_tr_sovos_efatura.bak_20260628` yedeğinin gerekliliğini kullanıcıyla değerlendir

## 🚧 Devam Eden

_(şu anda boş)_

## ✅ Tamamlanan
- [x] PR #8 (SOAP şema karşılaştırma notu, yalnızca `task.md`) `main`'e squash ile birleştirildi (2026-11-10)
- [x] Markdown dosyaları güncellendi: `CLAUDE.md`, `task.md`, `README.md` (2026-11-10)
- [x] Eşleme sihirbazı satırları: `default_get` faturanın ürün satırlarından wizard satırı üretiyor (satırdaki ürün ya da `IncomingMatcher.find_product` önerisi, cron'un eşleme notu açıklamadan ayıklanıyor); satır güveni yüzde (0–100). Pasif döviz: `_find_currency` `active_test=False` ile arıyor; pasif ya da tanımsız para biriminde fatura 'pending' + chatter notu (tanımsızda şirket para birimi). 5 yeni test, 302 testin tamamı geçti → 18.0.8.0.7 (2026-10-07)
- [x] Gelen fatura cron'u: `get_inbound_list()` tarihsiz çağrısı düzeltildi — `x_sovos_last_fetch_date`'ten bugüne (Europe/Istanbul) gün gün GetUblList, ilk çalışmada son 7 gün, liste hatası / işlenemeyen fatura olan gün sonraki çalışmada tekrar, fatura başına savepoint, FromDate/ToDate `xs:dateTime`; testlerde `get_inbound_list` `autospec=True`, `test_cron` artık `get_invoice_ubl`'ı da yamalıyor; 297 test geçti → 18.0.8.0.6 (2026-10-06)
- [x] Gelen fatura testleri: `tests/test_incoming.py` — UBL parser (XXE dahil), eşleme motoru (VKN / unvan benzerliği / öğrenen tablo / UBL kodu / kural + difflib eşikleri), vergi-birim-gider hesabı, öğrenen tablo kısıtları, uçtan uca senkron (matched_auto / review / pending, döviz, UBL hatası), eşleme sihirbazı; `sovos_ci_test`'te 288 testin tamamı geçti (2026-10-06)
- [x] PR #1 (v8 + güvenlik + Odoo 18 uyumu, 18.0.8.0.5) `main`'e birleştirildi (2026-10-06)
- [x] Odoo conf: `http_interface = 127.0.0.1`, `proxy_mode = True`, yeni `admin_passwd` — nginx üzerinden 200 (2026-10-06)
- [x] PostgreSQL 5432 ufw kuralı 4 IP'ye daraltıldı; pg_hba `host` → `hostssl` (2026-10-06)
- [x] prod/test conf: `db_name` + anchor'lı `dbfilter` + `list_db = False` — servisler arası çapraz cron çalışması ve DB yöneticisi kapatıldı (2026-10-06)
- [x] `odoo18-prod` 18.0.8.0.5 koduyla yeniden başlatıldı, hata yok (2026-10-06)
- [x] Sunucu klasörü 18.0.8.0.5'e güncellendi, `odoo18-test` DB `-u` başarılı (2026-10-06)
- [x] Modül testleri temiz DB'de (`sovos_ci_test`) tamamen geçiyor — 18.0.8.0.5, 229 test (2026-10-06)

- [x] 2026-10-05 — Sunucudaki v8 repoya alındı (18.0.8.0.0 ham commit); gizli bilgi taraması temiz; SOAP kimlik bilgisi XML kaçışı ve gelen faturada XXE önlemi eklendi → 18.0.8.0.1; GİB şemaları `.gitignore`'a alındı (`setup_schemas.sh` ile kurulum); `kaynaklar/setup.exe` ve bozuk adlı xlsx kopyası çıkarıldı
- [x] 2026-10-05 — Repo kontrolleri: `.gitignore` eklendi, `.pyc` takipten çıkarıldı; `tests/test_ubl_validator.py` sözdizimi hatası (2 yer) düzeltildi; Sovos kullanıcı/şifresi SOAP gövdesinde XML kaçışlı (v8 taşınırken aynı düzeltme kontrol edilmeli)
- [x] 2026-10-05 — Çalışma dosyaları kod okunarak yeniden yazıldı; repo (v6) ile canlı kopya (v8) farkı tespit edildi
- [x] 2026-06-23 — (yalnız sunucuda) v8: ürün eşleme modeli, XPath iş kuralları, şema kurulum betiği
- [x] 2026-06-07 → 06-11 — v6 Final: XSD/Schematron, atomik numara, tam GİB durum kodları, cron bildirimi, testler
