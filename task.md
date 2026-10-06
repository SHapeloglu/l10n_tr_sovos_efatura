# task.md — l10n_tr_sovos_efatura Görevleri

## 🔜 Sıradaki

- [ ] **Sunucu (modül dışı):** `odoo18-prod/test.olap.com.tr` SSL sertifikaları 2026-09-23'ten beri süresi dolmuş; DNS çözülmüyor, certbot 7 yenileme hatası
- [ ] **Güvenlik (sunucu, modül dışı):** Ollama 11434 (auth yok, herkese açık), VNC 5901, Docker 8090 (ufw'yi atlar), 8080 — kullanıcı kim/nereden kullanıldığını bildirecek
- [ ] `sovos_ci_test` geçici DB'sini sil (prod'dan görünüyor)

- [ ] Prod'da ilk gerçek gönderim + cron çalışmalarını logdan izle; sunucu kopyasını git ile yönetilir hale getir
- [ ] (İsteğe bağlı) Hata yolunda doğrulama XML eki / `x_validation_errors` rollback'te kayboluyor; kalıcı olması istenirse hata sonrası ayrı bir 'hata raporu' adımı tasarla (ayrı cursor kilitlenme riski nedeniyle reddedildi)
- [ ] v8 yeni özellikleri için test yaz: `ubl_parser`, `incoming_matcher`, `efatura.product.mapping`, gelen fatura eşleme sihirbazı (şu an testi yok)
- [ ] `l10n_tr_sovos_efatura.bak_20260628` yedeğinin gerekliliğini kullanıcıyla değerlendir

## 🚧 Devam Eden

_(şu anda boş)_

## ✅ Tamamlanan
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
