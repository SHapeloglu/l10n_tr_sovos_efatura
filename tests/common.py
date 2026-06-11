# -*- coding: utf-8 -*-
"""
Ortak Test Altyapısı — SovosTestCommon
========================================
Bu dosya tüm test sınıflarının miras aldığı temel sınıfı tanımlar.
Burada yapılan her şey her test çalışmadan ÖNCE otomatik hazırlanır.

TEMEL KAVRAMLAR (junior developer için):
-----------------------------------------
• TransactionCase: Odoo'nun test base sınıfı. Her test metodu kendi veritabanı
  transaction'ı içinde çalışır. Test bitince tüm değişiklikler GERİ ALINIR
  (rollback). Bu yüzden testler birbirini etkilemez, veritabanı kirlenmez.

• setUp(): Her test metodundan ÖNCE çalışır. Temiz bir ortam hazırlar.
  "Sahne kurulumu" gibi düşün — her oyundan önce sahne sıfırlanır.

• Mock (sahte nesne): Gerçek Sovos API'sine veya GİB'e bağlanmak yerine
  "sanki bağlandı, şu sonucu döndü" diyebilmemizi sağlar. Bu sayede testler
  internet bağlantısı olmadan, çok hızlı ve güvenilir şekilde çalışır.

v6.1 güncel: _release_number() parametresiz, super().action_post() sırası değişti,
saxonche/UblValidator yeni imza, e-Arşiv ayrı cron.
"""

# date: tarih işlemleri için (bugün, dün, 30 gün sonra vb.)
# timedelta: tarihe gün eklemek/çıkarmak için (date.today() + timedelta(days=8))
from datetime import date, timedelta

# patch: bir fonksiyon veya sınıfı geçici olarak SAHTE bir şeyle değiştirmek için
# MagicMock: otomatik olarak her metoda ve attribute'a cevap veren sahte nesne
from unittest.mock import patch, MagicMock

# Odoo'nun test altyapısı — TransactionCase her testten sonra DB'yi geri alır
from odoo.tests.common import TransactionCase


class SovosTestCommon(TransactionCase):
    """
    Tüm Sovos test sınıfları bu sınıftan miras alır.
    Ortak kurulum (setUp) ve yardımcı metodları burada tanımlanır.

    Miras yapısı:
        TestAtomicNumber(SovosTestCommon)
            └── SovosTestCommon(TransactionCase)
                    └── TransactionCase (Odoo base)
    """

    @classmethod
    def setUpClass(cls):
        """
        TÜM testlerden ÖNCE bir kez çalışır (sınıf düzeyinde kurulum).
        Şu an sadece parent'ı çağırıyor — ileride sınıf düzeyinde
        paylaşılan veriler buraya eklenebilir.
        """
        super().setUpClass()

    def setUp(self):
        """
        HER test metodundan ÖNCE çalışır. Test ortamını sıfırdan kurar.
        Bu metod bitince test metodu çalışır, sonra otomatik rollback yapılır.

        Bu metodda yapılanlar:
          1. Şirket yapılandırması (Sovos credentials)
          2. Fatura numara serisi
          3. Test müşterileri (e-Fatura, e-Arşiv, cache boş)
          4. Test ürünü
          5. Muhasebe hesabı ve satış defteri
        """
        # Parent setUp'ı çağır — Odoo'nun kendi hazırlıklarını yapsın
        super().setUp()

        # ── 1. Şirket Yapılandırması ──────────────────────────────────────────
        # self.env.company: aktif test şirketi (Odoo'nun varsayılan demo şirketi)
        self.company = self.env.company

        # write(): mevcut kaydı günceller. create() değil çünkü şirket zaten var.
        self.company.write({
            # Şirketin vergi kimlik numarası
            'vat': '1234567890',

            # Sovos e-Fatura servisi kullanıcı adı/şifresi
            # Gerçek değerlerin yerine test değerleri — Sovos'a gerçekten bağlanmayacağız
            'x_sovos_invoice_user': 'test_invoice_user',
            'x_sovos_invoice_pass': 'test_invoice_pass',

            # Sovos e-Arşiv servisi kullanıcı adı/şifresi
            'x_sovos_archive_user': 'test_archive_user',
            'x_sovos_archive_pass': 'test_archive_pass',

            # GİB'e gönderici olarak görünen VKN
            'x_sovos_sender_vkn': '1234567890',

            # Sovos'ta şirketi tanımlayan benzersiz ID (GB + VKN formatı)
            'x_sovos_identifier': 'GB1234567890',

            # Sovos portal'daki fatura şablonu ID'si
            'x_sovos_template_id': 'TMPL001',

            # TEST MODU AÇIK: True iken GİB'e gerçek iletim YAPILMAZ
            # Bu sayede testlerde yanlışlıkla gerçek fatura gönderilmez
            'x_sovos_test_mode': True,

            # Hata bildirimlerinin gideceği admin e-posta adresi
            'x_sovos_admin_email': 'admin@test.com',
        })

        # ── 2. Fatura Numara Serisi ───────────────────────────────────────────
        # e-Fatura numaraları belirli bir formatta olmalı: TST2026000000001 gibi
        # ir.sequence: Odoo'nun otomatik numara üretme mekanizması
        self.invoice_sequence = self.env['ir.sequence'].create({
            'name': 'Test e-Fatura Serisi',
            # code: bu serisi çağırmak için kullanılan anahtar
            'code': 'test.efatura',
            # prefix: numaranın başına eklenen metin. %(year)s → 2026 gibi yıl girer
            'prefix': 'TST%(year)s',
            # padding: rakam kısmının kaç basamaklı olacağı (9 → 000000001)
            'padding': 9,
            # Her çağrıda kaç artacağı (1 = 1, 2, 3, ...)
            'number_increment': 1,
            # Başlangıç numarası
            'number_next': 1,
            'company_id': self.company.id,
        })
        # Şirkete bu seriyi ata: fatura oluşturulunca bu seri kullanılacak
        self.company.x_invoice_sequence_id = self.invoice_sequence

        # ── 3a. e-Fatura Müşterisi ────────────────────────────────────────────
        # GİB sistemine KAYITLI müşteri → e-Fatura (InvoiceService) ile gönderilir
        self.partner_efatura = self.env['res.partner'].create({
            'name': 'Test Ticaret A.Ş.',
            # 10 haneli VKN (Vergi Kimlik Numarası) — tüzel kişi
            'vat': '9876543210',
            'email': 'test@testticaret.com',
            # x_efatura_type: 'efatura' → GİB'e kayıtlı, InvoiceService kullan
            'x_efatura_type': 'efatura',
            # x_default_scenario: TICARIFATURA → ticari fatura (karşılıklı kabul/red var)
            # Alternatif: TEMELFATURA (tek taraflı)
            'x_default_scenario': 'TICARIFATURA',
            # Cache ne zaman güncellendi — bugün → taze, yenileme gerekmez
            'x_efatura_type_updated': date.today(),
            'x_vergi_dairesi': 'Büyük Mükellefler',
            # Türkiye'yi seç: GİB e-Fatura sadece Türkiye'de geçerli
            'country_id': self.env.ref('base.tr').id,
        })

        # ── 3b. e-Arşiv Müşterisi ────────────────────────────────────────────
        # GİB sistemine KAYITSIZ müşteri → e-Arşiv (ArchiveService) ile gönderilir
        self.partner_earsiv = self.env['res.partner'].create({
            'name': 'Bireysel Müşteri',
            # 11 haneli TC Kimlik Numarası (bireysel kişi)
            'vat': '12345678901',
            'email': 'bireysel@gmail.com',
            # x_efatura_type: 'earsiv' → GİB'e kayıtsız, ArchiveService kullan
            'x_efatura_type': 'earsiv',
            'x_default_scenario': 'EARSIVFATURA',
            'x_efatura_type_updated': date.today(),
            'country_id': self.env.ref('base.tr').id,
        })

        # ── 3c. Cache Boş Müşteri ────────────────────────────────────────────
        # x_efatura_type ve güncellenme tarihi YOK → gönderimde Sovos'a sorgu atılır
        # Bu müşteriyle yapılan testler VKN cache davranışını test eder
        self.partner_no_cache = self.env['res.partner'].create({
            'name': 'Yeni Müşteri Ltd.',
            'vat': '5555555555',
            'email': 'yeni@musteri.com',
            # False = boş/None — e-fatura tipi henüz bilinmiyor
            'x_efatura_type': False,
            'x_efatura_type_updated': False,
            'country_id': self.env.ref('base.tr').id,
        })

        # ── 4. Test Ürünü ─────────────────────────────────────────────────────
        self.product = self.env['product.product'].create({
            'name': 'Test Ürünü',
            # type='service': stoğu olmayan hizmet ürünü — depo hareketi yaratmaz
            # Bu testler için daha basit, stok hareketleri test dışı
            'type': 'service',
            'list_price': 1000.0,
        })

        # ── 5a. Gelir Hesabı ──────────────────────────────────────────────────
        # Fatura satır kaydı için muhasebe hesabı gerekli
        # search() ile mevcut gelir hesabını bul (yeni oluşturmak yerine)
        self.account_income = self.env['account.account'].search([
            # Domain filtresi: (alan, operatör, değer) formatında liste
            ('account_type', '=', 'income'),          # gelir tipi hesaplar
            ('company_id', '=', self.company.id),     # bu şirkete ait
        ], limit=1)  # sadece 1 kayıt döndür

        # ── 5b. Satış Defteri (Journal) ───────────────────────────────────────
        # account.journal: muhasebe kayıtlarının hangi deftere yazılacağı
        self.sale_journal = self.env['account.journal'].search([
            ('type', '=', 'sale'),                    # satış defteri
            ('company_id', '=', self.company.id),
        ], limit=1)

    # ════════════════════════════════════════════════════════════════════════
    # FACTORY METODLARI
    # "Factory" = nesne üretmek için hazır şablon metodlar.
    # Testlerde her seferinde uzun create() yazmak yerine bu metodları çağırırız.
    # ════════════════════════════════════════════════════════════════════════

    def _create_invoice(self, partner=None, lines=None, **kwargs):
        """
        Test faturası oluşturur. State=DRAFT, henüz gönderilmemiş.

        Parametreler:
            partner: Müşteri kaydı. Verilmezse self.partner_efatura kullanılır.
            lines: [(miktar, birim_fiyat, hesap), ...] formatında satır listesi.
                   Verilmezse [(1 adet, 1000 TL, gelir hesabı)] kullanılır.
            **kwargs: account.move alanlarını override etmek için.
                      Örn: _create_invoice(invoice_date=False)

        Döndürür: account.move kaydı (taslak fatura)
        """
        # Parametre verilmemişse varsayılanları kullan
        if partner is None:
            partner = self.partner_efatura
        if lines is None:
            # 1 adet, 1000 TL birim fiyat, gelir hesabı
            lines = [(1, 1000.0, self.account_income)]

        # Odoo'da many2many/one2many için özel yazım:
        # (0, 0, {değerler}) → yeni kayıt oluştur ve bağla
        # (1, id, {değerler}) → mevcut kaydı güncelle
        # (2, id) → kaydı sil ve bağlantıyı kaldır
        line_vals = [(0, 0, {
            'name': 'Test Kalemi',
            'quantity': qty,
            'price_unit': price,
            'account_id': account.id,
        }) for qty, price, account in lines]

        # Temel fatura değerleri
        vals = {
            # out_invoice: satış faturası (müşteriye)
            # Alternatifler: in_invoice (alış), out_refund (iade) vb.
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_date': date.today(),
            'journal_id': self.sale_journal.id,
            'invoice_line_ids': line_vals,
        }

        # kwargs ile gelen ekstra değerleri üzerine yaz
        # Örn: _create_invoice(invoice_date=False) → tarihi siler
        vals.update(kwargs)

        return self.env['account.move'].create(vals)

    def _create_sent_invoice(self, partner=None, scenario='TICARIFATURA', **kwargs):
        """
        Daha önce GÖNDERILMIŞ gibi hazırlanmış fatura oluşturur.
        Sovos API'si çağrılmaz — DB'ye direkt yazılır.

        Bu ne zaman kullanılır?
            Gönderim SONRASI test edilmesi gereken durumlar için:
            - İptal wizard'ı testleri (gönderilmiş faturayı iptal etmek)
            - GİB durum kodu işleme testleri (zaten gönderilmiş, cevap bekleniyor)
            - Tekrar gönderim testleri

        Döndürür: state=posted, x_efatura_status='sent' olan fatura
        """
        if partner is None:
            partner = self.partner_efatura

        # Önce normal taslak fatura oluştur
        inv = self._create_invoice(partner=partner, **kwargs)

        # Ardından "gönderilmiş" durumuna zorla
        # NOT: Normalde action_post() bunu yapar ama burada Sovos'u bypass ediyoruz
        inv.write({
            'state': 'posted',                          # Odoo muhasebe durumu: onaylandı
            'name': 'TST2026000000001',                 # Atanmış fatura numarası
            # UUID: GİB'te faturaları tanımlayan benzersiz kimlik (UUID v4 formatı)
            'x_sovos_uuid': 'test-uuid-1234-5678-abcd-ef0123456789',
            # Envelope UUID: Sovos'un zarfı için UUID (birden fazla fatura bir zarfta gelebilir)
            'x_sovos_envelope_uuid': 'env-uuid-1234-5678-abcd-ef0123456789',
            # Partner'ın e-fatura tipi (efatura veya earsiv)
            'x_efatura_type': partner.x_efatura_type if partner else 'efatura',
            'x_efatura_scenario': scenario,             # TICARIFATURA, TEMELFATURA, EARSIVFATURA
            'x_efatura_status': 'sent',                 # Sovos'a gönderildi, GİB cevabı bekleniyor
            'x_efatura_send_date': '2026-06-01 10:00:00',
            # Numara onaylandı (Sovos başarı döndürdü)
            'x_number_status': 'confirmed',
            'x_reserved_number': 'TST2026000000001',
        })

        # TICARIFATURA'larda ticari kabul/red süreci var
        # Alıcı 8 gün içinde KABUL veya RED bildirmeli
        if scenario == 'TICARIFATURA':
            inv.write({
                # Henüz kabul/red gelmedi
                'x_inv_response_status': 'beklemede',
                # Son gün: bugünden 8 gün sonra
                'x_inv_response_deadline': date.today() + timedelta(days=8),
            })

        return inv

    # ════════════════════════════════════════════════════════════════════════
    # MOCK YARDIMCILARI
    #
    # "Mock" nedir?
    #   Gerçek bir nesne veya fonksiyonun SAHTE versiyonu.
    #   Testlerde dış bağımlılıkları (Sovos API, GİB) devre dışı bırakır.
    #
    # "patch" nedir?
    #   with patch('modül.Sınıf.metod', return_value=...): bloğu içinde
    #   o metod çağrıldığında gerçek kod yerine sahte değer döner.
    #
    # Neden gerekli?
    #   • Sovos API'sine gerçekten bağlanmak testleri yavaşlatır
    #   • Test ortamında gerçek credentials olmayabilir
    #   • Hata senaryoları (timeout, 429 vb.) gerçek ortamda tetiklemek zordur
    #   • Testler deterministik olmalı — her çalışmada aynı sonucu vermeli
    #
    # v6.1 NOT: UblValidator artık bir sınıf instance'ı — patch yolu güncellendi
    # ════════════════════════════════════════════════════════════════════════

    def _mock_ubl_builder(self):
        """
        UblBuilder.build() metodunu sahte XML döndürecek şekilde mock'lar.

        Gerçekte ne yapar: Fatura nesnesinden UBL-TR 2.1 formatında XML üretir.
        Test için: Minimal geçerli XML byte string döndürür.

        Neden mock'lanır?
            UBL üretimi karmaşık ve yavaş olabilir. Biz sadece "build çağrıldı mı?"
            veya "build sonrası ne olur?" sorularını test etmek istiyoruz.
        """
        # Minimal geçerli XML — sadece "birşey döndü" demek için yeterli
        dummy_xml = b'<?xml version="1.0" encoding="UTF-8"?><Invoice>TEST</Invoice>'
        return patch(
            # Tam Python import yolu: paket.modül.Sınıf.metod
            'l10n_tr_sovos_efatura.services.ubl_builder.UblBuilder.build',
            return_value=dummy_xml,   # çağrıldığında bu değeri döndür
        )

    def _mock_validator_valid(self):
        """
        UblValidator.validate() → başarılı sonuç döndürür.

        Dönüş değeri: (True, None, [])
            • True  → validasyon geçti
            • None  → hata katmanı yok (XSD veya SCHEMATRON değil)
            • []    → hata listesi boş

        Kullanım: Validasyonun geçtiğini, gönderimin devam etmesi gerektiğini
        simüle etmek istediğimizde.
        """
        return patch(
            'l10n_tr_sovos_efatura.services.ubl_validator.UblValidator.validate',
            return_value=(True, None, []),
        )

    def _mock_validator_xsd_fail(self, errors=None):
        """
        UblValidator.validate() → XSD validasyon hatası döndürür.

        Dönüş değeri: (False, 'XSD', ['hata mesajı', ...])
            • False     → validasyon başarısız
            • 'XSD'     → hangi katmanda hata olduğu
            • errors    → GİB XSD şema hata mesajları

        Parametreler:
            errors: Özel hata mesajları listesi. Verilmezse varsayılan kullanılır.

        Kullanım: XML'in GİB XSD şemasına uymadığı senaryoları test etmek için.
        Örn: Zorunlu alan eksik (cbc:ID, cbc:IssueDate vb.)
        """
        return patch(
            'l10n_tr_sovos_efatura.services.ubl_validator.UblValidator.validate',
            # errors or [...] → errors None/boş ise varsayılan hata mesajını kullan
            return_value=(False, 'XSD', errors or ['cbc:ID zorunlu alan eksik']),
        )

    def _mock_validator_schematron_fail(self, errors=None):
        """
        UblValidator.validate() → Schematron kural ihlali döndürür.

        Schematron nedir?
            XSD'den farklı olarak XML yapısını değil, iş kurallarını kontrol eder.
            Örn: "Vergi tutarı, matrah × vergi oranına eşit olmalı"
            Bu tür mantık kuralları XSD ile ifade edilemez, Schematron ile yapılır.

        Dönüş değeri: (False, 'SCHEMATRON', ['BR-01: ...'])
            BR-XX kodları GİB'in iş kuralı (Business Rule) kodlarıdır.
        """
        return patch(
            'l10n_tr_sovos_efatura.services.ubl_validator.UblValidator.validate',
            return_value=(False, 'SCHEMATRON', errors or ['BR-01: Fatura numarası zorunlu']),
        )

    def _mock_validator_parse_fail(self):
        """
        UblValidator.validate() → XML_PARSE katmanı hatası döndürür.
        v6.1 ile eklendi: XML sözdizimi bozuksa (well-formed değilse) bu katman devreye girer.

        XSD'den ÖNCE gelir: XML parse edilemiyorsa zaten XSD'ye gerek yok.

        Dönüş değeri: (False, 'XML_PARSE', ['XML sözdizim hatası satır 1'])
        """
        return patch(
            'l10n_tr_sovos_efatura.services.ubl_validator.UblValidator.validate',
            return_value=(False, 'XML_PARSE', ['XML sözdizim hatası satır 1']),
        )

    def _mock_sovos_invoice_success(self):
        """
        SovosInvoiceService.send_ubl() → başarılı gönderim simüle eder.

        Gerçekte ne yapar: XML'i Sovos'a gönderir, Sovos GİB'e iletir.
        Döndürür: envelope_uuid (Sovos zarfını tanımlayan benzersiz ID)

        Bu mock ile:
            inv.x_sovos_envelope_uuid == 'mock-envelope-uuid' olur
            inv.x_efatura_status == 'sent' olur
        """
        return patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.send_ubl',
            return_value='mock-envelope-uuid',   # gerçekte Sovos'tan gelen UUID
        )

    def _mock_sovos_archive_success(self):
        """
        SovosArchiveService.send_invoice() → başarılı e-Arşiv gönderimi simüle eder.

        e-Arşiv, GİB'e kayıtsız alıcılara gönderilen fatura türüdür.
        InvoiceService DEĞİL, ArchiveService kullanılır.
        """
        return patch(
            'l10n_tr_sovos_efatura.services.sovos_archive_service'
            '.SovosArchiveService.send_invoice',
            return_value='mock-archive-uuid',
        )

    def _mock_sovos_failure(self, msg='Sovos bağlantı hatası'):
        """
        SovosInvoiceService.send_ubl() → exception fırlatır (bağlantı hatası simülasyonu).

        side_effect=Exception(...) → metod çağrıldığında exception fırlatır.
        return_value ile fark: return_value değer döndürür, side_effect hata fırlatır.

        Kullanım: Sovos erişilemez olduğunda ne olduğunu test etmek için.
        Beklenen davranış: numara serbest bırakılmalı, fatura draft'a dönmeli.
        """
        return patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.send_ubl',
            side_effect=Exception(msg),    # çağrıldığında Exception fırlatır
        )

    def _mock_vkn_check(self, is_registered=True):
        """
        SovosInvoiceService.check_vkn_registered() → sahte VKN sorgu sonucu döndürür.

        Gerçekte ne yapar: Sovos API'sine VKN gönderir, GİB'e kayıtlı mı diye sorar.
        Test için: Sorgu yapmadan direkt True/False döndürür.

        Parametreler:
            is_registered=True  → bu VKN GİB'e kayıtlı (efatura)
            is_registered=False → bu VKN GİB'e kayıtsız (earsiv)
        """
        return patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.check_vkn_registered',
            return_value=is_registered,
        )

    def _mock_vkn_check_failure(self):
        """
        SovosInvoiceService.check_vkn_registered() → bağlantı hatası simüle eder.

        Kullanım: Sovos erişilemezken VKN sorgusu yapılmaya çalışıldığında
        ne olacağını test etmek için.
        Beklenen davranış: Mevcut cache korunmalı, işlem bloke edilmemeli.
        """
        return patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.check_vkn_registered',
            side_effect=Exception('Sovos bağlantı hatası'),
        )
