# -*- coding: utf-8 -*-
"""
GİB Durum Kodu İşleme Testleri — v6.1
=======================================
Test edilen kod: models/account_move.py
Test edilen metod: _process_gib_status(status_code)

GİB DURUM KODU NEDİR?
----------------------
Fatura Sovos üzerinden GİB'e gönderildikten sonra GİB bir durum kodu döndürür.
Bu kodu periyodik olarak sorgularız (cron ile). Kod faturanın ne aşamada
olduğunu gösterir.

Önemli kod grupları:
    1000, 1100         → Bekleme (kuyrukta, işleniyor) — durum değişmez
    1101, 1103, 1150,
    1160, 1210         → Teknik hata — aynı UUID ile tekrar gönderilebilir
    1104, 1163, 1215   → Kritik hata — iptal + yeni fatura VEYA admin bildirimi
    1161, 1171         → Sovos imza/sistem hatası — Sovos destek gerekir
    1300               → BAŞARILI (GİB kabul etti)
    1305               → Alıcı kabul etti
    1310               → Alıcı reddetti

v6.1 Değişiklikler:
  - GIB_SUCCESS = {1300}, GIB_ACCEPTED_BY_RECEIVER = {1305} AYRI setler
  - GIB_RETRY_SAME_UUID ↔ RETRY_SAME_UUID eşleşmesi teyit edildi
  - 1215 → hâlâ _set_error() → cron kilitlenmesi bug DEVAM EDİYOR

Risk Seviyesi: KRİTİK — yanlış durum işleme = muhasebe hatası
"""
from datetime import date, timedelta
from unittest.mock import patch, call

from .common import SovosTestCommon


class TestGibStatusCodes(SovosTestCommon):
    """
    _process_gib_status(code) metodunun tüm kod senaryolarını test eder.

    setUp'ta self.inv oluşturuluyor — her testte "zaten gönderilmiş" fatura var.
    _create_sent_invoice(): x_efatura_status='sent', x_number_status='confirmed'
    """

    def setUp(self):
        """
        Her testten önce gönderilmiş bir fatura hazırla.
        Durum kodu testleri "gönderildikten sonra GİB ne dedi?" senaryosunu test eder.
        """
        # Önce parent setUp'ı çağır (şirket, partnerler vb. kurulumu)
        super().setUp()
        # Her test için taze bir "gönderilmiş" fatura oluştur
        self.inv = self._create_sent_invoice()

    # ════════════════════════════════════════════════════════════════════
    # BAŞARI KODLARI (1300, 1305)
    # ════════════════════════════════════════════════════════════════════

    def test_1300_sets_accepted_clears_error(self):
        """
        1300 (GİB Kabul) → x_efatura_status='accepted', önceki hata mesajı silinmeli.

        v6.1 ÖNEMLİ: GIB_SUCCESS = {1300} — 1305 bu sette artık YOK.
        (Eski versiyonda ikisi aynı setteydi, şimdi ayrıldı.)

        Hata mesajının temizlenmesi: Önceki bir girişimde hata oluşmuş
        ve x_efatura_error_msg dolmuş olabilir. 1300 gelince temizle.
        """
        # Önceden hata mesajı varmış gibi simüle et
        self.inv.write({'x_efatura_error_msg': 'önceki hata'})

        # Durum kodu işle — Sovos cron'u bunu çağırır
        self.inv._process_gib_status(1300)

        self.assertEqual(self.inv.x_efatura_status, 'accepted')
        # assertFalse: hata mesajı temizlenmiş olmalı (boş string veya False)
        self.assertFalse(self.inv.x_efatura_error_msg)
        # GİB kodunun kaydedildiğini kontrol et (audit trail)
        self.assertEqual(self.inv.x_gib_status_code, 1300)

    def test_1300_accepted_cannot_be_resent(self):
        """
        1300 alınan fatura tekrar GÖNDERİLEMEZ.

        GİB faturayı kabul etti = kesinleşti. Aynı faturayı tekrar göndermek
        mükerrer fatura oluşturur. Wizard bunu engellemelidir.
        """
        from odoo.exceptions import UserError
        self.inv._process_gib_status(1300)
        self.assertEqual(self.inv.x_efatura_status, 'accepted')

        # Tekrar gönderim wizard'ı oluşturulursa UserError fırlatılmalı
        with self.assertRaises(UserError) as cm:
            wizard = self.env['sovos.resend.invoice.wizard'].create({
                'invoice_id': self.inv.id,
                'resend_type': 'same_uuid',
            })
            wizard.action_resend()
        self.assertIn('hatalı', str(cm.exception).lower())

    def test_1305_sets_accepted_and_kabul(self):
        """
        1305 (Alıcı Kabul) → accepted + x_inv_response_status='kabul'.

        v6.1: 1305 artık GIB_ACCEPTED_BY_RECEIVER setinde (GIB_SUCCESS'te değil).
        Fark: 1300 = GİB sistemi kabul etti, 1305 = alıcı şirket kabul etti.
        Her ikisi de 'accepted' yapar ama 1305 ek olarak 'kabul' atar.
        """
        self.inv._process_gib_status(1305)

        self.assertEqual(self.inv.x_efatura_status, 'accepted')
        # x_inv_response_status: alıcı şirketin yanıtı ('kabul' veya 'red')
        self.assertEqual(self.inv.x_inv_response_status, 'kabul')
        self.assertFalse(self.inv.x_efatura_error_msg)
        self.assertEqual(self.inv.x_gib_status_code, 1305)

    def test_1305_is_not_in_gib_success_set(self):
        """
        v6.1 DÜZELTİLMESİ: 1305'in GIB_SUCCESS'ten ayrıldığını doğrular.

        Bu "sentinel test" — eğer biri yanlışlıkla 1305'i GIB_SUCCESS'e
        geri eklerse bu test kırılır ve fark edilir.

        Doğrudan model modülünden set'leri import ediyoruz:
        Bu sayede kod değişikliği anında test devreye girer.
        """
        # Modülden direkt import et (sabitleri test ediyoruz)
        from l10n_tr_sovos_efatura.models.account_move import GIB_SUCCESS, GIB_ACCEPTED_BY_RECEIVER

        self.assertNotIn(1305, GIB_SUCCESS,
            '1305 GIB_SUCCESS içinde olmamalı (v6.1 düzeltmesi)')
        self.assertIn(1305, GIB_ACCEPTED_BY_RECEIVER)

    def test_1310_sets_rejected(self):
        """
        1310 (Alıcı Red) → rejected + x_inv_response_status='red' + hata mesajı.

        Alıcı şirket faturayı reddetti. Bu durumda:
            - Fatura 'rejected' durumuna geçer
            - x_inv_response_status='red' (alıcı yanıtı)
            - x_efatura_error_msg: red gerekçesi kaydedilir
        """
        self.inv._process_gib_status(1310)

        self.assertEqual(self.inv.x_efatura_status, 'rejected')
        self.assertEqual(self.inv.x_inv_response_status, 'red')
        # Hata mesajı dolu olmalı (red gerekçesi)
        self.assertTrue(self.inv.x_efatura_error_msg)
        self.assertEqual(self.inv.x_gib_status_code, 1310)

    # ════════════════════════════════════════════════════════════════════
    # TEKNİK HATA KODLARI (aynı UUID ile tekrar gönderilebilir)
    # ════════════════════════════════════════════════════════════════════

    def test_1101_sets_error(self):
        """1101 → Teknik hata. x_efatura_status='error' olmalı."""
        self.inv._process_gib_status(1101)
        self.assertEqual(self.inv.x_efatura_status, 'error')
        # Hata mesajı kaydedilmeli (kullanıcı bilgilendirilmeli)
        self.assertTrue(self.inv.x_efatura_error_msg)

    def test_1103_sets_error(self):
        """1103 → GİB imza doğrulama hatası. Tekrar gönderilebilir (aynı UUID)."""
        self.inv._process_gib_status(1103)
        self.assertEqual(self.inv.x_efatura_status, 'error')

    def test_1150_sets_error_schematron(self):
        """1150 → GİB tarafında Schematron hatası."""
        self.inv._process_gib_status(1150)
        self.assertEqual(self.inv.x_efatura_status, 'error')

    def test_1160_sets_error_xsd(self):
        """1160 → GİB tarafında XSD validasyon hatası."""
        self.inv._process_gib_status(1160)
        self.assertEqual(self.inv.x_efatura_status, 'error')

    def test_1210_sets_error_receiver_unreachable(self):
        """
        1210 → Alıcı e-Fatura sistemine ulaşılamadı.

        Bu durumda iptal gerekmez, aynı fatura tekrar gönderilebilir.
        Hata mesajında 'iptal gerekmez' geçmeli → kullanıcı ne yapacağını bilir.
        """
        self.inv._process_gib_status(1210)
        self.assertEqual(self.inv.x_efatura_status, 'error')
        self.assertIn('iptal gerekmez', self.inv.x_efatura_error_msg)

    # ════════════════════════════════════════════════════════════════════
    # KRİTİK HATALAR (admin bildirimi gerektirenler)
    # Bu kodlarda _notify_admin_gib_error() çağrılmalı
    # ════════════════════════════════════════════════════════════════════

    def test_1104_sets_error_and_notifies_admin(self):
        """
        1104 → Fatura iptal edilip yeni kesilmeli + admin bilgilendirilmeli.

        1104: Çeşitli teknik hatalar (XML hatası, imza sorunu vb.)
        Bu durumda aynı UUID ile tekrar gönderim OLMAZ — iptal + yeni fatura.

        patch.object() kullanımı:
            Belirli bir instance'ın metodunu mock'lar.
            self.inv._notify_admin_gib_error → bu NESNEYE özgü mock.
            (patch() modül seviyesinde, patch.object() instance/sınıf seviyesinde)
        """
        # patch.object: self.inv'in _notify_admin_gib_error metodunu izle
        with patch.object(self.inv, '_notify_admin_gib_error') as mock_notify:
            self.inv._process_gib_status(1104)
            # Bildirim tam olarak 1 kez çağrılmalı
            mock_notify.assert_called_once()
            # İlk positional argüman 1104 olmalı (hangi kod için bildirim yapıldı)
            args = mock_notify.call_args[0]
            self.assertEqual(args[0], 1104)

        self.assertEqual(self.inv.x_efatura_status, 'error')
        self.assertTrue(self.inv.x_efatura_error_msg)

    def test_1163_sets_error_and_notifies_admin(self):
        """
        1163 → Mükerrer UUID (aynı UUID daha önce gönderilmiş).

        Bu ciddi bir hatadır — UUID generator'da sorun var demek.
        Admin bilgilendirilmeli, manuel inceleme gerekebilir.
        """
        with patch.object(self.inv, '_notify_admin_gib_error') as mock_notify:
            self.inv._process_gib_status(1163)
            mock_notify.assert_called_once()
        self.assertEqual(self.inv.x_efatura_status, 'error')

    # ════════════════════════════════════════════════════════════════════
    # SOVOS DESTEK GEREKTIREN HATALAR
    # ════════════════════════════════════════════════════════════════════

    def test_1161_sets_error_sovos_support(self):
        """
        1161 → İmza hatası. Çözüm için Sovos teknik desteği gerekir.

        Hata mesajında 'Sovos' geçmeli → kullanıcı kime başvuracağını bilir.
        """
        self.inv._process_gib_status(1161)
        self.assertEqual(self.inv.x_efatura_status, 'error')
        self.assertIn('Sovos', self.inv.x_efatura_error_msg)

    def test_1171_sets_error_sovos_support(self):
        """1171 → Başka bir Sovos tarafındaki sistem hatası."""
        self.inv._process_gib_status(1171)
        self.assertEqual(self.inv.x_efatura_status, 'error')

    # ════════════════════════════════════════════════════════════════════
    # BEKLEME KODLARI (durum değişmemeli)
    # Cron bir sonraki döngüde tekrar sorgular
    # ════════════════════════════════════════════════════════════════════

    def test_1000_no_status_change(self):
        """
        1000 → Fatura GİB kuyruğunda, henüz işlenmedi. Durum değişmemeli.

        Cron mantığı:
            1000 geldi → "henüz işlenmedi, bekle" → durum aynı kalsın
            Bir sonraki cron çalışmasında tekrar sorgu atılır.
        """
        original = self.inv.x_efatura_status   # 'sent'
        self.inv._process_gib_status(1000)
        # Durum değişmemeli
        self.assertEqual(self.inv.x_efatura_status, original)

    def test_1100_no_status_change(self):
        """1100 → GİB işliyor, bekle. Durum değişmemeli."""
        original = self.inv.x_efatura_status
        self.inv._process_gib_status(1100)
        self.assertEqual(self.inv.x_efatura_status, original)

    # ════════════════════════════════════════════════════════════════════
    # BİLİNEN BUG: 1215 SONRASI CRON KİLİTLENMESİ
    # ════════════════════════════════════════════════════════════════════

    def test_1215_sets_error_and_notifies_admin(self):
        """
        1215 → 4 başarısız deneme + admin bildirim.

        BİLİNEN BUG belgeleme testi:
            1215 gelince _set_error() çağrılıyor → x_efatura_status='error'
            Cron sadece 'sent'/'sending' durumlarını sorguluyor.
            Bu fatura artık 'error' → cron onu bir daha BULAMAZ → KILITLENDI.

            Bu test mevcut yanlış davranışı belgeler.
            Düzeltme sonrası TODO yorumları aktive edilmeli.
        """
        with patch.object(self.inv, '_notify_admin_gib_error') as mock_notify:
            self.inv._process_gib_status(1215)
            mock_notify.assert_called_once()

        self.assertEqual(self.inv.x_efatura_status, 'error',
            '1215 sonrası status=error → cron bir daha bulamaz (bilinen bug)')
        # TODO: Düzeltme sonrası bu satırları aktive et:
        # self.assertIn(self.inv.x_efatura_status, ('sent', 'sending'))
        # veya self.assertTrue(self.inv.x_gib_pending_retry)

    # ════════════════════════════════════════════════════════════════════
    # KRİTİK: İKİ SET SENKRONİZASYONU
    # ════════════════════════════════════════════════════════════════════

    def test_retry_sets_are_identical(self):
        """
        GIB_RETRY_SAME_UUID (account_move.py) ile RETRY_SAME_UUID (resend_wizard.py)
        TAMAMEN AYNI olmalı.

        Neden iki ayrı set var?
            account_move.py: "bu kod gelince hata ver, tekrar gönderilebilir"
            resend_wizard.py: "bu hata kodundaki fatura için aynı UUID ile gönder"

        Risk: Biri güncellenip diğeri unutulursa:
            account_move.py 1105 → error koyuyor
            resend_wizard.py 1105'i bilmiyor → wizard "yeni fatura" diyor
            → Kullanıcı gereksiz yere yeni fatura keser

        symmetric_difference(): A'da olup B'de olmayan VEYA B'de olup A'da olmayan elemanlar.
        Boş set dönmesi = tamamen aynılar.
        """
        from l10n_tr_sovos_efatura.models.account_move import GIB_RETRY_SAME_UUID
        from l10n_tr_sovos_efatura.wizards.resend_invoice_wizard import RETRY_SAME_UUID

        diff = GIB_RETRY_SAME_UUID.symmetric_difference(RETRY_SAME_UUID)
        self.assertEqual(diff, set(),
            'Set farkı bulundu: %s\n'
            'account_move.py: %s\n'
            'resend_wizard.py: %s' % (diff, GIB_RETRY_SAME_UUID, RETRY_SAME_UUID))

    # ════════════════════════════════════════════════════════════════════
    # 8 GÜNLÜK UYARI HESAPLAMA
    # TICARIFATURA'da alıcının yanıt verme süresi
    # ════════════════════════════════════════════════════════════════════

    def test_ticarifatura_deadline_set_to_8_days(self):
        """
        TICARIFATURA gönderiminde yanıt süresi bugün + 8 gün olarak set edilmeli.

        self.inv = _create_sent_invoice(scenario='TICARIFATURA') → setUp'ta oluşturuldu.
        _create_sent_invoice() otomatik olarak deadline atar.
        Bu test o değerin doğru hesaplandığını kontrol eder.
        """
        self.assertEqual(
            self.inv.x_inv_response_deadline,
            date.today() + timedelta(days=8)
        )

    def test_show_8day_warning_when_deadline_today(self):
        """
        Son gün bugünse uyarı gösterilmeli (x_show_8day_warning=True).

        x_show_8day_warning: computed field — deadline <= bugün+1 ise True döner.
        Kullanıcı arayüzünde sarı uyarı bandı göstermek için kullanılır.
        """
        self.inv.x_inv_response_deadline = date.today()
        self.assertTrue(self.inv.x_show_8day_warning)

    def test_show_8day_warning_when_deadline_tomorrow(self):
        """Son gün yarınsa uyarı gösterilmeli — kullanıcıya 1 günü var."""
        self.inv.x_inv_response_deadline = date.today() + timedelta(days=1)
        self.assertTrue(self.inv.x_show_8day_warning)

    def test_no_8day_warning_when_deadline_in_5_days(self):
        """5 gün kalmışsa uyarı yok — erken uyarı göstermek gereksiz."""
        self.inv.x_inv_response_deadline = date.today() + timedelta(days=5)
        self.assertFalse(self.inv.x_show_8day_warning)

    def test_no_8day_warning_when_kabul(self):
        """
        Alıcı zaten KABUL bildirdiyse uyarı gösterilmemeli.

        Kabul geldikten sonra deadline uyarısı anlamsız — işlem tamamlandı.
        """
        self.inv.write({
            'x_inv_response_deadline': date.today(),
            'x_inv_response_status': 'kabul',   # alıcı kabul etti
        })
        self.assertFalse(self.inv.x_show_8day_warning)

    # ════════════════════════════════════════════════════════════════════
    # TİP GÜVENLİĞİ
    # _process_gib_status() farklı veri tiplerine karşı dayanıklı olmalı
    # ════════════════════════════════════════════════════════════════════

    def test_string_status_code_accepted(self):
        """
        '1300' (string) → int'e dönüştürülüp işlenmeli.

        SOAP API'lerden gelen veriler bazen string olabilir.
        int('1300') → 1300 dönüşümü yapılmalı, crash olmamalı.
        """
        # String olarak ver — int değil
        self.inv._process_gib_status('1300')
        # Yine de doğru işlenmeli
        self.assertEqual(self.inv.x_efatura_status, 'accepted')

    def test_none_status_code_no_crash(self):
        """
        None değeri → crash olmamalı, durum değişmemeli.

        Savunmacı programlama: API bazen None dönebilir.
        Kod None'ı → 0 → bilinmeyen kod → işlem yapma şeklinde ele almalı.
        """
        original = self.inv.x_efatura_status
        self.inv._process_gib_status(None)
        # Durum değişmemeli
        self.assertEqual(self.inv.x_efatura_status, original)

    def test_unknown_code_does_not_crash(self):
        """
        Bilinmeyen kod (9999 gibi) sessizce geçmeli — exception fırlatmamalı.

        GİB gelecekte yeni kodlar ekleyebilir. Eski kod versiyonumuz o kodu
        bilmeyebilir. Crash yerine "bilmiyorum, kaydet geç" mantığı.
        """
        original = self.inv.x_efatura_status
        self.inv._process_gib_status(9999)
        # GİB kodu yine de kaydedilmeli (audit trail için)
        self.assertEqual(self.inv.x_gib_status_code, 9999)

    # ════════════════════════════════════════════════════════════════════
    # HATA MESAJI DİL DESTEĞİ
    # ════════════════════════════════════════════════════════════════════

    def test_gib_msg_returns_localized_string(self):
        """
        v6.1: _gib_msg() lazy dict kullanır — her çağrıda aktif dil context'ine göre çeviri.

        _gib_msg(1300) → "GİB tarafından kabul edildi" (Türkçe)
        _gib_msg(1300) → "Accepted by GIB" (İngilizce — farklı context'te)

        Bu test her bilinen kod için boş olmayan mesaj döndüğünü doğrular.
        """
        from l10n_tr_sovos_efatura.models.account_move import _gib_msg
        # Bilinen tüm kritik kodlar için mesaj var mı?
        for code in [1101, 1103, 1104, 1150, 1160, 1215, 1300, 1305, 1310]:
            msg = _gib_msg(code)
            # assertTrue: mesaj dolu olmalı (boş string veya None değil)
            self.assertTrue(msg, '_gib_msg(%d) boş string döndürdü' % code)
