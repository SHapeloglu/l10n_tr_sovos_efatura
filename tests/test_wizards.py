# -*- coding: utf-8 -*-
"""
İptal ve Yeniden Gönderim Wizard Testleri — v6.1
=================================================
Test edilen kodlar:
  wizards/cancel_invoice_wizard.py   → e-Fatura/e-Arşiv iptal
  wizards/resend_invoice_wizard.py   → hata sonrası tekrar gönderim

WİZARD NEDİR?
-------------
Odoo'da "wizard", kullanıcıdan ek bilgi alarak belirli bir işlemi
gerçekleştiren geçici formlardır. Kullanıcı butona tıklar → wizard açılır
→ onaylar/seçim yapar → iş mantığı çalışır.

İPTAL AKIŞLARI (3 farklı senaryo):
    1. e-Arşiv İptal
       → SovosArchiveService.cancel_invoice() API çağrısı
       → x_efatura_status = 'cancelled'

    2. TEMELFATURA İptal (e-Fatura, tek taraflı)
       → Kullanıcı onay checkbox'u işaretlemeli
       → Karşı tarafa Odoo'dan iptal e-postası gönderilir

    3. TİCARİFATURA İptal (e-Fatura, karşılıklı onay)
       → 8 gün geçtiyse BLOKE (GİB portal üzerinden iptal gerekir)
       → 8 gün geçmediyse TEMELFATURA gibi işlenir

YENİDEN GÖNDERİM AKIŞLARI:
    same_uuid  → Aynı UUID ile tekrar gönder (1101, 1103, 1150, 1160, 1210)
    new_uuid   → Yeni UUID üret (1104, 1163)

v6.1 Değişiklikler:
  - cancel_wizard: TICARIFATURA 8 gün kontrolü deadline field'a taşındı
  - resend_wizard: action_resend() sonrası accepted faturada UserError
  - RETRY_SAME_UUID seti resend_wizard.py'a taşındı
"""
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from odoo.exceptions import UserError

from .common import SovosTestCommon


class TestCancelWizard(SovosTestCommon):
    """
    İptal wizard testleri.
    Her testte gönderilmiş fatura oluşturulur ve iptal senaryosu test edilir.
    """

    # ════════════════════════════════════════════════════════════════════
    # E-ARŞİV İPTAL
    # ════════════════════════════════════════════════════════════════════

    def test_earsiv_cancel_calls_api_and_sets_cancelled(self):
        """
        e-Arşiv iptali → ArchiveService.cancel_invoice() API çağrısı yapılmalı
        ve x_efatura_status='cancelled' olmalı.

        e-Arşiv iptali için GİB onayı gerekmez — Sovos API'sine direkt çağrı yeterli.
        (e-Fatura iptalinden farklı: karşı taraf yoktur, sadece arşiv kaydı silinir)
        """
        # e-Arşiv faturası oluştur (gönderilmiş)
        inv = self._create_sent_invoice(partner=self.partner_earsiv, scenario='EARSIVFATURA')
        inv.write({'x_efatura_type': 'earsiv'})

        # Wizard oluştur: kullanıcı "İptal Et" formunu doldurup onayladı
        wizard = self.env['sovos.cancel.invoice.wizard'].create({
            'invoice_id': inv.id,
            'cancel_reason': 'Fatura hatalı kesildi',
        })

        with patch(
            'l10n_tr_sovos_efatura.services.sovos_archive_service'
            '.SovosArchiveService.cancel_invoice',
            return_value=True,   # API başarılı yanıt verdi
        ) as mock_cancel:
            wizard.action_cancel()

        # API çağrısı yapıldı mı?
        mock_cancel.assert_called_once()
        # Fatura iptal durumuna geçti mi?
        self.assertEqual(inv.x_efatura_status, 'cancelled')
        # Odoo muhasebe durumu da iptal olmalı
        self.assertEqual(inv.state, 'cancel')

    def test_earsiv_cancel_without_reason_raises_user_error(self):
        """
        İptal gerekçesi boşsa UserError — kullanıcı gerekçe girmeden iptal edemez.

        GİB mevzuatı: iptal gerekçesi zorunludur, kayıt altına alınmalıdır.
        """
        inv = self._create_sent_invoice(partner=self.partner_earsiv, scenario='EARSIVFATURA')
        inv.write({'x_efatura_type': 'earsiv'})

        wizard = self.env['sovos.cancel.invoice.wizard'].create({
            'invoice_id': inv.id,
            'cancel_reason': '',   # boş gerekçe
        })

        with self.assertRaises(UserError) as cm:
            wizard.action_cancel()
        self.assertIn('gerekçe', str(cm.exception).lower())

    def test_earsiv_cancel_api_failure_raises_user_error(self):
        """
        Sovos API başarısız → UserError, fatura iptal edilMEMELİ.

        Savunmacı davranış:
            API exception attı → faturayı cancelled yapmak YANLIŞ olur.
            GİB'te hâlâ "aktif" durumda ama Odoo'da "cancelled" olursa uyumsuzluk.
            Hata yay → kullanıcı durumu görür, tekrar dener.
        """
        inv = self._create_sent_invoice(partner=self.partner_earsiv, scenario='EARSIVFATURA')
        inv.write({'x_efatura_type': 'earsiv'})

        wizard = self.env['sovos.cancel.invoice.wizard'].create({
            'invoice_id': inv.id,
            'cancel_reason': 'Test iptali',
        })

        with patch(
            'l10n_tr_sovos_efatura.services.sovos_archive_service'
            '.SovosArchiveService.cancel_invoice',
            side_effect=Exception('Sovos bağlantı hatası'),
        ), self.assertRaises(UserError):
            wizard.action_cancel()

        # Fatura HÂLâ 'sent' durumunda olmalı (değişmemeli)
        self.assertEqual(inv.x_efatura_status, 'sent')

    # ════════════════════════════════════════════════════════════════════
    # TEMELFATURA İPTAL (e-Fatura, tek taraflı)
    # ════════════════════════════════════════════════════════════════════

    def test_temelfatura_cancel_requires_confirmation_checkbox(self):
        """
        TEMELFATURA iptali için onay checkbox'u işaretlenmeli.

        TEMELFATURA iptalinde alıcı onayı GEREKMEZ (tek taraflı),
        ama kullanıcının bilinçli olarak "evet, iptal ediyorum" demesi istenir.
        Checkbox: x_confirm_cancel = True
        """
        inv = self._create_sent_invoice(scenario='TEMELFATURA')
        wizard = self.env['sovos.cancel.invoice.wizard'].create({
            'invoice_id': inv.id,
            'cancel_reason': 'Hatalı fatura',
            'x_confirm_cancel': False,   # onay YOK
        })

        with self.assertRaises(UserError) as cm:
            wizard.action_cancel()

        # Hata mesajında onay gerektiği belirtilmeli
        self.assertIn('onay', str(cm.exception).lower())

    def test_temelfatura_cancel_succeeds_with_confirmation(self):
        """
        Onay checkbox'u işaretlenince TEMELFATURA başarıyla iptal edilmeli.
        """
        inv = self._create_sent_invoice(scenario='TEMELFATURA')
        wizard = self.env['sovos.cancel.invoice.wizard'].create({
            'invoice_id': inv.id,
            'cancel_reason': 'Hatalı fatura',
            'x_confirm_cancel': True,    # onay VAR
        })

        with patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.cancel_invoice',
            return_value=True,
        ):
            wizard.action_cancel()

        self.assertEqual(inv.x_efatura_status, 'cancelled')

    # ════════════════════════════════════════════════════════════════════
    # TİCARİFATURA İPTAL — 8 GÜN MATRİSİ
    # ════════════════════════════════════════════════════════════════════

    def test_ticarifatura_cancel_blocked_after_8_days(self):
        """
        TICARIFATURA'da 8 gün geçtiyse iptal BLOKLANMALi.

        GİB mevzuatı: TICARIFATURA gönderildikten 8 gün sonra artık
        Odoo üzerinden iptal YAPILAMAZ. Kullanıcı GİB e-Fatura portalından
        manuel işlem yapmalıdır.

        timedelta(-1): deadline dün = 8 gün DOLDU.
        """
        inv = self._create_sent_invoice(scenario='TICARIFATURA')
        # Deadline geçmiş: dün
        inv.write({'x_inv_response_deadline': date.today() - timedelta(days=1)})

        wizard = self.env['sovos.cancel.invoice.wizard'].create({
            'invoice_id': inv.id,
            'cancel_reason': 'İptal denemesi',
            'x_confirm_cancel': True,
        })

        with self.assertRaises(UserError) as cm:
            wizard.action_cancel()

        # Hata mesajında portal yönlendirmesi olmalı
        self.assertIn('portal', str(cm.exception).lower())
        # Fatura hâlâ iptal olmamış
        self.assertNotEqual(inv.x_efatura_status, 'cancelled')

    def test_ticarifatura_cancel_allowed_within_8_days(self):
        """
        TICARIFATURA'da 8 gün DOLMADIYSA iptal mümkün.

        Deadline yarın = hâlâ 1 gün var → iptal yapılabilir.
        """
        inv = self._create_sent_invoice(scenario='TICARIFATURA')
        # Deadline yarın = süre dolmamış
        inv.write({'x_inv_response_deadline': date.today() + timedelta(days=1)})

        wizard = self.env['sovos.cancel.invoice.wizard'].create({
            'invoice_id': inv.id,
            'cancel_reason': 'Test iptali',
            'x_confirm_cancel': True,
        })

        with patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.cancel_invoice',
            return_value=True,
        ):
            wizard.action_cancel()

        self.assertEqual(inv.x_efatura_status, 'cancelled')

    def test_ticarifatura_cancel_allowed_on_deadline_day(self):
        """
        Deadline tam bugünse (son gün) iptal HÂLÂ mümkün.

        Sınır durumu testi:
            deadline < today → bloke (geçti)
            deadline == today → izin ver (bugün son gün ama henüz geçmedi)
            deadline > today → izin ver (süre var)
        """
        inv = self._create_sent_invoice(scenario='TICARIFATURA')
        inv.write({'x_inv_response_deadline': date.today()})   # tam bugün

        wizard = self.env['sovos.cancel.invoice.wizard'].create({
            'invoice_id': inv.id,
            'cancel_reason': 'Son gün iptali',
            'x_confirm_cancel': True,
        })

        with patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.cancel_invoice',
            return_value=True,
        ):
            # Exception fırlatılmamalı
            wizard.action_cancel()

        self.assertEqual(inv.x_efatura_status, 'cancelled')

    # ════════════════════════════════════════════════════════════════════
    # ACCEPTED FATURA KORUMASI
    # ════════════════════════════════════════════════════════════════════

    def test_accepted_invoice_cannot_be_cancelled(self):
        """
        GİB'in kabul ettiği (accepted) fatura iptal edileMEZ.

        GİB 1300 kodu döndürdü → fatura kesinleşti.
        Kesinleşmiş faturayı iptal etmek GİB mevzuatına aykırı.
        """
        inv = self._create_sent_invoice()
        # Kabul edilmiş olarak işaretle
        inv.write({'x_efatura_status': 'accepted'})

        wizard = self.env['sovos.cancel.invoice.wizard'].create({
            'invoice_id': inv.id,
            'cancel_reason': 'Kabul sonrası iptal denemesi',
            'x_confirm_cancel': True,
        })

        with self.assertRaises(UserError) as cm:
            wizard.action_cancel()

        self.assertIn('kabul', str(cm.exception).lower())


class TestResendWizard(SovosTestCommon):
    """
    Yeniden gönderim wizard testleri.

    Fatura Sovos'a gönderildi ama GİB hata kodu döndürdü (1101, 1103 vb.)
    Bu wizard ile düzeltilmiş XML tekrar gönderilir.

    Yeniden gönderim tipleri:
        same_uuid → Aynı UUID, teknik hatalar için (GİB'in kendi hataları)
        new_uuid  → Yeni UUID, içerik hataları için (1104 gibi)
    """

    # ════════════════════════════════════════════════════════════════════
    # SAME UUID YENİDEN GÖNDERİM
    # ════════════════════════════════════════════════════════════════════

    def test_resend_same_uuid_for_1103(self):
        """
        1103 (GİB imza hatası) → aynı UUID ile tekrar gönderilebilir.

        1103 açıklaması: İmza doğrulama başarısız, içerik doğru.
        Çözüm: Aynı UUID ile yeniden imzala ve gönder.
        """
        inv = self._create_sent_invoice()
        # 1103 hatası almış gibi set et
        inv.write({
            'x_efatura_status': 'error',
            'x_gib_status_code': 1103,
            'x_efatura_error_msg': 'GİB imza doğrulama hatası',
        })
        original_uuid = inv.x_sovos_uuid   # UUID korunmalı

        # same_uuid tipiyle wizard oluştur
        wizard = self.env['sovos.resend.invoice.wizard'].create({
            'invoice_id': inv.id,
            'resend_type': 'same_uuid',
        })

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            wizard.action_resend()

        # UUID değişmedi mi?
        self.assertEqual(inv.x_sovos_uuid, original_uuid,
            'same_uuid tipinde UUID değişmemeli')
        self.assertEqual(inv.x_efatura_status, 'sent')

    def test_resend_new_uuid_for_1104(self):
        """
        1104 hatası → yeni UUID ile yeniden gönderilmeli.

        1104 açıklaması: Fatura içeriğinde kritik hata.
        Çözüm: İçerik düzeltildi, yeni UUID ile yeni fatura olarak gönder.

        UUID değişmeli: eski UUID GİB'te "hatalı" olarak işaretli,
        aynı UUID ile göndermek çakışmaya yol açar.
        """
        inv = self._create_sent_invoice()
        inv.write({
            'x_efatura_status': 'error',
            'x_gib_status_code': 1104,
        })
        original_uuid = inv.x_sovos_uuid

        wizard = self.env['sovos.resend.invoice.wizard'].create({
            'invoice_id': inv.id,
            'resend_type': 'new_uuid',
        })

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_invoice_success():
            wizard.action_resend()

        # UUID DEĞİŞMELİ
        self.assertNotEqual(inv.x_sovos_uuid, original_uuid,
            'new_uuid tipinde UUID yenilenmeli')
        self.assertTrue(inv.x_sovos_uuid,
            'Yeni UUID boş olamaz')

    def test_resend_requires_correct_type_for_error_code(self):
        """
        1103 hatası için new_uuid tipi seçilirse UserError.

        İş kuralı uyumu:
            1103 → same_uuid ile çözülmeli (RETRY_SAME_UUID setinde)
            Kullanıcı yanlış tip seçtiyse düzelt, engelme.
        """
        inv = self._create_sent_invoice()
        inv.write({'x_efatura_status': 'error', 'x_gib_status_code': 1103})

        wizard = self.env['sovos.resend.invoice.wizard'].create({
            'invoice_id': inv.id,
            'resend_type': 'new_uuid',   # yanlış tip! 1103 için same_uuid olmalı
        })

        with self.assertRaises(UserError) as cm:
            wizard.action_resend()

        # Hata mesajında "aynı UUID" kullanması gerektiği belirtilmeli
        self.assertIn('same_uuid', str(cm.exception).lower())

    def test_resend_blocked_for_accepted_invoice(self):
        """
        Accepted (kabul edilmiş) fatura TEKRAR GÖNDERİLEMEZ.

        Kesinleşmiş faturayı tekrar göndermek mükerrer fatura oluşturur.
        Bu hem hukuki hem de muhasebe açısından ciddi sorun.
        """
        inv = self._create_sent_invoice()
        inv.write({'x_efatura_status': 'accepted'})

        wizard = self.env['sovos.resend.invoice.wizard'].create({
            'invoice_id': inv.id,
            'resend_type': 'same_uuid',
        })

        with self.assertRaises(UserError) as cm:
            wizard.action_resend()

        self.assertIn('hatalı', str(cm.exception).lower())

    def test_resend_blocked_for_non_error_status(self):
        """
        'sent' (gönderilmiş, bekleniyor) durumundaki fatura tekrar gönderilmemeli.

        Yeniden gönderim sadece 'error' durumundaki faturalar için mantıklı.
        Cevap bekleyen faturayı tekrar göndermek çakışmaya yol açar.
        """
        inv = self._create_sent_invoice()
        # x_efatura_status = 'sent' (zaten _create_sent_invoice'da set edildi)

        wizard = self.env['sovos.resend.invoice.wizard'].create({
            'invoice_id': inv.id,
            'resend_type': 'same_uuid',
        })

        with self.assertRaises(UserError):
            wizard.action_resend()

    # ════════════════════════════════════════════════════════════════════
    # SOVOS HATASI — YENİDEN GÖNDERİMDE
    # ════════════════════════════════════════════════════════════════════

    def test_resend_sovos_failure_preserves_error_status(self):
        """
        Yeniden gönderimde de Sovos erişilemezse status 'error' kalmali.

        Resend denendi ama yine başarısız oldu.
        En azından eski hata durumu korunsun, 'sent' gibi yanlış durum atanmasın.
        """
        inv = self._create_sent_invoice()
        inv.write({'x_efatura_status': 'error', 'x_gib_status_code': 1103})

        wizard = self.env['sovos.resend.invoice.wizard'].create({
            'invoice_id': inv.id,
            'resend_type': 'same_uuid',
        })

        with self._mock_ubl_builder(), \
             self._mock_validator_valid(), \
             self._mock_sovos_failure('Sovos tekrar kapalı'), \
             self.assertRaises(UserError):
            wizard.action_resend()

        # Hata durumu korunmalı (yanlış durum atanmamalı)
        self.assertEqual(inv.x_efatura_status, 'error')

    def test_resend_validation_failure_preserves_error_status(self):
        """
        Yeniden göndermeden önce validasyon başarısız → error kalmalı.

        XML tekrar üretildi ama hâlâ XSD hatası var.
        Düzeltilmeden gönderilmeye çalışılıyor.
        """
        inv = self._create_sent_invoice()
        inv.write({'x_efatura_status': 'error', 'x_gib_status_code': 1103})

        wizard = self.env['sovos.resend.invoice.wizard'].create({
            'invoice_id': inv.id,
            'resend_type': 'same_uuid',
        })

        with self._mock_ubl_builder(), \
             self._mock_validator_xsd_fail(['cbc:ID zorunlu']), \
             self.assertRaises(UserError):
            wizard.action_resend()

        self.assertEqual(inv.x_efatura_status, 'error')

    # ════════════════════════════════════════════════════════════════════
    # WIZARD KAPATILINCA DEĞIŞIKLIK OLMAMALI
    # ════════════════════════════════════════════════════════════════════

    def test_cancel_wizard_discard_does_not_change_invoice(self):
        """
        Wizard "İptal" butonu (kaydetme, discard) → faturada değişiklik olmamalı.

        Kullanıcı wizard açtı sonra "Vazgeç" veya "Kapat" dedi.
        action_cancel() çağrılmadı → fatura olduğu gibi kalmalı.

        Bu test action_cancel() çağrılmadığında durum değişmediğini doğrular.
        """
        inv = self._create_sent_invoice()
        original_status = inv.x_efatura_status   # 'sent'

        # Wizard oluşturuldu ama action_cancel() ÇAĞRILMADI
        wizard = self.env['sovos.cancel.invoice.wizard'].create({
            'invoice_id': inv.id,
            'cancel_reason': 'Vazgeçtim',
        })
        # Wizard sadece oluşturuldu, action çağrılmadı → fatura değişmemeli

        # Durum aynı mı?
        self.assertEqual(inv.x_efatura_status, original_status,
            'Wizard action çağrılmadan fatura değişmemeli')

    def test_resend_wizard_discard_does_not_change_invoice(self):
        """
        Resend wizard kapatılınca fatura olduğu gibi kalmalı.
        """
        inv = self._create_sent_invoice()
        inv.write({'x_efatura_status': 'error', 'x_gib_status_code': 1103})
        original_uuid = inv.x_sovos_uuid

        # Wizard oluşturuldu ama action_resend() ÇAĞRILMADI
        wizard = self.env['sovos.resend.invoice.wizard'].create({
            'invoice_id': inv.id,
            'resend_type': 'same_uuid',
        })

        # UUID değişmedi mi?
        self.assertEqual(inv.x_sovos_uuid, original_uuid)
        # Durum error kalmış mı?
        self.assertEqual(inv.x_efatura_status, 'error')
