# task.md — l10n_tr_sovos_efatura Görevleri

## 🔜 Sıradaki

- [ ] **Canlı v8'i repoya al** (`/opt/odoo/custom_addons/l10n_tr_sovos_efatura` → bu repo), README ve manifest açıklamasını v8'e güncelle; sunucu kopyasını git ile yönetilir hale getir — kullanıcı onayıyla
- [ ] `services/schemas/` için karar: GİB şema dosyaları repoya mı (lisans/boyut), yoksa `setup_schemas.sh` ile kurulum mu
- [ ] v8 taşınırken: gizli bilgi taraması, SOAP kimlik bilgisi XML kaçışı, test dosyalarının sözdizimi kontrolü
- [ ] `kaynaklar/setup.exe` ve zip'in repoda kalıp kalmayacağına karar ver
- [ ] Test DB'de `--test-tags /l10n_tr_sovos_efatura` çalıştırıp sonucu kaydet
- [ ] `l10n_tr_sovos_efatura.bak_20260628` yedeğinin gerekliliğini kullanıcıyla değerlendir

## 🚧 Devam Eden

_(şu anda boş)_

## ✅ Tamamlanan

- [x] 2026-10-05 — Repo kontrolleri: `.gitignore` eklendi, `.pyc` takipten çıkarıldı; `tests/test_ubl_validator.py` sözdizimi hatası (2 yer) düzeltildi; Sovos kullanıcı/şifresi SOAP gövdesinde XML kaçışlı (v8 taşınırken aynı düzeltme kontrol edilmeli)
- [x] 2026-10-05 — Çalışma dosyaları kod okunarak yeniden yazıldı; repo (v6) ile canlı kopya (v8) farkı tespit edildi
- [x] 2026-06-23 — (yalnız sunucuda) v8: ürün eşleme modeli, XPath iş kuralları, şema kurulum betiği
- [x] 2026-06-07 → 06-11 — v6 Final: XSD/Schematron, atomik numara, tam GİB durum kodları, cron bildirimi, testler
