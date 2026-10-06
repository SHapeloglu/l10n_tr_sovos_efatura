# CLAUDE.md — l10n_tr_sovos_efatura (Odoo 18 × Sovos e-Fatura / e-Arşiv)

Odoo 18 Community modülü: Sovos (GİB özel entegratörü) üzerinden e-Fatura ve e-Arşiv gönderimi, gelen alış faturalarını alma, durum takibi, TİCARİFATURA kabul/red, iptal/yeniden gönderim, kur farkı faturası, PDF arşivi, VKN cache, çok şirket. Gönderim öncesi UBL-TR XSD + iş kuralı doğrulaması ve **atomik fatura numarası** rezervasyonu.

- GitHub: https://github.com/SHapeloglu/l10n_tr_sovos_efatura — repo sürümü **18.0.8.0.5** (2026-10-06; sunucudaki v8 + güvenlik ve Odoo 18 uyum düzeltmeleri)
- Mimari: `architect.md` · Görevler: `task.md` · Fikirler: `backlog.md` · Günlük: `session.md`

## ⚠️ Sunucu kopyası ile repo

- Sunucudaki kurulu kopya: **`/opt/odoo/custom_addons/l10n_tr_sovos_efatura`** (git deposu değil). `odoo18-prod` (8076, `olap_prod`) ve `odoo18-test` (8074, `odoo18-test`) servisleri bu klasörü yüklüyor.
- 2026-10-05: sunucudaki v18.0.8.0.0 repoya alındı; repo artık **önde** (18.0.8.0.1: SOAP kimlik bilgisi XML kaçışı, gelen faturada XXE önlemi). Sunucu henüz güncellenmedi.
- GİB şema dosyaları (`services/schemas/` altı, `VERSION` hariç) repoda yok — sunucuda `setup_schemas.sh` ile kurulur. Sunucuyu repodan güncellerken mevcut `services/schemas/` korunmalı.
- Bir de sunucuda `l10n_tr_sovos_efatura.bak_20260628` yedeği var.
- **Değişiklik repoda yapılır**, sunucu repodan güncellenir; sunucuda doğrudan düzenleme yapma.

## Komutlar

```bash
# Kurulum / güncelleme (sunucuda test ortamı)
sudo -u odoo /opt/odoo/venv18/bin/python3 /opt/odoo/odoo18/odoo-bin -c /etc/odoo/odoo18-test.conf -d odoo18-test -u l10n_tr_sovos_efatura --stop-after-init
# Testler (Odoo test çatısı; tests/ altında 11 dosya)
sudo -u odoo /opt/odoo/venv18/bin/python3 /opt/odoo/odoo18/odoo-bin -c /etc/odoo/odoo18-test.conf -d odoo18-test --test-tags /l10n_tr_sovos_efatura -u l10n_tr_sovos_efatura --stop-after-init
# GİB şemaları (v8): bash setup_schemas.sh UBL-TR1.2.1_Paketi.zip e-FaturaPaketi.zip
```

Servis kullanıcısı / venv yolu sunucuda doğrulanmalı (`systemctl cat odoo18-test`). **Prod veritabanında `-u` çalıştırmadan önce test DB'de dene ve kullanıcıya sor.**

## Kurallar ve Tuzaklar

- **GİB durum kodları tek kaynak: `services/constants.py`** (`GIB_RETRY_SAME_UUID`, `GIB_CANCEL_AND_NEW`, …). Kod setini başka dosyada tekrar tanımlama.
- Teknik hata (1101, 1103, 11xx…) → **aynı UUID** ile tekrar gönder; içerik hatası → iptal + yeni fatura. `resend_invoice_wizard` bu ayrımı yapıyor.
- Atomik numara: `ir.sequence` ile rezerve → doğrulama/gönderim başarısızsa **serbest bırak** (`x_number_status=released`), başarılıysa onayla. Akışın sırasını bozma.
- Test modunda (`x_sovos_test_mode=True`) GİB'e iletim yapılmaz; test verisinde gerçek VKN kullanma (KVKK).
- Sovos kimlik bilgileri şirket kaydında (`res.company`); koda/data XML'ine yazma. SOAP gövdesine yazılan kullanıcı girdisi `xml.sax.saxutils.escape` ile kaçışlanır.
- Dışarıdan gelen XML (gelen fatura) `resolve_entities=False, no_network=True` parser ile okunur (`services/ubl_parser.py`).
- Yeni alanlar `x_` önekli (mevcut konvansiyon). Görünüm ve model değişikliğinde `__manifest__.py` sürümünü artır.
- `dokumanlar/` (BRD, Spec, test raporu, eğitim notları, geliştirici sözlüğü) ve `kaynaklar/` (GİB durum kodları PDF, Sovos UBL-TR kataloğu, örnek API istemcisi) referanstır. `setup.exe` repodan çıkarıldı.
- Oturum sonunda `session.md`'ye kayıt düş, `task.md`'yi güncelle.
