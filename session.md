# session.md — l10n_tr_sovos_efatura Oturum Günlüğü

---

## 2026-10-05

**Yapılanlar:**
- Şablondan üretilmiş çalışma dosyaları kod okunarak yeniden yazıldı.

**Tespitler:**
- Repo 18.0.6.0.0; sunucuda prod/test Odoo'nun yüklediği kopya 18.0.8.0.0 ve git dışında.
- Repoda GİB şema dosyaları yok (yalnız `VERSION`), `.pyc` izleniyor.

**Kontroller (repo v6):**
- Kodda/geçmişte gizli bilgi yok; test VKN'leri sahte; örnek API istemcisi zip'inde kimlik bilgisi yok.
- Düzeltildi: `tests/test_ubl_validator.py` iki `with ... \\` bloğunun ortasındaki yorum satırı yüzünden dosya hiç yüklenmiyordu.
- Düzeltildi: Sovos kullanıcı/şifresi SOAP XML'ine kaçışsız yazılıyordu (`&`, `<` içeren şifre isteği bozar) → `xml.sax.saxutils.escape`.
- `.gitignore` eklendi, izlenen `.pyc` kaldırıldı.
- Odoo test çatısı bu ortamda yok; yalnız sözdizimi kontrolü yapıldı.

**v8 taşıma (aynı gün, kullanıcının yüklediği `sovos_v8.zip` ile):**
- Ham v8 ayrı commit olarak alındı; sonra düzeltmeler ayrı commit.
- Tarama: kimlik bilgisi, gerçek VKN, iç IP yok; tüm `.py`/`.xml` sözdizimi temiz (v8'de test sözdizimi hatası zaten yoktu).
- Kararlar: GİB şemaları repoya alınmadı (yılda 1–2 güncelleme, `setup_schemas.sh` var); `setup.exe` çıkarıldı (modül kullanmıyor); sürüm 18.0.8.0.1.
- Yeni bulgu: `services/ubl_parser.py` tedarikçi XML'ini varsayılan lxml parser ile okuyordu; `resolve_entities=True` ile yerel dosya sızıntısı lokal olarak gösterildi → güvenli parser.
- Odoo test çatısı bu ortamda yok; testler sunucuda çalıştırılmalı.

**Test çalıştırma (sunucuda, v8.0.0 kodu):**
- `odoo18-test` DB: 194/194 hata — `product_template.sale_line_warn` NOT NULL (DB ortam sorunu, kod değil). Temiz DB (`sovos_ci_test`) önerildi.
- `sovos_ci_test`: 194/194 hata — `account.account.company_id` Odoo 18'de yok (`company_ids`). Testlerde 5 yer + **canlı kodda** `services/incoming_matcher.py::find_expense_account` düzeltildi → 18.0.8.0.2.

- PR kodu + l10n_tr ile 3. çalıştırma: 58 geçti, 6 failure, 130 error. Kökler:
  - 114: testler `l10n_tr_sovos_efatura.*` yolunu yamalıyordu → `odoo.addons.l10n_tr_sovos_efatura.*`.
  - 12: Odoo 18'de kayıt üzerinde `patch.object(record, ...)` yapılamaz → `patch.object(type(record), ...)`.
  - Wizard testleri eski API'ye göre yazılmıştı (`x_confirm_cancel`, `new_uuid`); kod (canlı) esas alındı:
    `gib_portal_confirmed`, `new_invoice` → iptal yönlendirmesi; 'sent' TICARIFATURA iptal blokajı (DÜZELTME #3) için yeni test.
  - Kod: e-Arşiv iptalinde boş gerekçe artık API'ye gitmeden UserError (GİB kuralı). → 18.0.8.0.3
  - 5 AssertionError'ın ayrıntısı bir sonraki çalıştırmada görülecek.

**Sıradaki adım:** `/tmp/sovos_pr`'de `git pull` + testleri yeniden çalıştır.

- 6. çalıştırma: 195 testte 18 failure + 11 error. Düzeltmeler (18.0.8.0.4):
  - **Kod:** kur farkı sihirbazı `copy()` yerine `create()` (Odoo 18'de satır/hesap sorunu);
    cron `_cron_run_for_all_companies` görevi `with_company(company)` ile çalıştırıyor;
    1163 (mükerrer UUID) da admin'e bildiriliyor (1104 gibi, tüm GIB_CANCEL_AND_NEW).
  - **Test:** `_create_sent_invoice` benzersiz numara/UUID; var olmayan `SovosInvoiceService.cancel_invoice`
    yamaları kaldırıldı; satırsız muhasebe fişine dengeli satır; şirket 2'ye hesap planı;
    e-Arşiv senaryosu açık; cron testleri `_sync_incoming_for_company` adıyla; 1215 testi
    düzeltilmiş davranışa (status 'sent', tek bildirim); retry seti testi constants.py tek kaynak;
    VKN cron testi yalnızca test partnerına bakıyor; send_ubl testi DocData ZIP içeriğine bakıyor;
    DocumentCurrencyCode testi TRY'yi açıkça veriyor; ID format testi `cbc:ID` filtresi.
  - **Açık (karar bekliyor):** test_atomic_number'daki 6 test `x_number_status='released'`
    bekliyor; ancak `raise UserError` tüm transaction'ı geri aldığı için hata/serbest bırakma
    bilgisi üretimde de kalıcı olmuyor. Tasarım kararı kullanıcıya soruldu.

- 7. çalıştırma (18.0.8.0.4): **6 failure + 1 error / 195** (29'dan düştü). Kalanlar ve çözüm (18.0.8.0.5):
  - test_section_lines_excluded…: section satırı posted faturaya ekleniyordu → önce ekle, sonra posted.
  - test_atomic_number 6 test: 'released' kalıcı olamaz (UserError → rollback). İncelenen
    "ayrı cursor ile kaydet" seçeneği **reddedildi**: ana transaction fatura satırını kilitlediği
    için ayrı cursor UPDATE'i kendini bekler (kilitlenme), aynı istekte oluşturulan faturayı ise hiç göremez.
    Karar: akış ve sıra değişmedi; testler gerçek garantiyi doğruluyor (numara faturada kalmaz,
    fatura draft, 'sent' olmaz). Kod: doğrulama hatasında ilk 5 hata UserError mesajında
    gösteriliyor (alan/ek rollback'te kaybolduğu için).
  - Bilinen sınırlama: hata yolunda doğrulama XML eki ve x_validation_errors kalıcı değil (task.md).

- 8. çalıştırma (18.0.8.0.5, `sovos_ci_test`, temiz DB + l10n_tr): **tüm testler geçti** —
  `odoo.tests.stats: l10n_tr_sovos_efatura: 229 tests 126.26s` (alt testler dahil), failure/error yok.
  Log'daki 2 ERROR satırı testlerin bilerek ürettiği kayıtlar (cron "Şirket 1 hatası", XPath beklenmedik hata).

**Sıradaki adım:** Sunucu kopyasını repodan güncelle — ⚠ `odoo18-prod` ve `odoo18-test` aynı klasörü
yüklüyor; klasör değişince prod da yeni Python kodunu yeniden başlatmada/worker yenilemede alır.
18.0.8.0.0 → 18.0.8.0.5 arasında alan/görünüm değişikliği yok (yalnızca Python), yine de prod `-u` kullanıcı onayıyla.

- **Sunucu güncellendi (kullanıcı onayıyla):** `/opt/odoo/custom_addons/l10n_tr_sovos_efatura` → 18.0.8.0.5
  (19 GİB şema dosyası korundu; `kaynaklar/*.xlsx` taşındı; `setup.exe` yalnızca yedekte).
  Yedek: `/opt/odoo/backups/l10n_tr_sovos_efatura_18.0.8.0.0_20261006_025643`.
  `odoo18-test` DB `-u` → `installed|18.0.8.0.5`, iki servis active. Log'daki tek ERROR
  ("Importing test framework…") bu modülden değil, custom_addons'taki başka bir modülden.
  Prod: workers=4 → işçiler yenilendikçe yeni Python kodu devreye girer; prod DB'de `-u` gerekmiyor.
  - `odoo18-prod` kullanıcı tarafından yeniden başlatıldı → active; journalctl'de ERROR/CRITICAL yok (logfile ayrıca kontrol edilecek).
  - Prod log (`/var/log/odoo/odoo18-prod.log`, `grep -a` gerekli — dosyada binary karakter var): yeniden
    başlatma sonrası modülle ilgili hata yok; `olap_prod` registry'si ilk istekte yüklenecek.
  - **Modül dışı bulgular (kullanıcıya bildirildi, onay bekliyor):** prod servisinde `dbfilter`/`list_db` yok →
    prod tüm DB'leri (odoo18-test, sovos_ci_test, isg) sunuyor ve `/web/database/manager` internetten erişilebilir
    (Haziran'da "Database creation error"); port dışa açık (TLS tarayıcıları). Öneri: `list_db = False`,
    `dbfilter = ^olap_prod$`, güçlü `admin_passwd`, portları 127.0.0.1 + nginx HTTPS. `isg` DB'de 31 isg_* modülü eksik.
  - **Düzeltme:** prod conf'ta `dbfilter = olap_prod` zaten vardı (web tarafı kısıtlıydı). Asıl sorun cron: `db_name`
    olmadığı için Odoo cron'u tüm DB'lerde dolaşıyordu — prod servisi odoo18-test/isg/sovos_ci_test cron'larını,
    **test servisi de `olap_prod` cron'larını** çalıştırıyordu (test log'unda dakikada bir `dbname=olap_prod` bağlantısı).
  - **Uygulandı (kullanıcı onayıyla, conf yedekleri `/etc/odoo/*.conf.bak_*`):**
    prod → `db_name = olap_prod`, `dbfilter = ^olap_prod$`, `list_db = False`;
    test → `db_name = odoo18-test`, `dbfilter = ^odoo18-test$`, `list_db = False`. İki servis yeniden başlatıldı, active;
    prod login 200, `/web/database/manager` "disabled by the administrator".
  - Kalan: Odoo portlarını 127.0.0.1'e bağla + nginx HTTPS; `admin_passwd` gücünü kontrol et; `sovos_ci_test` DB'sini sil; `isg` DB eksik modüller.
  - Sunucu ağ incelemesi: ufw varsayılan deny → Odoo portları (8074-8077) dışarıdan kapalı; nginx upstream'leri
    127.0.0.1:8076/8074. **Uygulandı:** 5432 ufw kuralı "Anywhere" yerine pg_hba'daki 4 IP'ye daraltıldı;
    `152.55.176.240` satırı `host` → `hostssl` (yedek `/root/pg_hba.conf.bak_20261006`).
    Bekleyen (kullanıcı kararı): Ollama 11434 kimlik doğrulamasız açık, VNC 5901 açık, Docker 8090 ufw'yi atlıyor,
    8080 (python3) bilinmiyor, 1433'te dinleyen yok; Odoo `http_interface = 127.0.0.1` + `proxy_mode = True` + yeni `admin_passwd` (14 kr.).
  - **Uygulandı (`/root/odoo_harden.sh`, conf yedekleri `*.conf.bak_20261006_032503`):** prod+test conf'a
    `http_interface = 127.0.0.1`, `proxy_mode = True`, servis başına yeni 43 karakterlik `admin_passwd`
    (`/root/odoo_admin_passwd_20261006_032503.txt`, kullanıcı kaydedip silecek). 8074-8077 yalnızca 127.0.0.1;
    nginx üzerinden prod/test `/web/login` 200.
  - **Modül dışı bulgu:** `odoo18-prod/test.olap.com.tr` Let's Encrypt sertifikalarının süresi 2026-09-23'te dolmuş;
    certbot.timer çalışıyor ama 7 yenileme başarısız; alan adları sunucudan DNS'te çözülmüyor (yenileme bu yüzden başarısız olabilir).

---

## Önceki Çalışmalar

- **2026-06-23** — Sunucuda v8 (repoya işlenmedi).
- **2026-06-07 → 06-11** — İlk commit ve v6 Final yüklemeleri.

---

### Kayıt Şablonu

```markdown
## YYYY-AA-GG
**Yapılanlar:** ...
**Kararlar / neden:** ...
**Açık sorunlar:** ...
**Sıradaki adım:** ...
```
