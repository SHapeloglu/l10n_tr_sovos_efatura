# CLAUDE.md — l10n_tr_sovos_efatura (Odoo 18 × Sovos e-Fatura / e-Arşiv)

Odoo 18 Community modülü: Sovos (GİB özel entegratörü) üzerinden e-Fatura ve e-Arşiv gönderimi, gelen alış faturalarını alma, durum takibi, TİCARİFATURA kabul/red, iptal/yeniden gönderim, kur farkı faturası, PDF arşivi, VKN cache, çok şirket. Gönderim öncesi UBL-TR XSD + iş kuralı doğrulaması ve **atomik fatura numarası** rezervasyonu.

- GitHub: https://github.com/SHapeloglu/l10n_tr_sovos_efatura — repo sürümü **18.0.8.0.7** (2026-10-07; gelen fatura cron + eşleme sihirbazı + pasif döviz düzeltmeleri — sunucuda hâlâ 18.0.8.0.5)
- Mimari: `architect.md` · Görevler: `task.md` · Fikirler: `backlog.md` · Günlük: `session.md`

## 📍 Kaldığımız yer (2026-10-06)

- **Modül:** 18.0.8.0.5 — 229 test temiz DB'de geçiyor; sunucu klasörü güncellendi, `odoo18-test` `-u` yapıldı, prod yeniden başlatıldı (hatasız). PR #1 `main`'e birleştirildi (2026-10-06) — `main` artık sunucudaki kopyayla aynı sürümde.
- **⚠ Prod DB'de modül kurulu görünmüyor:** 2026-10-06'da `olap_prod` → `ir_module_module` satırı `uninstalled` (`odoo18-test`'te `installed|18.0.8.0.5`). Prod servisi klasörü yüklüyor ama modül prod DB'de etkin değil; doğrula, kurulum (`-i`) yalnızca kullanıcı onayıyla.
- **Sunucu sıkılaştırma yapıldı:** conf'larda `db_name`/`dbfilter`/`list_db=False`, `http_interface=127.0.0.1`, `proxy_mode=True`, yeni `admin_passwd`; PostgreSQL 5432 4 IP'ye daraltıldı, pg_hba `hostssl`.
- **Bekleyen (kullanıcıda):** DNS panellerine A kayıtları (95.111.242.96) → `certbot renew` — 7 sertifika süresi dolmuş, adımlar `task.md`'de. Kayıtlar `dig` ile görünmeden certbot çalıştırma (LE: saatte 5 başarısız deneme).
- **Bekleyen (karar):** Ollama 11434 / VNC 5901 / Docker 8090 / 8080 kim kullanıyor; kullanılmayan alan adları.
- **Sonraki modül işi:** ⚠ SOAP katmanını Sovos test hesabıyla doğrula (örnek istemci şemasıyla uyuşmuyor — task.md); sonra 0.6+0.7 sunucuya kurulumu; gelen fatura testleri `tests/test_incoming.py`'de.
- Kullanıcı sunucuda root; komutları kullanıcı çalıştırıp çıktıyı yapıştırıyor (oturumdan SSH yok). Uzun komutları `cat > script.sh <<'EOF'` + `bash script.sh` biçiminde ver — doğrudan yapıştırmada satırlar karışıyor.
- Test çalıştırma: `bash /tmp/sovos_pr/run_tests.sh` (geçici `sovos_ci_test` DB, `/tmp/sovos_pr` klonu). Odoo başarıda "failures" satırı yazmaz; `odoo.tests.stats` satırına bak.

## ⚠️ Sunucu düzeni (2026-11-08 incelemesi — Docker)

- Odoo **Docker** konteynerlerinde çalışıyor (systemd `odoo18-*` servisleri pasif, `/etc/odoo` yok). Tek imaj `odoo18:latest`, kaynak `/opt/odoo-docker/src/` (Dockerfile `COPY src/custom_addons` ile gömüyor). Dolayısıyla modül kodu **imaj yeniden derlenerek** (`/opt/odoo-docker`, `docker compose`) güncellenir; konteynerde `custom_addons` bind-mount yok.
- Konteynerler: `odoo18-prod` (127.0.0.1:18076, DB `olap_prod`, conf `/opt/odoo-docker/conf/odoo18-prod.conf`), `odoo18-test` (127.0.0.1:18074, DB `odoo18-test`), `odoo18-isg` (127.0.0.1:18078). DB sunucusu: `postgres-ortak` konteyneri (127.0.0.1:5434, `db_host=postgres-ortak`). Sistem PostgreSQL 16 kullanılmıyor (veri dizini yok, unit maskelendi).
- İmajdaki `l10n_tr_sovos_efatura` = repo (18.0.8.0.7, içerik olarak birebir aynı). Sunucudaki `/opt/odoo/custom_addons/l10n_tr_sovos_efatura` eski/yedek kopya, Odoo tarafından kullanılmıyor.
- Prod DB (`olap_prod`): modül **`uninstalled`** (2026-11-08 doğrulandı). Kurulum (`-i`) yalnızca kullanıcı onayıyla.

## ⚠️ Eski sunucu notları (systemd dönemi — 2026-10-06)

- Eski kurulu kopya: **`/opt/odoo/custom_addons/l10n_tr_sovos_efatura`** (git deposu değil).
- 2026-10-05: sunucudaki v18.0.8.0.0 repoya alındı (18.0.8.0.1: SOAP kimlik bilgisi XML kaçışı, gelen faturada XXE önlemi).
- 2026-10-06: sunucu klasörü repodan **18.0.8.0.5**'e güncellendi (`git archive` + mevcut `services/schemas/` korundu); `odoo18-test` DB'de `-u` yapıldı. Eski kopya yedeği: `/opt/odoo/backups/l10n_tr_sovos_efatura_18.0.8.0.0_20261006_025643`. Prod DB'de `-u` yapılmadı (gerek yok: yalnızca Python değişikliği).
- Her servis conf'unda `db_name` + `dbfilter = ^<db>$` + `list_db = False` var (2026-10-06). `db_name` kaldırılırsa cron tüm DB'lerde dolaşır — test servisi prod cron'larını çalıştırır.
- Yedekleri `custom_addons` **dışında** tut (`/opt/odoo/backups/`) — klasördeki kopyalar Odoo modül taramasına karışabilir.
- GİB şema dosyaları (`services/schemas/` altı, `VERSION` hariç) repoda yok — sunucuda `setup_schemas.sh` ile kurulur. Sunucuyu repodan güncellerken mevcut `services/schemas/` korunmalı.
- Bir de sunucuda `l10n_tr_sovos_efatura.bak_20260628` yedeği var.
- **Değişiklik repoda yapılır**, sunucu repodan güncellenir; sunucuda doğrudan düzenleme yapma.

## Komutlar

```bash
# Docker düzeni (2026-11-08): kod imajda, güncelleme = imaj yeniden derleme + konteyner yeniden oluşturma
# (/opt/odoo-docker/src güncellenir → docker build -t odoo18:latest → docker compose up -d odoo18-test)
# Test DB'de -u (konteynerde, DENEME — doğrulanmadı):
docker exec -u odoo odoo18-test python3 /opt/odoo/odoo18/odoo-bin -c /etc/odoo/odoo.conf -d odoo18-test -u l10n_tr_sovos_efatura --stop-after-init
# GİB şemaları (v8): bash setup_schemas.sh UBL-TR1.2.1_Paketi.zip e-FaturaPaketi.zip
```

Konteyner adları, DB adları ve yollar sunucuda doğrulanmalı (`docker ps`, `docker inspect`). **Prod veritabanında `-u`/`-i` çalıştırmadan önce test DB'de dene ve kullanıcıya sor.**

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
