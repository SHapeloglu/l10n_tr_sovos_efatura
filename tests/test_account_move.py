# -*- coding: utf-8 -*-
"""
Fatura Gönderimi & Toplu Gönderim Testleri — v6.1
===================================================
Test edilen kod: models/account_move.py
Test edilen metodlar:
  • _efatura_post_single()  → tek fatura gönderimi
  • action_send_efatura_bulk() → toplu (çoklu) fatura gönderimi
  • action_preview_efatura()   → XML önizleme (gönderim YOK)

Bu dosyadaki testler iki ana sınıfa ayrılmıştır:
  • TestEFaturaPost  → tek fatura senaryoları (10 test)
  • TestBulkSend    → toplu gönderim senaryoları (9 test)

v6.1 Değişiklikler:
  - action_send_efatura_bulk() artık state=POSTED + henüz gönderilmemiş filtresi
    (eski spec: sadece draft — yeni spec: POSTED ama x_efatura_status in ('draft', False))
  - 'validasyon' string arama kırılgan bug devam ediyor (dil değişirse bozulur)
  - e-Arşiv ayrı cron ile yönetiliyor

Risk Seviyesi: YÜKSEK — temel iş akışını kapsar
"""
import time
from datetime import date

# patch: belirli bir metodu/fonksiyonu sahte ile değiştirmek için
# MagicMock: her özelliğe/metoda otomatik cevap veren sahte nesne
from unittest.mock import patch, MagicMock

# UserError: kullanıcıya gösterilen, işlemi durduran Odoo hatası
# (teknik hata değil, iş kuralı ihlali — örn: "Bu müşteri e-Fatura sisteminde kayıtlı değil")
from odoo.exceptions import UserError

# Ortak test altyapısı — şirket, partnerler, mock metodları buradan gelir
from .common import SovosTestCommon


class TestEFaturaPost(SovosTestCommon):
    """
    Tek fatura gönderim testleri.

    Her test şu akışı doğrular:
        1. Taslak fatura oluştur
        2. action_post() çağır (mock'lar aktifken)
        3. Beklenen alanların doğru set edildiğini kontrol et

    action_post() içindeki adımlar (gerçek kodda):
        1. Ön koşul kontrolleri (VKN, numara serisi, tarih...)
        2. Numara rezervasyonu (_reserve_invoice_number)
        3. UBL XML üretimi (UblBuilder.build)
        4. XML validasyonu (UblValidator.validate)
        5. Sovos'a gönderim (InvoiceService.send_ubl veya ArchiveService.send_invoice)
        6. Odoo'da durumu güncelle (state=posted, x_efatura_status=sent...)
    """

    # ════════════════════════════════════════════════════════════════════
    # SENARYO YÖNLENDİRME TESTLERİ
    # Hangi müşteri tipi → hangi servis?
    # ════════════════════════════════════════════════════════════════════

    def test_efatura_partner_uses_invoice_service(self):
        """
        GİB kayıtlı müşteri (x_efatura_type='efatura') → InvoiceService kullanılmalı.

        İş kuralı: GİB e-Fatura sistemine kayıtlı şirketlere fatura gönderirken
        SovosInvoiceService.send_ubl() çağrılır. Bu servis faturayı GİB'e iletir
        ve karşı tarafın Sovos kutusuna düşer.
        """
        # Adım 1: GİB kayıtlı müşteriye taslak fatura oluştur
        inv = self._create_invoice(partner=self.partner_efatura)

        # Adım 2: with bloğu içindeki mock'lar aktifken action_post() çalıştır
        # _mock_sovos_invoice_success() → as mock_send ile yakalanıyor:
        # Bu sayede "send_ubl kaç kez çağrıldı?" sorusunu test edebiliriz
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success() as mock_send:
            inv.action_post()

        # Adım 3: Doğrulama
        # assert_called_once(): bu mock tam olarak 1 kez çağrılmış olmalı
        # 0 kez → send_ubl hiç çağrılmamış (hata)
        # 2+ kez → çift gönderim (hata)
        mock_send.assert_called_once()

        # Faturanın e-fatura tipinin partner'dan kopyalandığını kontrol et
        self.assertEqual(inv.x_efatura_type, 'efatura')

        # Gönderim başarılı → status 'sent' olmalı
        self.assertEqual(inv.x_efatura_status, 'sent')

        # Odoo muhasebe durumu: 'posted' = onaylandı, kayıtlara geçti
        self.assertEqual(inv.state, 'posted')

    def test_earsiv_partner_uses_archive_service(self):
        """
        GİB kayıtsız müşteri (x_efatura_type='earsiv') → ArchiveService kullanılmalı.

        İş kuralı: GİB'e kayıtsız bireyler/işletmeler için e-Arşiv kullanılır.
        SovosArchiveService.send_invoice() çağrılır, GİB'e DOĞRUDAN gitmez,
        Sovos'un arşivinde saklanır.
        """
        inv = self._create_invoice(partner=self.partner_earsiv)

        # NOT: InvoiceService değil ArchiveService mock'lanıyor
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_archive_success() as mock_send:
            inv.action_post()

        # ArchiveService'in tam olarak bir kez çağrıldığını doğrula
        mock_send.assert_called_once()
        self.assertEqual(inv.x_efatura_type, 'earsiv')
        self.assertEqual(inv.x_efatura_status, 'sent')

    def test_earsiv_ticarifatura_scenario_raises_user_error(self):
        """
        e-Arşiv alıcısına TICARIFATURA senaryosu seçilirse UserError fırlatılmalı.

        İş kuralı (Spec §1.2):
            TICARIFATURA sadece GİB'e KAYITLI şirketler arasında kullanılabilir.
            GİB kayıtsız bir alıcıya TICARIFATURA göndermek mümkün değil.
            Kullanıcı yanlış senaryo seçmişse, gönderimden ÖNCE hata ver.

        NEDEN mock YOK?
            action_post() senaryo kontrolü UBL üretiminden ÖNCE yapılır.
            Hata erken fırlatılır, UblBuilder veya Sovos'a hiç ulaşılmaz.
            Mock'lamak gereksiz ve yanıltıcı olur.
        """
        # e-Arşiv müşterisine yanlış senaryo ata
        self.partner_earsiv.x_default_scenario = 'TICARIFATURA'
        inv = self._create_invoice(partner=self.partner_earsiv)

        # assertRaises: içindeki kod UserError fırlatmalı, yoksa test başarısız
        with self.assertRaises(UserError) as cm:
            inv.action_post()

        # cm.exception: yakalanan hatanın kendisi
        # assertIn: hata mesajında bu string geçmeli (kullanıcıya anlamlı mesaj)
        self.assertIn('GİB e-Fatura sistemine kayıtlı değil', str(cm.exception))

    def test_earsiv_with_earsivfatura_scenario_succeeds(self):
        """
        e-Arşiv alıcısına EARSIVFATURA senaryosu → başarıyla gönderilmeli.

        Bir önceki testle beraber okuyun:
            TICARIFATURA + earsiv partner → HATA
            EARSIVFATURA + earsiv partner → BAŞARILI   ← bu test
        """
        self.partner_earsiv.x_default_scenario = 'EARSIVFATURA'
        inv = self._create_invoice(partner=self.partner_earsiv)

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_archive_success():
            inv.action_post()

        self.assertEqual(inv.x_efatura_status, 'sent')

    def test_ticarifatura_sets_response_fields(self):
        """
        TICARIFATURA gönderiminde ticari yanıt alanları set edilmeli.

        İş kuralı: TICARIFATURA'larda alıcı şirketin 8 gün içinde
        KABUL veya RED bildirmesi gerekir (e-Fatura mevzuatı).

        Beklenen:
            x_inv_response_status = 'beklemede'  (henüz cevap yok)
            x_inv_response_deadline = bugün + 8 gün
        """
        inv = self._create_invoice(partner=self.partner_efatura)
        # Senaryoyu açıkça TICARIFATURA olarak set et
        inv.x_efatura_scenario = 'TICARIFATURA'

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            inv.action_post()

        self.assertEqual(inv.x_inv_response_status, 'beklemede')

        # __import__('datetime') → test içinde import yapmadan timedelta kullan
        # Daha temiz yol: dosya başında timedelta import etmek (burada örnekleniyor)
        self.assertEqual(
            inv.x_inv_response_deadline,
            date.today() + __import__('datetime').timedelta(days=8)
        )

    def test_earsiv_does_not_set_response_deadline(self):
        """
        e-Arşiv gönderiminde 8 günlük yanıt süresi SET EDİLMEMELİ.

        e-Arşiv'de ticari kabul/red süreci yoktur.
        deadline alanı boş kalmalı (False).
        """
        inv = self._create_invoice(partner=self.partner_earsiv)
        self.partner_earsiv.x_default_scenario = 'EARSIVFATURA'

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_archive_success():
            inv.action_post()

        # assertFalse: değer False, None veya boş olmalı
        self.assertFalse(inv.x_inv_response_deadline)

    def test_unique_uuids_for_each_invoice(self):
        """
        Her fatura için benzersiz (farklı) UUID üretilmeli.

        UUID (Universally Unique Identifier): GİB'te her faturayı tanımlayan
        128-bit benzersiz kimlik. İki fatura aynı UUID'ye sahip olursa GİB reddeder.

        Bu test: 2 farklı fatura → 2 farklı UUID olduğunu doğrular.
        """
        inv1 = self._create_invoice()
        inv2 = self._create_invoice()

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            inv1.action_post()
            inv2.action_post()

        # assertNotEqual: iki değer FARKLI olmalı
        self.assertNotEqual(inv1.x_sovos_uuid, inv2.x_sovos_uuid)

        # assertTrue: değer truthy olmalı (boş string, None, False değil)
        self.assertTrue(inv1.x_sovos_uuid)
        self.assertTrue(inv2.x_sovos_uuid)

    def test_efatura_status_is_sending_during_send(self):
        """
        Sovos'a gönderim SIRASINDA x_efatura_status='sending' olmalı.

        UX (kullanıcı deneyimi) testi:
            Uzun süren bir gönderimde kullanıcı faturaya bakıyorsa
            'Gönderiliyor...' yazısını görmeli, 'Gönderildi' değil.
            Bu test o anlık durumu yakalar.

        Teknik:
            side_effect ile send_ubl() çağrıldığında bir fonksiyon çalıştırıyoruz.
            O fonksiyon çalışırken (yani "Sovos çağrısı sırasında") status'u kaydediyoruz.
        """
        inv = self._create_invoice()
        # Gönderim sırasındaki status değerlerini biriktireceğimiz liste
        status_during_send = []

        def capture_status(*args, **kwargs):
            """
            Bu fonksiyon send_ubl() yerine çalışır.
            Çalıştığı an faturanın status'unu kaydeder.
            """
            # inv.x_efatura_status: bu an (gönderim sırasında) ne?
            status_during_send.append(inv.x_efatura_status)
            # Gerçek send_ubl gibi envelope_uuid döndür
            return 'mock-envelope-uuid'

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             patch(
                 'l10n_tr_sovos_efatura.services.sovos_invoice_service'
                 '.SovosInvoiceService.send_ubl',
                 side_effect=capture_status,   # return_value değil side_effect!
             ):
            inv.action_post()

        # capture_status çalışırken status 'sending' olmalıydı
        self.assertEqual(status_during_send[0], 'sending')

    # ════════════════════════════════════════════════════════════════════
    # ÖNİZLEME TESTLERİ
    # action_preview_efatura(): XML oluşturur ama Sovos'a GÖNDERMEZ
    # ════════════════════════════════════════════════════════════════════

    def test_preview_returns_act_url(self):
        """
        Önizleme ir.actions.act_url tipinde action dönmeli.

        ir.actions.act_url: Odoo'nun "URL aç" action tipi.
        Önizleme XML içeriğini tarayıcıda açmak için kullanılır.
        """
        inv = self._create_invoice()
        # Önizleme için fatura posted olmalı ve numarası olmalı
        inv.write({'state': 'posted', 'name': 'TST2026000000001'})

        with self._mock_ubl_builder(), self._mock_validator_valid():
            result = inv.action_preview_efatura()

        # result: Odoo action dictionary'si
        self.assertEqual(result['type'], 'ir.actions.act_url')

    def test_preview_shows_validation_error_in_html(self):
        """
        Validasyon hatası varsa önizleme URL'inde hata bilgisi olmalı.

        Kullanıcı "Önizle" dediğinde XML geçersizse, beyaz ekran değil
        hata mesajı görmeli.
        """
        inv = self._create_invoice()
        inv.write({'state': 'posted', 'name': 'TST2026000000001'})

        # XSD hatası döndüren mock ile önizle
        with self._mock_ubl_builder(), \
             self._mock_validator_xsd_fail(['Test XSD hatası']):
            result = inv.action_preview_efatura()

        # URL'de hata bilgisi encode edilmiş olmalı
        self.assertIn('Validasyon Hatası', result['url'])
        self.assertIn('XSD', result['url'])

    def test_preview_does_not_send_to_sovos(self):
        """
        Önizleme Sovos'a gönderim YAPMAMALIIDIR.

        KRİTİK: Kullanıcı sadece "nasıl görünecek" diye bakıyor.
        Önizleme sırasında gerçek gönderim olursa fatura mükerrer gönderilir.

        Teknik doğrulama: mock_send.assert_not_called() → send_ubl hiç çağrılmadı
        """
        inv = self._create_invoice()
        inv.write({'state': 'posted', 'name': 'TST2026000000001'})

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success() as mock_send:
            inv.action_preview_efatura()

        # assert_not_called(): bu mock HİÇ çağrılmamalı
        mock_send.assert_not_called()


class TestBulkSend(SovosTestCommon):
    """
    Toplu fatura gönderim testleri.

    action_send_efatura_bulk(): birden fazla faturayı tek seferde gönderir.
    Tek faturadan farkları:
      • Zaten gönderilmiş faturaları atlar
      • Bir hata diğerlerini durdurmaz (iş sürekliliği)
      • Rate limiting için gönderimler arasında 500ms bekler
      • Faturalar VKN'e göre sıralanır (Sovos cache optimizasyonu)
    """

    # ════════════════════════════════════════════════════════════════════
    # BAŞARILI TOPLU GÖNDERİM
    # ════════════════════════════════════════════════════════════════════

    def test_bulk_sends_all_draft_invoices(self):
        """
        3 taslak fatura → 3'ü de başarıyla gönderilmeli.

        Temel "mutlu yol" testi.
        """
        # 3 ayrı fatura oluştur
        # self.env['account.move'] → boş recordset
        # |= operatörü: recordset'lere birleştirme (SQL UNION gibi)
        invs = self.env['account.move']
        for _ in range(3):
            invs |= self._create_invoice(partner=self.partner_efatura)

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            result = invs.action_send_efatura_bulk()

        # result['params']['message']: kullanıcıya gösterilen özet mesaj
        # "3 fatura gönderildi" gibi bir şey içermeli
        self.assertIn('3', result['params']['message'])

        # Her fatura 'sent' durumuna geçmiş olmalı
        for inv in invs:
            self.assertEqual(inv.x_efatura_status, 'sent')

    def test_bulk_sorted_by_partner_vkn(self):
        """
        Faturalar alıcı VKN'e göre SIRALANARAK işlenmeli.

        Neden önemli?
            Sovos aynı alıcıya art arda gelen faturaları daha hızlı işler
            (session/cache avantajı). Karışık sırada göndermek performansı düşürür.

        Test stratejisi:
            Kasıtlı olarak ters sırada fatura oluştur (B, A).
            Gönderim sırasında işlenen VKN'leri kaydet.
            Son sıralamanın sorted() ile aynı olduğunu doğrula.
        """
        partner_a = self.env['res.partner'].create({
            'name': 'A Şirketi', 'vat': '1111111111',
            'x_efatura_type': 'efatura',
            'x_efatura_type_updated': date.today(),
        })
        partner_b = self.env['res.partner'].create({
            'name': 'B Şirketi', 'vat': '2222222222',
            'x_efatura_type': 'efatura',
            'x_efatura_type_updated': date.today(),
        })

        # Kasıtlı TERS sıra: B sonra A
        inv_b = self._create_invoice(partner=partner_b)
        inv_a = self._create_invoice(partner=partner_a)
        selection = inv_b | inv_a

        # Gönderim sırasını takip etmek için liste
        processed = []

        def track_order(xml_bytes, uuid, partner, scenario):
            """send_ubl() yerine çalışır, partner VKN'ini kaydeder."""
            processed.append(partner.vat)
            return 'mock-uuid'

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             patch(
                 'l10n_tr_sovos_efatura.services.sovos_invoice_service'
                 '.SovosInvoiceService.send_ubl',
                 side_effect=track_order,
             ):
            selection.action_send_efatura_bulk()

        # processed: ['1111111111', '2222222222'] olmalı (A önce, B sonra)
        # sorted(processed): zaten sıralı liste
        # assertEqual ile karşılaştır → sıralama doğruysa eşit
        self.assertEqual(processed, sorted(processed),
            "Faturalar VKN'e göre sıralı işlenmeli")

    def test_bulk_rate_limit_sleep_called(self):
        """
        Her gönderimden sonra 500ms bekleme (time.sleep(0.5)) çağrılmalı.

        Rate limiting nedir?
            Sovos API'si saniyede çok fazla istek gelirse HTTP 429 (Too Many Requests)
            döndürür. Bunu önlemek için her gönderimden sonra 0.5 saniye beklenir.

        time.sleep mock'lanıyor çünkü:
            Gerçekten beklesek test çok yavaşlar.
            "sleep çağrıldı mı?" sorusunu cevaplamak yeterli.
        """
        inv = self._create_invoice()

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success(), \
             patch('l10n_tr_sovos_efatura.models.account_move.time.sleep') as mock_sleep:
            inv.action_send_efatura_bulk()

        # assert_called_with(0.5): tam olarak 0.5 argümanı ile çağrılmalı
        mock_sleep.assert_called_with(0.5)

    # ════════════════════════════════════════════════════════════════════
    # FİLTRELEME: Hangi faturalar gönderilir, hangileri atlanır?
    # ════════════════════════════════════════════════════════════════════

    def test_bulk_skips_already_sent_invoices(self):
        """
        Zaten gönderilmiş faturalar (x_efatura_status='sent') ATLANMALI.

        Senaryo: Kullanıcı listeden hem taslak hem de gönderilmiş fatura seçip
        "Toplu Gönder" dedi. Sadece taslak olanlar gönderilmeli.
        """
        draft_inv = self._create_invoice()
        # _create_sent_invoice(): zaten gönderilmiş durumda fatura üretir
        sent_inv = self._create_sent_invoice()

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            # İki faturayı birlikte seç (| operatörü ile birleştir)
            result = (draft_inv | sent_inv).action_send_efatura_bulk()

        # sent_inv'in durumu değişmemeli — hâlâ 'sent'
        self.assertEqual(sent_inv.x_efatura_status, 'sent')
        # Mesajda sadece "1 fatura gönderildi" yazmalı (2 değil)
        self.assertIn('1', result['params']['message'])

    def test_bulk_empty_selection_raises_user_error(self):
        """
        Gönderilebilir fatura yoksa kullanıcıya anlamlı hata mesajı verilmeli.

        Senaryo: Kullanıcı sadece zaten gönderilmiş faturalar seçti.
        Gönderilebilecek hiçbir şey yok → UserError.
        """
        sent_inv = self._create_sent_invoice()
        with self.assertRaises(UserError) as cm:
            sent_inv.action_send_efatura_bulk()
        # Hata mesajında 'taslak' geçmeli → kullanıcı ne yapması gerektiğini anlar
        self.assertIn('taslak', str(cm.exception).lower())

    # ════════════════════════════════════════════════════════════════════
    # KISMİ HATA SENARYOLARI
    # İş sürekliliği: 1 fatura başarısız olsa diğerleri devam etmeli
    # ════════════════════════════════════════════════════════════════════

    def test_bulk_partial_failure_others_continue(self):
        """
        3 faturadan 1'i Sovos'a gönderilirken hata verirse diğer 2'si devam etmeli.

        KRİTİK iş kuralı:
            Tek bir fatura başarısız oldu diye tüm toplu gönderim durmamalı.
            Başarısız olan işaretlenir, diğerleri devam eder.

        Test stratejisi:
            2. çağrıda hata fırlatan bir fonksiyon yaz.
            Sonuçta hem "2 başarılı" hem "1 hata" mesajı olmalı.
        """
        invs = [self._create_invoice() for _ in range(3)]
        # | ile 3 faturayı birleştir
        bulk = invs[0] | invs[1] | invs[2]

        # Çağrı sayacı: closure (iç fonksiyon) için dict kullanıyoruz
        # Not: Python'da iç fonksiyondan dış değişkene atama yapılamaz,
        # ama dict'in içindeki değeri değiştirebiliriz
        call_count = {'n': 0}

        def alternate_fail(*args, **kwargs):
            """1. ve 3. çağrı başarılı, 2. çağrı hata fırlatır."""
            call_count['n'] += 1
            if call_count['n'] == 2:
                raise Exception('Sovos geçici hata')
            return 'mock-envelope-uuid'

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             patch(
                 'l10n_tr_sovos_efatura.services.sovos_invoice_service'
                 '.SovosInvoiceService.send_ubl',
                 side_effect=alternate_fail,
             ):
            result = bulk.action_send_efatura_bulk()

        msg = result['params']['message']
        # Mesajda hem 2 (başarılı) hem 1 (hatalı) sayısı olmalı
        self.assertIn('2', msg)
        self.assertIn('1', msg)
        # Kısmi hata olduğunda bildirim tipi 'warning' olmalı (success değil)
        self.assertEqual(result['params']['type'], 'warning')

    def test_bulk_validation_error_counted_separately(self):
        """
        Validasyon hatası (XSD/Schematron) ayrı kategoride sayılmalı.

        BİLİNEN HATA (BUG) belgeleme testi:
            Mevcut kod 'validasyon' string'ini arar hata mesajında.
            Eğer Odoo dili Türkçe değilse bu string değişir ve test kırılır.
            Bu test bu kırılgan mantığı belgeler — düzeltilene kadar çalışır.
        """
        inv = self._create_invoice()
        # Sovos'a gönderilmeden validasyon aşamasında hata alır
        with self._mock_ubl_builder(), \
             self._mock_validator_xsd_fail():
            result = inv.action_send_efatura_bulk()

        msg = result['params']['message']
        # 'Validasyon' Türkçe'de çalışır; dil değişirse bozulur → bilinen bug
        self.assertIn('Validasyon', msg,
            'BUG: "validasyon" string arama dil bağımlı — dil değişirse kırılır')

    def test_bulk_success_notification_type_is_success(self):
        """
        Tüm faturalar başarıyla gönderilirse bildirim tipi 'success' olmalı.

        Odoo notification types: 'success' (yeşil), 'warning' (sarı), 'danger' (kırmızı)
        Kısmi hata yoksa kullanıcıya yeşil başarı bildirimi göster.
        """
        inv = self._create_invoice()
        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            result = inv.action_send_efatura_bulk()

        self.assertEqual(result['params']['type'], 'success')
