# Odoo Geliştirici Terimleri Sözlüğü
### Junior Developer Referans Kılavuzu
*Her iki projeden (l10n_tr_sovos_efatura + nakliye_yonetim) derlendi*

---

## A

### `@api.constrains`
Kayıt kaydedilmeden önce çalışan doğrulama dekoratörü. Kural ihlalinde
`ValidationError` fırlatır, kayıt DB'ye yazılmaz.

```python
@api.constrains('gidis_km', 'donus_km')
def _check_km(self):
    for kayit in self:
        if kayit.gidis_km < 0:
            raise ValidationError("Km değeri negatif olamaz!")
```

Farkı: `@api.onchange` sadece form ekranında çalışır, API'den gelen veriyi
kontrol etmez. `@api.constrains` her durumda çalışır (form, API, import).

---

### `@api.depends`
Computed alan hangi alanlar değişince yeniden hesaplanacak, bunu belirtir.
Bağımlılıklar değişmeden metod çalışmaz (performans optimizasyonu).

```python
@api.depends('gidis_km', 'donus_km')
def _compute_toplam_km(self):
    for kayit in self:
        kayit.toplam_km = kayit.gidis_km + kayit.donus_km
```

Zincir bağımlılık da yazılabilir:
```python
@api.depends('satir_ids', 'satir_ids.tutar', 'tevkifat_orani')
def _compute_toplamlar(self):
```
`satir_ids` değişince veya herhangi bir satırın `tutar` alanı değişince tetiklenir.

---

### `@api.model`
Metodun belirli bir kayıta değil, modelin kendisine ait olduğunu belirtir.
`self` bir kayıt içermez. Genellikle `search()`, `create()` veya cron
metodlarında kullanılır.

```python
@api.model
def get_ayarlar(self):
    ayarlar = self.search([], limit=1)
    if not ayarlar:
        ayarlar = self.create({})
    return ayarlar
```

---

### `@api.onchange`
Form ekranında alan değiştiğinde client-side (tarayıcıda) tetiklenir.
DB'ye kayıt yapılmaz; sadece form görünümünü günceller.

```python
@api.onchange('plan_id')
def _onchange_plan_id(self):
    if self.plan_id:
        satirlar = []
        for satir in self.plan_id.satir_ids:
            satirlar.append((0, 0, {...}))
        self.satir_ids = satirlar
```

`@api.constrains` ile farkı: onchange sadece ekranda, constrains her yerde çalışır.

---

### `active` alanı
Odoo'nun özel boolean alanı. `active=False` yapılan kayıtlar normal aramalarda
görünmez. `search()` varsayılan olarak `('active', '=', True)` filtresi uygular.

```python
aktif = fields.Boolean(string='Aktif', default=True, tracking=True)
```

Pasife alınca `ir.rule` devreye girebilir — şantiye muhasebecisi pasif
şantiyeyi göremez.

---

## B

### `browse(id)`
Bilinen ID ile kayda erişir. `search()` gibi DB'ye gitmez, sadece referans oluşturur.

```python
sequence = self.env['ir.sequence'].browse(company.x_invoice_sequence_id.id)
```

---

## C

### Chatter (`mail.thread`)
Odoo'nun kayıt bazlı mesajlaşma sistemi. `_inherit = ['mail.thread']` ile
modele eklenir. Değişiklik logları, kullanıcı notları, e-postalar burada görünür.

```python
class NakliyeHakedis(models.Model):
    _inherit = ['mail.thread', 'mail.activity.mixin']
```

`message_post()` ile kod tarafından not eklenebilir:
```python
hakedis.message_post(
    body="⚠️ Bu hakediş 3 günden fazladır onay bekliyor!",
    message_type='comment',
    subtype_xmlid='mail.mt_note',
)
```

---

### `compute` (Hesaplanmış Alan)
Değeri başka alanlara göre otomatik hesaplanan alan. Kullanıcı tarafından
girilemez, sistem hesaplar.

```python
toplam_km = fields.Float(
    compute='_compute_toplam_km',
    store=True    # DB'ye kazdır → filtreleme ve raporlama mümkün
)
```

`store=True` → DB'ye yazılır, SQL'de filtrelenebilir
`store=False` (varsayılan) → DB'ye yazılmaz, her okumada hesaplanır

---

### `copy()` ve `copy=False`
`copy()`: Kaydı kopyalar. Bazı alanların kopyalanmaması için `copy=False` kullanılır.

```python
x_sovos_uuid = fields.Char(copy=False)  # Kopyalanınca boş gelsin
```

`copy()` ile override:
```python
yeni_plan = self.copy({
    'name': f"{self.name} (Yeni)",
    'baslangic_tarihi': date.today(),
    'aktif': True,
})
```

---

### `create(vals)`
Yeni kayıt oluşturan ORM metodu. Dict ile alan değerleri verilir.
One2many ile birden fazla alt kayıt aynı anda oluşturulabilir.

```python
hakedis = self.env['nakliye.hakedis'].create({
    'nakliyeci_id': self.nakliyeci_id.id,
    'satir_ids': [(0, 0, satir) for satir in satir_vals],
})
```

---

### Cron (Zamanlı Görev)
Odoo'nun arka planda belirli aralıklarla çalıştırdığı görevler.
`data/cron.xml` ile tanımlanır, bir modelin metoduna bağlanır.

```python
@api.model
def action_hakedis_hatirlatma(self):
    # Her gün çalışır, onay bekleyen hakedişlere hatırlatma ekler
    onay_bekleyenler = self.search([
        ('durum', '=', 'onay_bekliyor'),
        ('write_date', '<=', bekleme_tarihi),
    ])
```

---

## D

### `default`
Alan oluşturulduğunda atanacak varsayılan değer.

```python
durum = fields.Selection(default='taslak')
tarih = fields.Date(default=fields.Date.today)   # Bugünün tarihi
formen_id = fields.Many2one(default=lambda self: self.env.user)  # Giriş yapan kullanıcı
```

`lambda self: self.env.user` → kayıt oluşturulurken anlık kullanıcıyı alır.
Modül yüklenirken değil, kayıt oluşturulurken çalışır.

---

### `domain`
Alan görünümünde veya arama sorgusunda filtreleme kuralı.
Liste veya string olarak yazılabilir.

```python
# Alan tanımında (string domain — dinamik)
arac_id = fields.Many2one(
    domain="[('parent_id', '=', nakliyeci_id)]"
)

# Kod içinde (liste domain — statik)
sozlesme = self.env['nakliye.sozlesme'].search([
    ('aktif', '=', True),
    ('santiye_id', '=', self.santiye_id.id),
])
```

Domain operatörleri:
```
('alan', '=', deger)     → eşit
('alan', '!=', deger)    → eşit değil
('alan', 'in', [1,2,3])  → listede
('alan', '>', deger)     → büyük
('alan', '>=', deger)    → büyük eşit
('alan', 'like', '%x%')  → içerir
('alan', '=', False)     → NULL / boş
```

Mantıksal operatörler (prefix notation):
```python
['|', ('a', '=', 1), ('b', '=', 2)]  # OR
['&', ('a', '=', 1), ('b', '=', 2)]  # AND (varsayılan)
['!', ('a', '=', 1)]                  # NOT
```

---

## E

### `ensure_one()`
Metodun tek bir kayıt üzerinde çalışmasını garanti eder.
Birden fazla kayıt gelirse `ValueError` fırlatır.

```python
def action_hakedis_olustur(self):
    self.ensure_one()  # Wizard tek kayıt için çalışır
    sozlesme = self.env['nakliye.sozlesme'].search(...)
```

---

### `env`
Odoo'nun çalışma ortamı. Üç şeyi içerir: kullanıcı, bağlantı (cursor), bağlam.

```python
self.env.user          # Giriş yapan kullanıcı
self.env.company       # Aktif şirket
self.env.cr            # DB cursor (savepoint için)
self.env['res.partner']  # Modele erişim
self.env.ref('mail.mt_note')  # XML ID ile kayda erişim
```

---

## F

### `fields.Boolean`
True/False değer tutan alan. `default=True` çok yaygın.

```python
aktif = fields.Boolean(string='Aktif', default=True)
nakliye_araci = fields.Boolean(string='Nakliye Aracı', default=False)
```

---

### `fields.Char`
Kısa metin alanı. `size` ile maksimum uzunluk belirlenebilir.

```python
plaka = fields.Char(string='Plaka', size=10)
x_sovos_uuid = fields.Char(string='UUID', size=36, copy=False)
```

---

### `fields.Date` / `fields.Datetime`
Tarih ve tarih-saat alanları.

```python
tarih = fields.Date(default=fields.Date.today)
write_date = fields.Datetime(readonly=True)  # Odoo otomatik günceller
```

---

### `fields.Float`
Ondalıklı sayı alanı. `digits=(precision, scale)` ile hassasiyet belirlenebilir.

```python
toplam_km = fields.Float(string='Toplam Km', digits=(10, 2))
tevkifat_orani = fields.Float(string='Tevkifat Oranı (%)', default=3.0)
```

---

### `fields.Integer`
Tam sayı alanı.

```python
sozlesme_uyari_gun = fields.Integer(string='Uyarı Süresi (Gün)', default=30)
adet = fields.Integer(string='Adet', default=1)
```

---

### `fields.Many2many`
Çok-a-çok ilişki. Her iki tarafta birden fazla kayıt olabilir.

```python
muhasebeci_ids = fields.Many2many(
    'res.users',
    string='Muhasebeciler'
)
formen_ids = fields.Many2many(
    'res.users',
    string='Formenler'
)
```

ORM komutları (write/create içinde):
```python
(4, id)        # Mevcut kaydı bağla
(3, id)        # Bağlantıyı kopar (kayıt silinmez)
(5, 0, 0)      # Tüm bağlantıları kopar
(6, 0, [ids])  # Sadece bu ID'leri bağlı tut
```

---

### `fields.Many2one`
Çok-a-bir ilişki. Bu kayıt başka bir tablodaki tek kayda bağlıdır.
`ondelete` parametresi: bağlı kayıt silinince ne olacak?

```python
plan_id = fields.Many2one(
    'nakliye.gunluk.plan',
    ondelete='cascade'  # Plan silinince satır da silinir
)
santiye_id = fields.Many2one(
    'nakliye.santiye',
    ondelete='restrict'  # Şantiyeye bağlı kayıt varken silinemez
)
sozlesme_id = fields.Many2one(
    'nakliye.sozlesme',
    ondelete='set null'  # Sözleşme silinince alan boşalır
)
```

---

### `fields.One2many`
Bir-a-çok ilişki. Bir kaydın birden fazla alt kaydı.
Her zaman karşı taraftaki `Many2one` alanının adını gerektirir.

```python
satir_ids = fields.One2many(
    'nakliye.hakedis.satir',  # Alt model
    'hakedis_id',              # Alt modeldeki Many2one alanı
    string='Hakediş Satırları'
)
```

ORM komutları (write/create içinde):
```python
(0, 0, vals)   # Yeni satır ekle
(1, id, vals)  # Mevcut satırı güncelle
(2, id)        # Satırı sil
(5, 0, 0)      # Tüm satırları sil
```

---

### `fields.Selection`
Sabit seçenekler listesi. DB'de string olarak saklanır.

```python
durum = fields.Selection([
    ('taslak', 'Taslak'),
    ('onaylandi', 'Onaylandı'),
    ('iptal', 'İptal'),
], string='Durum', default='taslak', tracking=True)
```

Boş değer: `False` (None değil)

---

### `fields.Text`
Uzun metin alanı. Sınırsız uzunluk, çok satırlı.

```python
notlar = fields.Text(string='Notlar')
x_efatura_error_msg = fields.Text(string='Hata Mesajı', copy=False)
```

---

### `filtered(lambda)`
Recordset içinden koşula uyanları döndürür. SQL'deki WHERE gibi ama Python'da.

```python
# Onaylı fişler
onaylilar = fis_ids.filtered(lambda f: f.durum == 'onaylandi')

# Aktif ve bitiş tarihi olmayan atamalar
aktif_atama = santiye_atama_ids.filtered(
    lambda a: a.aktif and not a.bitis_tarihi
)

# display_type kontrolü
urun_satirlar = invoice_line_ids.filtered(
    lambda l: l.display_type == 'product'
)
```

---

## G

### `getattr(nesne, 'metod_adi')`
String ile nesnenin metoduna veya özelliğine erişir.
Dinamik metod çağrısı için kullanılır.

```python
task_fn = getattr(self, '_sync_efatura_status_for_company')
task_fn(company)  # self._sync_efatura_status_for_company(company) ile aynı
```

---

### `groups` (Alan Güvenliği)
Alanı sadece belirli Odoo güvenlik grubunun görmesini sağlar.
Yetkisiz kullanıcı için alan yok gibidir — DB'de var ama görünmez.

```python
x_sovos_invoice_pass = fields.Char(groups='base.group_system')
# Sadece Sistem Yöneticileri görebilir
```

`readonly` ile farkı:
- `readonly` → görür ama değiştiremez
- `groups` → hiç göremez

---

## H

### `help`
Alan üzerine fare gelince çıkan tooltip metni. Son kullanıcı için açıklama.

```python
x_efatura_type = fields.Selection(
    help='efatura: GİB kayıtlı\nearsiv: GİB kayıtsız'
)
```

---

## I

### `_inherit`
Mevcut modeli genişletir. Yeni tablo açmaz, mevcut tabloya alan/metod ekler.

```python
class HrEmployee(models.Model):
    _inherit = 'hr.employee'   # hr_employee tablosuna ekle
    calisma_tipi = fields.Selection([...])
```

Birden fazla model inherit (mixin):
```python
_inherit = ['mail.thread', 'mail.activity.mixin']
```

---

### `ir.actions.act_window`
Odoo penceresinde bir modelin liste veya form görünümünü açar.
Buton aksiyonlarında ve wizard dönüşlerinde kullanılır.

```python
return {
    'type': 'ir.actions.act_window',
    'name': 'Hakediş',
    'res_model': 'nakliye.hakedis',
    'res_id': hakedis.id,
    'view_mode': 'form',      # form, list, kanban, tree
    'target': 'current',      # current, new (popup), fullscreen
}
```

---

### `ir.actions.act_window_close`
Wizard penceresini kapatır.

```python
def kaydet(self):
    return {'type': 'ir.actions.act_window_close'}
```

---

### `ir.actions.client`
Tarayıcı tarafında özel aksiyon çalıştırır. Bildirim göstermek için kullanılır.

```python
return {
    'type': 'ir.actions.client',
    'tag': 'display_notification',
    'params': {
        'title': 'Başarılı',
        'message': 'Fatura gönderildi.',
        'type': 'success',   # success, warning, danger, info
        'sticky': False,     # False=otomatik kapan, True=kullanıcı kapatsın
    },
}
```

---

### `ir.attachment`
Odoo'nun dosya saklama modeli. PDF, XML, resim gibi dosyalar burada tutulur.
Varsayılan: Linux dosya sisteminde (DB'de yol tutulur).

```python
self.env['ir.attachment'].create({
    'name': 'fatura.pdf',
    'type': 'binary',
    'datas': base64.b64encode(pdf_bytes),
    'res_model': 'account.move',
    'res_id': self.id,
})
```

---

### `ir.config_parameter`
Sistem genelinde tekil anahtar-değer çiftleri için. Basit ayarlar için kullanılır.

```python
param = self.env['ir.config_parameter'].get_param('web.base.url')
self.env['ir.config_parameter'].set_param('my.key', 'value')
```

---

### `ir.rule`
Kayıt bazlı erişim kontrolü. Kim hangi kayıtları görebilir/değiştirebilir.
Güvenlik grubuyla birlikte çalışır.

Örnek: Şantiye muhasebecisi sadece kendi şantiyesinin kayıtlarını görür.
`security/ir_rule.xml` dosyasında tanımlanır.

---

### `ir.sequence`
Sıralı numara üretici. GİB fatura numaraları, sipariş numaraları için kullanılır.

```python
sequence = self.env['ir.sequence'].browse(company.x_invoice_sequence_id.id)
number = sequence.next_by_id()
# → 'ABC2024000000001'
```

---

## L

### `lambda`
İsimsiz tek satırlık fonksiyon. `filtered`, `sorted`, `mapped` içinde sık kullanılır.

```python
# Filtre
aktif_satirlar = satir_ids.filtered(lambda s: s.aktif)

# Sıralama
siralı = records.sorted(lambda r: r.tarih)

# Değer listesi
tutarlar = satir_ids.mapped(lambda s: s.tutar)

# Varsayılan değer
default=lambda self: self.env.user
```

Uzun versiyonu:
```python
lambda s: s.aktif
# =
def isimsiz(s):
    return s.aktif
```

---

### Lazy Import
Modül yüklenirken değil, metod çağrılınca import etme. Döngüsel import riskini
ve gereksiz yüklenmeyi önler.

```python
def action_test_connection(self):
    from ..services.sovos_invoice_service import SovosInvoiceService  # Burada import
    svc = SovosInvoiceService(self)
```

---

## M

### `mail.activity.mixin`
Aktivite (hatırlatma) desteği ekler. Kullanıcı belirli tarihte bir şey
yapması için kendine hatırlatma ekleyebilir.

```python
_inherit = ['mail.thread', 'mail.activity.mixin']
```

---

### `mail.thread`
Chatter desteği ekler. Kayıt üzerinde mesajlaşma, değişiklik logu, e-posta.
`tracking=True` ile alan değişiklikleri otomatik loglanır.

```python
_inherit = ['mail.thread', 'mail.activity.mixin']
durum = fields.Selection([...], tracking=True)
```

---

### `mapped()`
Recordset'teki tüm kayıtların belirtilen alanını liste olarak döndürür.

```python
# Alan adı ile (string)
tutarlar = satir_ids.mapped('tutar')       # [100.0, 200.0, 150.0]
toplam = sum(satir_ids.mapped('tutar'))    # 450.0

# Lambda ile (hesaplama)
net_tutarlar = satir_ids.mapped(lambda s: s.adet * s.yemek_bedeli)
```

---

### `message_post()`
Kaydın chatter'ına (log) not ekler. `mail.thread` mixin'den gelir.

```python
hakedis.message_post(
    body="⚠️ Onay bekliyor!",
    message_type='comment',       # comment veya email
    subtype_xmlid='mail.mt_note', # mt_note=iç not, mt_comment=dışarıya gönderilir
)
```

---

### `models.Model`
Kalıcı veritabanı modeli. Her `_name` için ayrı tablo oluşturulur.

```python
class NakliyeHakedis(models.Model):
    _name = 'nakliye.hakedis'
    _description = 'Nakliyeci Hakediş'
```

---

### `models.TransientModel`
Geçici model. Wizard kapandıktan sonra kayıtlar DB'den silinir.
`_name` zorunlu, tablo oluşturulur ama periyodik olarak temizlenir.

```python
class NakliyeHakedisWizard(models.TransientModel):
    _name = 'nakliye.hakedis.wizard'
    _description = 'Hakediş Oluşturma Sihirbazı'
```

---

## N

### `_name`
Modelin Odoo'daki kayıt adı. Nokta ile ayrılmış hiyerarşik format.
DB'de alt çizgiye çevrilir: `nakliye.hakedis` → `nakliye_hakedis` tablosu.

```python
_name = 'nakliye.hakedis'      # DB: nakliye_hakedis
_name = 'nakliye.plan.satir'   # DB: nakliye_plan_satir
```

---

## O

### `ondelete`
Many2one alanında: bağlı kayıt silinince ne yapılacak.

```python
plan_id = fields.Many2one('nakliye.gunluk.plan', ondelete='cascade')
# cascade  → bağlı kayıt silinince bu kayıt da silinir
# restrict → bu kayıt varken bağlı kayıt silinemez (hata verir)
# set null → bağlı kayıt silinince alan boşalır (False olur)
```

---

### ORM Komutları (One2many / Many2many)
`write()` veya `create()` içinde ilişkili kayıtları yönetmek için tuple komutlar.

```python
# (0, 0, vals) → Yeni kayıt oluştur ve bağla
satir_ids = [(0, 0, {'tarih': date.today(), 'tutar': 100.0})]

# (1, id, vals) → Mevcut kaydı güncelle
satir_ids = [(1, 5, {'tutar': 150.0})]

# (2, id) → Kaydı sil
satir_ids = [(2, 5)]

# (3, id) → Bağlantıyı kopar (Many2many, kayıt silinmez)
muhasebeci_ids = [(3, 7)]

# (4, id) → Mevcut kaydı bağla (Many2many)
muhasebeci_ids = [(4, 7)]

# (5, 0, 0) → Tüm bağlantıları kopar / tüm satırları sil
satir_ids = [(5, 0, 0)]

# (6, 0, [ids]) → Sadece bu ID'leri bağlı tut (Many2many)
muhasebeci_ids = [(6, 0, [1, 2, 3])]
```

---

## R

### `readonly`
Alanı sadece okunur yapar. Kullanıcı görebilir ama değiştiremez.
`groups` ile farkı: `readonly` görünür, `groups` hiç göstermez.

```python
write_date = fields.Datetime(readonly=True)
aktif_santiye_id = fields.Many2one(compute='...', readonly=True)
```

---

### `_rec_name`
Modelin listede ve Many2one'da görünen alan adı. Varsayılan `name`.

```python
class NakliyeTaseronIsci(models.Model):
    _name = 'nakliye.taseron.isci'
    _rec_name = 'isci_adi'  # name yerine isci_adi gösterilir
```

---

### `related`
Başka bir kayıttan gelen alanı direkt gösterir. İlişki zinciri üzerinden çalışır.

```python
santiye_id = fields.Many2one(
    'nakliye.santiye',
    related='plan_satir_id.plan_id.santiye_id',  # 3 adım zincir
    store=True   # DB'ye kaydedilsin → filtrelenebilir
)
```

`store=False` (varsayılan): Her okumada ilişkiyi takip eder, yavaş.
`store=True`: DB'de tutulur, hızlı ama senkronizasyon gerekir.

---

## S

### Savepoint
Transaction içinde kısmi geri alma noktası. Tam rollback değil, sadece
savepoint'ten sonrası geri alınır.

```python
with self.env.cr.savepoint():
    number = sequence.next_by_id()  # Numara rezerve et
    send_to_sovos(...)              # Hata olursa numara geri alınır
```

---

### `search(domain, limit, order)`
Domain filtresine uyan kayıtları döndürür. Her zaman recordset döner.

```python
# Tüm kayıtlar
all_records = self.env['nakliye.santiye'].search([])

# Filtrelenmiş
aktif = self.env['nakliye.santiye'].search([('aktif', '=', True)])

# Limit
ilk = self.env['nakliye.sozlesme'].search([...], limit=1)

# Sıralı
siralı = self.search([], order='tarih desc')
```

---

### `search_count(domain)`
Domain koşulunu sağlayan kayıt sayısını döndürür. `search()` + `len()`'den hızlı.

```python
sayi = self.env['nakliye.hakedis'].search_count([('durum', '=', 'onay_bekliyor')])
```

---

### `self`
İçinde bulunulan sınıfa ve metoda göre farklı anlam taşır.

```python
class NakliyeHakedis(models.Model):
    _inherit = 'nakliye.hakedis'  # → self = hakediş kaydı/recordset

class NakliyeHakedisWizard(models.TransientModel):
    _name = 'nakliye.hakedis.wizard'  # → self = wizard kaydı

class SovosInvoiceService:  # Sıradan Python sınıfı
    def __init__(self, company):
        self.company = company  # → self = SovosInvoiceService nesnesi
```

Metodda parametre olarak geliyorsa dışarıdan gönderilmiş:
```python
def _sync_for_company(self, company):
    # self = sovos.sync kaydı
    # company = dışarıdan gelen res.company kaydı
```

---

### `size`
Char alanında maksimum karakter sayısı. DB'de VARCHAR(n) oluşturur.
Yazılmazsa sınırsız (VARCHAR).

```python
plaka = fields.Char(size=10)    # Plaka maks 10 karakter
x_sovos_uuid = fields.Char(size=36)  # UUID her zaman 36 karakter
```

---

### `sorted()`
Recordset'i belirtilen alana göre sıralar.

```python
# Tarihe göre artan
siralı = records.sorted(lambda r: r.tarih)

# Tutara göre azalan
siralı = records.sorted(lambda r: r.tutar, reverse=True)

# Alan adı ile (string)
siralı = records.sorted('tarih')
```

---

### `store` (Computed Alan)
Computed alanın DB'ye yazılıp yazılmayacağı.

```python
# store=True → DB'ye yazılır
toplam_km = fields.Float(compute='_compute_toplam_km', store=True)
# → SQL WHERE toplam_km > 100 yapılabilir
# → ir.rule'da kullanılabilir
# → Raporlarda filtrelenebilir

# store=False (varsayılan) → DB'ye yazılmaz
x_show_8day_warning = fields.Boolean(compute='_compute_warning', store=False)
# → Her okumada hesaplanır
# → Arama/filtreleme yapılamaz
```

---

### `string`
Alanın ekranda görünen etiketi. Tüm view'larda bu metin gösterilir.

```python
durum = fields.Selection(string='Durum', ...)
# Form ekranında: "Durum" etiketi görünür
```

---

### `super()`
Override edilen metodun orijinal (parent) versiyonunu çalıştırır.
Yazılmazsa parent metodun işlevselliği tamamen kaybolur.

```python
def action_post(self):
    efatura_moves = self.filtered(lambda m: m.move_type == 'out_invoice')
    other_moves = self - efatura_moves

    for move in efatura_moves:
        move._efatura_post_single()  # Bizim akışımız

    if other_moves:
        super(AccountMove, other_moves).action_post()  # Odoo'nun orijinali
```

`super(Sinif, kayitlar).metod()` → belirli kayıtlar için parent metodunu çalıştır.

---

## T

### `time.sleep(saniye)`
Python kodunu belirli süre bekletir. Arka plan işlemlerinde rate limit
kontrolü için kullanılır.

```python
time.sleep(0.5)  # 500ms bekle → Sovos rate limit (maks 2 req/sn)
```

---

### `tracking=True`
Alan değiştiğinde chatter'a otomatik log yazar. `mail.thread` gerektirir.

```python
durum = fields.Selection([...], tracking=True)
# Durum: Taslak → Onaylandı
# Kim değiştirdi, ne zaman değiştirdi chatter'da görünür
```

---

### `TransientModel`
Bkz. `models.TransientModel`

---

## U

### `UserError`
Kullanıcıya gösterilen hata mesajı. İşlemi durdurur, ekranda popup açar.
Transaction rollback yapar.

```python
from odoo.exceptions import UserError

if not kayit.satir_ids:
    raise UserError("Satır olmadan onaylanamaz!")
```

`ValidationError` ile farkı:
- `UserError` → genel iş hatası, herhangi bir yerde kullanılabilir
- `ValidationError` → genellikle `@api.constrains` içinde veri doğrulama hatası
  İkisi kullanıcıya aynı şekilde gösterilir, teknik fark azdır.

---

## V

### `ValidationError`
Veri doğrulama hatası. `@api.constrains` içinde yaygın kullanılır.
`UserError` gibi davranır, ekranda popup gösterir.

```python
from odoo.exceptions import ValidationError

@api.constrains('brut_kg', 'tara_kg')
def _check_agirlik(self):
    for kayit in self:
        if kayit.brut_kg < kayit.tara_kg:
            raise ValidationError("Brüt ağırlık tara ağırlığından küçük olamaz!")
```

---

## W

### `with_company(company)`
Multi-company ortamda belirli şirket bağlamında işlem yapar.

```python
AccountMove = self.env['account.move'].with_company(company)
pending = AccountMove.search([('x_efatura_status', '=', 'sent')])
```

---

### `write(vals)`
Mevcut kaydı günceller. DB'ye SQL UPDATE yapar.
Birden fazla alanı tek seferde günceller (tek SQL).

```python
# Tek alan
kayit.write({'durum': 'onaylandi'})

# Birden fazla alan (tek SQL UPDATE — daha performanslı)
kayit.write({
    'durum': 'onaylandi',
    'x_efatura_status': 'sent',
    'x_sovos_uuid': uuid,
})
```

`self.alan = deger` ile farkı:
- Direkt atama sadece Python nesnesinde değiştirir, DB'ye yazmaz
- `write()` DB'ye yazar + yetki kontrolü + tracking + computed yeniden hesap

---

### `write_date`
Odoo'nun her modelde otomatik tuttuğu son güncelleme tarihi.
`fields.Datetime`, `readonly=True`, Odoo otomatik günceller.

```python
onay_bekleyenler = self.search([
    ('durum', '=', 'onay_bekliyor'),
    ('write_date', '<=', bekleme_tarihi),  # X günden beri güncellenmemiş
])
```

---

## X

### `x_` (Özel Alan Öneki)
Odoo standart alanları ile çakışmayı önlemek için özel modüllerde
eklenen alanlara `x_` öneki koyulması yaygın bir pratiktir.

```python
x_efatura_status  = fields.Selection(...)  # Özel alan
x_sovos_uuid      = fields.Char(...)       # Özel alan
invoice_date      = fields.Date(...)       # Odoo standart alanı (önek yok)
```

Zorunlu değil ama kod okunabilirliği için tercih edilir.

---

## Z

### `[:1]` (Recordset Dilimleme)
Recordset'in ilk kaydını alır. `limit=1` ile arama yerine mevcut recordset'te kullanılır.
Boş recordset'te `IndexError` değil boş recordset döner.

```python
aktif_atama = santiye_atama_ids.filtered(lambda a: a.aktif and not a.bitis_tarihi)
kayit.aktif_santiye_id = aktif_atama[:1].santiye_id  # Boşsa False döner
```

---

## Hızlı Başvuru Tablosu

### Alan Tipleri

| Tip | DB Karşılığı | Boş Değer | Örnek Kullanım |
|-----|-------------|-----------|----------------|
| `Char` | VARCHAR | False | İsim, kod, UUID |
| `Text` | TEXT | False | Açıklama, notlar |
| `Integer` | INTEGER | 0 | Adet, gün sayısı |
| `Float` | NUMERIC | 0.0 | Tutar, km, oran |
| `Boolean` | BOOLEAN | False | Aktif/pasif |
| `Date` | DATE | False | İşlem tarihi |
| `Datetime` | TIMESTAMP | False | Oluşturma zamanı |
| `Selection` | VARCHAR | False | Durum, tip |
| `Many2one` | INTEGER (FK) | False | Şantiye, partner |
| `One2many` | - (virtual) | [] | Satır listesi |
| `Many2many` | Ara tablo | [] | Çoklu ilişki |

---

### Dekoratörler

| Dekoratör | Ne Zaman | Nerede |
|-----------|----------|--------|
| `@api.model` | Kayıt bağımsız | create, search, cron |
| `@api.depends` | Computed alan | _compute_ metodları |
| `@api.constrains` | Veri doğrulama | _check_ metodları |
| `@api.onchange` | Form değişimi | _onchange_ metodları |

---

### ORM Metodları

| Metod | Ne Yapar | SQL Karşılığı |
|-------|----------|---------------|
| `search(domain)` | Kayıt bul | SELECT + WHERE |
| `search_count(domain)` | Kayıt say | SELECT COUNT |
| `create(vals)` | Yeni kayıt | INSERT |
| `write(vals)` | Güncelle | UPDATE |
| `unlink()` | Sil | DELETE |
| `browse(id)` | ID ile eriş | - |
| `filtered(lambda)` | Filtrele | WHERE (Python'da) |
| `mapped(field)` | Alan listesi | SELECT alan |
| `sorted(key)` | Sırala | ORDER BY (Python'da) |
| `ensure_one()` | Tek kayıt garantisi | - |

---

### Exception Tipleri

| Exception | Ne Zaman | Kullanıcıya |
|-----------|----------|-------------|
| `UserError` | İş kuralı ihlali | Popup mesaj |
| `ValidationError` | Veri doğrulama | Popup mesaj |
| `AccessError` | Yetki yok | Erişim reddedildi |
| `MissingError` | Kayıt silinmiş | Kayıt bulunamadı |

---

### Log Seviyeleri

| Seviye | Ne Zaman | Üretimde Görünür? |
|--------|----------|-------------------|
| `DEBUG` | Geliştirme detayı | Hayır (varsayılan) |
| `INFO` | Rutin bilgi | Hayır (varsayılan) |
| `WARNING` | Beklenmedik, iş devam ediyor | Evet |
| `ERROR` | Ciddi hata, müdahale gerekebilir | Evet |
| `CRITICAL` | Sistem çöküyor | Evet |

