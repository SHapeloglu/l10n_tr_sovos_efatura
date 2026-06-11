# -*- coding: utf-8 -*-
"""
Atomik Numara Rezervasyonu Testleri — v6.1
==========================================
Test edilen kod: models/account_move.py
Test edilen metodlar:
  • _reserve_invoice_number()  → numara rezerve et
  • _release_number()          → numarayı serbest bırak (hata durumunda)

NEDEN "ATOMİK"?
---------------
e-Fatura numaraları sıralı ve boşluksuz olmalıdır (GİB mevzuatı).
Numara rezerve edilip fatura başarısız olursa o numara "kaybolur" — GİB'e
TST2026000000003 gönderilmişse TST2026000000002 de bir yerlerde olmalı.

Akış:
    1. Numara REZERVE edilir (x_number_status='reserved')
    2. UBL üretilir
    3. Validasyon yapılır
    4. Sovos'a gönderilir
    → HERHANGİ bir adımda hata çıkarsa numara SERBEST bırakılır (x_number_status='released')

"Released" numara bir sonraki gönderimde tekrar kullanılabilir.

v6.1 Değişiklikler:
  - _release_number() artık parametresiz (self üzerinden çalışır)
  - super().action_post() validasyon SONRASI, Sovos ÖNCE çağrılıyor
  - action_post() tek super() çağrısı → çift post riski giderildi

Risk Seviyesi: KRİTİK — GİB uyumsuzluğu, muhasebe açıkları
"""
from unittest.mock import patch

from odoo.exceptions import UserError

from .common import SovosTestCommon


class TestAtomicNumber(SovosTestCommon):
    """
    Fatura numarası yaşam döngüsü testleri.

    Numara durumları (x_number_status):
        None/False  → henüz rezerve edilmedi (taslak)
        'reserved'  → rezerve edildi, gönderim devam ediyor
        'confirmed' → Sovos başarı döndürdü, numara kalıcı
        'released'  → hata nedeniyle serbest bırakıldı, tekrar kullanılabilir
    """

    # ════════════════════════════════════════════════════════════════════
    # BAŞARILI AKIŞ
    # Her şey yolunda gittiğinde ne olmalı?
    # ════════════════════════════════════════════════════════════════════

    def test_number_confirmed_on_successful_send(self):
        """
        Başarılı gönderimde tüm numara ve durum alanları doğru set edilmeli.

        Kontrol listesi:
            ✓ x_number_status = 'confirmed'  (numara kalıcı)
            ✓ x_reserved_number dolu         (hangi numara kullanıldı)
            ✓ inv.name = x_reserved_number   (fatura adı numara ile eşleşiyor)
            ✓ x_sovos_uuid dolu              (GİB'teki benzersiz kimlik)
            ✓ x_efatura_status = 'sent'      (gönderildi, cevap bekleniyor)
            ✓ state = 'posted'               (Odoo muhasebe durumu onaylandı)
        """
        inv = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            inv.action_post()

        self.assertEqual(inv.x_number_status, 'confirmed')
        self.assertTrue(inv.x_reserved_number)
        # Fatura adı (inv.name) rezerve edilen numara ile aynı olmalı
        self.assertEqual(inv.name, inv.x_reserved_number)
        self.assertTrue(inv.x_sovos_uuid)
        self.assertEqual(inv.x_efatura_status, 'sent')
        self.assertEqual(inv.state, 'posted')

    def test_envelope_uuid_saved_from_sovos(self):
        """
        Sovos'tan dönen envelope UUID x_sovos_envelope_uuid alanına kaydedilmeli.

        Envelope UUID nedir?
            Sovos faturayı bir "zarf" (envelope) içine koyar.
            Zarf birden fazla fatura içerebilir.
            Zarf UUID'si ile GİB'teki durumu takip ederiz.

        Mock'tan dönen değer: 'mock-envelope-uuid' (common.py'da tanımlandı)
        """
        inv = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():  # 'mock-envelope-uuid' döner
            inv.action_post()
        self.assertEqual(inv.x_sovos_envelope_uuid, 'mock-envelope-uuid')

    def test_invoice_state_is_posted_after_success(self):
        """
        v6.1 ÖNEMLİ: super().action_post() çağrı sırası değişti.

        v6.0: super() ÖNCE → state=posted → sonra Sovos'a gönder
        v6.1: super() validasyon SONRASI, Sovos'tan ÖNCE

        Bu test v6.1 sırasının doğru çalıştığını doğrular:
        Sovos başarılıysa state=posted olmalı.
        """
        inv = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            inv.action_post()
        self.assertEqual(inv.state, 'posted')

    # ════════════════════════════════════════════════════════════════════
    # HATA SENARYOLARI — Her birinde numara SERBEST bırakılmalı
    # "Ne olursa olsun numara kaybolmasın" ilkesi
    # ════════════════════════════════════════════════════════════════════

    def test_number_released_on_ubl_build_failure(self):
        """
        UBL üretimi başarısız → numara serbest, fatura taslak kalmalı.

        Akış:
            1. Numara rezerve edildi ✓
            2. UblBuilder.build() → HATA (lxml serialize hatası)
            3. Numara serbest bırakılmalı
            4. Fatura state=draft kalmalı (super() henüz çağrılmadı)

        v6.1'de neden state=draft kalır?
            super().action_post() UBL üretiminden SONRA çağrılıyor.
            UBL üretimi başarısız olunca super() hiç çağrılmaz → state değişmez.
        """
        inv = self._create_invoice()

        # _mock_ubl_builder() kullanmıyoruz — doğrudan HATA mock'u yazıyoruz
        with patch(
            'l10n_tr_sovos_efatura.services.ubl_builder.UblBuilder.build',
            side_effect=Exception('lxml serialize hatası'),  # exception fırlatır
        ):
            with self.assertRaises(UserError):
                inv.action_post()

        # Numara serbest bırakıldı mı?
        self.assertEqual(inv.x_number_status, 'released')
        # Hata durumu set edildi mi?
        self.assertEqual(inv.x_efatura_status, 'error')
        # Fatura taslak mı kaldı?
        self.assertEqual(inv.state, 'draft',
            'UBL üretim hatasında fatura draft kalmalıydı')

    def test_number_released_on_xsd_failure(self):
        """
        XSD validasyon hatası → numara serbest, validasyon hataları kaydedilmeli.

        Akış:
            1. Numara rezerve edildi ✓
            2. UBL üretildi ✓
            3. UblValidator.validate() → (False, 'XSD', ['hata']) döndü
            4. Numara serbest bırakılmalı
            5. x_validation_errors: hata mesajları kaydedilmeli
            6. state=draft kalmalı (v6.1)

        x_validation_errors: Kullanıcıya "XML'inizde şu hatalar var" diye gösterilir.
        """
        inv = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_xsd_fail(['cbc:ID zorunlu']):
            with self.assertRaises(UserError):
                inv.action_post()

        self.assertEqual(inv.x_number_status, 'released')
        self.assertEqual(inv.x_efatura_status, 'error')
        self.assertEqual(inv.state, 'draft')
        # Hata mesajı x_validation_errors alanında saklanmış olmalı
        self.assertIn('cbc:ID', inv.x_validation_errors)

    def test_number_released_on_schematron_failure(self):
        """
        Schematron kural ihlali → numara serbest, hata mesajı kaydedilmeli.

        Schematron vs XSD farkı:
            XSD: XML yapısı doğru mu? (tag isimleri, tipler, zorunlu alanlar)
            Schematron: İş kuralları doğru mu? (tutarlar, oranlar, mantık kontrolleri)

        BR-01: GİB'in Business Rule kodları bu formatda gelir.
        """
        inv = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_schematron_fail(['BR-01: Tutar tutarsız']):
            with self.assertRaises(UserError):
                inv.action_post()

        self.assertEqual(inv.x_number_status, 'released')
        self.assertEqual(inv.state, 'draft')
        self.assertIn('BR-01', inv.x_validation_errors)

    def test_number_released_on_xml_parse_failure(self):
        """
        v6.1 YENİ: XML_PARSE katmanı hatası → numara serbest.

        XML_PARSE ne zaman tetiklenir?
            UblBuilder bozuk (well-formed olmayan) XML ürettiyse.
            Örn: açılan tag kapatılmamış, geçersiz karakter vb.
            Bu durumda XSD'ye bile gerek yok — XML parse edilemiyor.

        Hata mesajında 'XML_PARSE' geçmeli → kullanıcı hangi katmanda
        hata olduğunu anlayabilmeli.
        """
        inv = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_parse_fail():
            with self.assertRaises(UserError) as cm:
                inv.action_post()

        self.assertEqual(inv.x_number_status, 'released')
        # Hata mesajında katman adı geçmeli
        self.assertIn('XML_PARSE', str(cm.exception))

    def test_number_released_on_sovos_failure(self):
        """
        Sovos erişilemez → numara serbest, fatura draft'a geri dönmeli.

        v6.1 ÖZEL DURUMU:
            v6.1'de super().action_post() Sovos'tan ÖNCE çağrılıyor.
            Bu yüzden Sovos hata verdiğinde state ZATEN 'posted' olmuş.
            Kodu button_draft() çağırarak faturayı draft'a GERİ almalı.

        Karşılaştırma:
            UBL/validasyon hatası → super() henüz çağrılmadı → state=draft (doğal)
            Sovos hatası         → super() çağrıldı → state=posted → button_draft() ile geri al
        """
        inv = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_failure('Zaman aşımı (60s)'):
            with self.assertRaises(UserError):
                inv.action_post()

        self.assertEqual(inv.x_number_status, 'released')
        self.assertEqual(inv.x_efatura_status, 'error')
        # button_draft() çağrılarak fatura draft'a döndürülmüş olmalı
        self.assertEqual(inv.state, 'draft',
            "Sovos hatasında button_draft() faturayı draft'a döndürmeliydi")

    def test_number_released_on_rate_limit(self):
        """
        HTTP 429 Too Many Requests → numara serbest bırakılmalı.

        Rate limit (hız sınırı): Sovos API saniyede belirli sayıda istek kabul eder.
        Sınır aşılırsa 429 döndürür. Bu da Sovos başarısız = numara serbest akışını izler.
        """
        inv = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_failure('RATE_LIMIT_429'):
            with self.assertRaises(UserError):
                inv.action_post()
        self.assertEqual(inv.x_number_status, 'released')

    # ════════════════════════════════════════════════════════════════════
    # ÖN KOŞUL KONTROLLERİ
    # action_post() başlamadan önce yapılan doğrulamalar
    # ════════════════════════════════════════════════════════════════════

    def test_missing_sequence_raises_user_error(self):
        """
        Şirkete numara serisi atanmamışsa UserError.

        Numara serisi olmadan e-Fatura numarası üretilemez.
        Erken hata ver → kullanıcı ayarlar sayfasına yönlendirilir.
        """
        # Şirketteki numara serisini kaldır
        self.company.x_invoice_sequence_id = False
        inv = self._create_invoice()
        with self.assertRaises(UserError) as cm:
            inv.action_post()
        # Hata mesajında 'numara serisi' geçmeli
        self.assertIn('numara serisi', str(cm.exception).lower())

    def test_missing_company_vkn_raises_user_error(self):
        """
        Şirketin VKN'i yoksa UserError.

        GİB'e gönderici VKN zorunludur. VKN olmadan fatura oluşturulamaz.
        """
        self.company.x_sovos_sender_vkn = False
        inv = self._create_invoice()
        with self.assertRaises(UserError) as cm:
            inv.action_post()
        self.assertIn('VKN', str(cm.exception))

    def test_missing_partner_vkn_raises_user_error(self):
        """
        Müşterinin VKN/TCKN'i yoksa UserError.

        Alıcı vergi kimliği XML'de zorunlu alan. Boş bırakılamaz.
        """
        self.partner_efatura.vat = False
        inv = self._create_invoice()
        with self.assertRaises(UserError) as cm:
            inv.action_post()
        self.assertIn('VKN', str(cm.exception))

    def test_missing_invoice_date_raises_user_error(self):
        """
        Fatura tarihi yoksa UserError.

        GİB'e tarihsiz fatura gönderilemez.
        _create_invoice(invoice_date=False): kwargs ile tarihi silerek oluşturur.
        """
        # invoice_date=False → _create_invoice'daki vals.update(kwargs) ile override edilir
        inv = self._create_invoice(invoice_date=False)
        with self.assertRaises(UserError) as cm:
            inv.action_post()
        self.assertIn('tarih', str(cm.exception).lower())

    def test_missing_sovos_credentials_raises_user_error(self):
        """
        Sovos kullanıcı adı yoksa UserError.

        API credentials olmadan Sovos'a bağlanılamaz.
        Erken kontrol et → gönderim sırasında değil, başlangıçta hata ver.
        """
        self.company.x_sovos_invoice_user = False
        inv = self._create_invoice()
        with self.assertRaises(UserError) as cm:
            inv.action_post()
        self.assertIn('kullanıcı', str(cm.exception).lower())

    # ════════════════════════════════════════════════════════════════════
    # E-FATURA DIŞI HAREKETLER ETKİLENMEMELİ
    # ════════════════════════════════════════════════════════════════════

    def test_purchase_invoice_bypasses_efatura(self):
        """
        Alış faturası (in_invoice) e-Fatura akışına GİRMEMELİ.

        Modül sadece satış faturalarını (out_invoice) GİB'e gönderir.
        Alış faturası: tedarikçiden gelen, Sovos/GİB ile ilgisi yok.

        v6.1: action_post() filtered → efatura olan hareketler e-fatura akışına,
        diğerleri doğrudan super().action_post()'a gönderilir.
        """
        # Alış defteri (purchase journal)
        purchase_journal = self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', self.company.id),
        ], limit=1)

        # move_type='in_invoice': alış faturası
        inv = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner_efatura.id,
            'invoice_date': '2026-06-01',
            'journal_id': purchase_journal.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Alış Kalemi',
                'quantity': 1,
                'price_unit': 500.0,
                'account_id': self.account_income.id,
            })],
        })

        # Mock YOK: Sovos çağrısı olmamalı, action_post() normal çalışmalı
        inv.action_post()

        self.assertEqual(inv.state, 'posted')
        # x_sovos_uuid boş olmalı → e-Fatura akışına girmedi
        self.assertFalse(inv.x_sovos_uuid,
            'Alış faturasında x_sovos_uuid boş olmalı')

    def test_no_double_post_on_mixed_selection(self):
        """
        v6.1 DÜZELTİLDİ: Karma seçimde (e-Fatura + diğer) çift post riski giderildi.

        Eski bug: e-Fatura hareketi hem e-Fatura akışında hem de super()'da
        post ediliyordu → muhasebe kaydı iki kez oluşuyordu.

        Test stratejisi:
            _efatura_post_single metodunu "sayan" bir wrapper ile değiştir.
            Karma seçimde çalıştır.
            Sayacın tam olarak 1 olduğunu doğrula.
        """
        efatura_inv = self._create_invoice(partner=self.partner_efatura)
        # Basit muhasebe fişi (e-Fatura değil)
        misc_move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.env['account.journal'].search([
                ('type', '=', 'general'),
                ('company_id', '=', self.company.id),
            ], limit=1).id,
        })
        combo = efatura_inv | misc_move

        # _efatura_post_single kaç kez çağrıldığını say
        post_call_count = {'efatura': 0}
        original_post = type(efatura_inv)._efatura_post_single

        def counting_post(self_inv):
            """Gerçek metodu çağır ama önce sayacı artır."""
            post_call_count['efatura'] += 1
            return original_post(self_inv)

        # patch.object: belirli bir instance/sınıfın metodunu değiştir
        # type(efatura_inv) → account.move sınıfı
        with patch.object(type(efatura_inv), '_efatura_post_single', counting_post), \
             self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            combo.action_post()

        self.assertEqual(post_call_count['efatura'], 1,
            'e-Fatura tam olarak bir kez post edilmeli (çift post yok)')
