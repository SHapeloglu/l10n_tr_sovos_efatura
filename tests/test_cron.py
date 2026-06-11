# -*- coding: utf-8 -*-
"""
Cron & Senkronizasyon Testleri — v6.1
=======================================
Test edilen kod: models/sovos_sync.py
Test edilen sınıf: sovos.sync

CRON GÖREVLERİ NELERDİR?
-------------------------
Odoo'da "cron" = belirli aralıklarla otomatik çalışan görevler.
Bu modüldeki cron'lar:

    cron_sync_incoming_invoices
        → Sovos'tan gelen (bize gönderilen) faturaları çek
        → Her 1 saatte bir

    cron_sync_efatura_status
        → Gönderdiğimiz e-Fatura'ların GİB durumunu sorgula
        → Her 30 dakikada bir

    cron_sync_earsiv_status (v6.1 YENİ)
        → Gönderdiğimiz e-Arşiv'lerin durumunu sorgula (ayrı endpoint)
        → Her 30 dakikada bir

    cron_check_8day_deadline
        → 8 günlük yanıt süresi dolmak üzere olan TICARIFATURA'ları uyar
        → Her gün

    cron_refresh_vkn_cache
        → Bayat VKN cache'lerini yenile
        → Her gece

v6.1 YENİ:
  - cron_sync_earsiv_status() → ayrı e-Arşiv cron (GetInvoiceDocument)
  - _notify_admin() → mail.mail + Odoo chatter (mail.message)
  - _check_8day_for_company() → compute field bypass, tarih hesabı burada

Risk Seviyesi: ORTA — cron hataları gecikmeye yol açar ama acil değil
"""
from datetime import date, timedelta
from unittest.mock import patch, MagicMock, call

from odoo.exceptions import UserError

from .common import SovosTestCommon


class TestCronSync(SovosTestCommon):
    """
    Cron görevlerinin doğru çalıştığını doğrulayan testler.

    Cron metodları doğrudan çağrılır (gerçekten zamanlayıcı beklenmez).
    Sovos API çağrıları mock'lanır.
    """

    # ════════════════════════════════════════════════════════════════════
    # GELEN FATURA SENKRONİZASYONU
    # Tedarikçiler bize e-Fatura gönderdi → Odoo'ya çek
    # ════════════════════════════════════════════════════════════════════

    def test_incoming_invoice_created_with_partner(self):
        """
        Gelen faturanın gönderici VKN'i Odoo'daki bir partner ile eşleşiyorsa
        partner_id dolu in_invoice (alış faturası) oluşturulmalı.

        Akış:
            Sovos.get_inbound_list() → [{'uuid': ..., 'sender_vkn': ...}]
            VKN eşleşti → partner bulundu
            in_invoice oluştur → partner_id = partner
            x_efatura_status = 'accepted' (bize geldi = kabul)
        """
        sync = self.env['sovos.sync']

        # Sovos'tan gelecek fatura verisi (mock)
        mock_invoices = [{
            'uuid': 'inbound-uuid-0001',
            # sender_vkn = self.partner_efatura.vat → Odoo'da bu partner var
            'sender_vkn': self.partner_efatura.vat,
            'invoice_date': '2026-06-01',
        }]

        with patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.get_inbound_list',
            return_value=mock_invoices,
        ):
            sync._sync_incoming_for_company(self.company)

        # Oluşturulan faturayı bul
        created = self.env['account.move'].search([
            ('x_sovos_uuid', '=', 'inbound-uuid-0001'),
            ('move_type', '=', 'in_invoice'),  # alış faturası
        ])
        self.assertTrue(created)
        self.assertEqual(created.partner_id, self.partner_efatura)
        # Gelen fatura = kabul edildi (bizim tarafımızdan)
        self.assertEqual(created.x_efatura_status, 'accepted')

    def test_incoming_invoice_created_without_partner(self):
        """
        Gönderici VKN Odoo'da bulunamazsa partner_id=False, fatura yine oluşturulmalı.

        Neden fatura yine oluşturulur?
            Muhasebeci bu faturayı görüp manuel olarak partner eşlemesi yapabilmeli.
            Faturayı tamamen yok saymak daha kötü olur — kayıt kalmalı.

        partner_id=False → Odoo'da "ortaksız" kayıt (muhasebe fişi oluşmaz, bekler)
        """
        sync = self.env['sovos.sync']
        mock_invoices = [{
            'uuid': 'inbound-uuid-0002',
            'sender_vkn': '9999999999',   # Odoo'da bu VKN'e sahip partner YOK
            'invoice_date': '2026-06-01',
        }]
        with patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.get_inbound_list',
            return_value=mock_invoices,
        ):
            sync._sync_incoming_for_company(self.company)

        created = self.env['account.move'].search([
            ('x_sovos_uuid', '=', 'inbound-uuid-0002'),
        ])
        self.assertTrue(created)
        # Partner bulunamadı → False
        self.assertFalse(created.partner_id,
            'Partner bulunamazsa partner_id=False olmalı — muhasebe fişi oluşmaz')

    def test_incoming_invoice_not_duplicated(self):
        """
        Aynı UUID ikinci kez Sovos'tan gelirse yeni kayıt OLUŞTURULMAMALI.

        Cron her çalışmasında Sovos'tan son N günün faturalarını çeker.
        Aynı fatura birden fazla kez gelirse idempotent olmalı
        (mükerrer kayıt oluşmamalı).

        search_count(): bu UUID'ye sahip kaç kayıt var?
        1 olmalı → 2 olursa mükerrer demek.
        """
        sync = self.env['sovos.sync']
        existing_uuid = 'inbound-uuid-exist'

        # Faturayı DB'ye elle ekle (zaten var gibi)
        self.env['account.move'].create({
            'move_type': 'in_invoice',
            'x_sovos_uuid': existing_uuid,
            'partner_id': self.partner_efatura.id,
            'journal_id': self.env['account.journal'].search([
                ('type', '=', 'purchase'), ('company_id', '=', self.company.id),
            ], limit=1).id,
        })

        # Aynı UUID tekrar Sovos'tan geliyor
        mock_invoices = [{'uuid': existing_uuid, 'sender_vkn': '1111111111'}]
        with patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.get_inbound_list',
            return_value=mock_invoices,
        ):
            sync._sync_incoming_for_company(self.company)

        # Hâlâ sadece 1 kayıt olmalı
        count = self.env['account.move'].search_count([('x_sovos_uuid', '=', existing_uuid)])
        self.assertEqual(count, 1, 'Mükerrer kayıt oluşturulmamalı')

    # ════════════════════════════════════════════════════════════════════
    # E-FATURA DURUM TAKİBİ
    # Gönderdiğimiz faturaların GİB'teki durumunu sorgula
    # ════════════════════════════════════════════════════════════════════

    def test_efatura_status_cron_queries_sent_invoices(self):
        """
        e-Fatura status cron → 'sent'/'sending' durumundaki e-Fatura'ları sorgular.

        Akış:
            1. x_efatura_type='efatura' + x_efatura_status='sent' faturalar bul
            2. Her biri için get_envelope_status(envelope_uuid) çağır
            3. Gelen kodu _process_gib_status() ile işle
        """
        inv = self._create_sent_invoice()   # x_efatura_type='efatura' (varsayılan)

        with patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.get_envelope_status',
            return_value=(1300, 'Başarılı'),    # GİB kabul etti
        ) as mock_status:
            self.env['sovos.sync']._sync_efatura_status_for_company(self.company)

        # Envelope UUID ile sorgulama yapıldı mı?
        mock_status.assert_called_once_with(inv.x_sovos_envelope_uuid)
        # 1300 işlendi → accepted oldu
        self.assertEqual(inv.x_efatura_status, 'accepted')

    def test_efatura_status_cron_skips_earsiv_invoices(self):
        """
        v6.1: e-Fatura cron e-Arşiv faturalarını SORGULAMAZ (ayrı cron var).

        e-Fatura endpoint'i: GetEnvelopeStatus (envelope_uuid ile)
        e-Arşiv endpoint'i: GetInvoiceDocument (invoice_uuid ile)
        Farklı endpoint'ler → farklı cron'lar.
        """
        # e-Arşiv faturası oluştur
        inv = self._create_sent_invoice(partner=self.partner_earsiv, scenario='EARSIVFATURA')
        inv.write({'x_efatura_type': 'earsiv'})

        with patch(
            'l10n_tr_sovos_efatura.services.sovos_invoice_service'
            '.SovosInvoiceService.get_envelope_status',
        ) as mock_status:
            self.env['sovos.sync']._sync_efatura_status_for_company(self.company)

        # e-Arşiv faturası sorgulanmamalı
        mock_status.assert_not_called()

    # ════════════════════════════════════════════════════════════════════
    # E-ARŞİV AYRI CRON — v6.1 YENİ
    # ════════════════════════════════════════════════════════════════════

    def test_earsiv_status_cron_queries_earsiv_invoices(self):
        """
        v6.1 YENİ: e-Arşiv cron → ArchiveService.get_invoice_status() çağrılmalı.

        e-Arşiv için farklı metod: invoice_uuid ile (envelope_uuid değil).
        """
        inv = self._create_sent_invoice(partner=self.partner_earsiv, scenario='EARSIVFATURA')
        inv.write({'x_efatura_type': 'earsiv'})

        with patch(
            'l10n_tr_sovos_efatura.services.sovos_archive_service'
            '.SovosArchiveService.get_invoice_status',
            return_value=(1300, 'Başarılı'),
        ) as mock_status:
            self.env['sovos.sync']._sync_earsiv_status_for_company(self.company)

        # invoice UUID ile (envelope değil) sorgu yapıldı mı?
        mock_status.assert_called_once_with(inv.x_sovos_uuid)
        self.assertEqual(inv.x_efatura_status, 'accepted')

    def test_earsiv_cron_skips_efatura_invoices(self):
        """e-Arşiv cron e-Fatura'ları sorgulamaz. Simetrik ayrım."""
        inv = self._create_sent_invoice()   # x_efatura_type='efatura'

        with patch(
            'l10n_tr_sovos_efatura.services.sovos_archive_service'
            '.SovosArchiveService.get_invoice_status',
        ) as mock_status:
            self.env['sovos.sync']._sync_earsiv_status_for_company(self.company)

        mock_status.assert_not_called()

    # ════════════════════════════════════════════════════════════════════
    # ADMİN BİLDİRİMİ — v6.1 güncellendi
    # ════════════════════════════════════════════════════════════════════

    def test_notify_admin_creates_mail_message(self):
        """
        _notify_admin() → mail.message oluşturulmalı (Odoo chatter bildirimi).

        mail.message: Odoo'nun dahili mesajlaşma sistemi.
        res.company kaydının chatter'ına mesaj eklenir.
        Admin Odoo'ya girince "Sovos hatası" mesajını görecek.

        Sayım yöntemi:
            Önceki mesaj sayısını al → bildirim gönder → sonraki sayı öncekinden büyük mü?
        """
        sync = self.env['sovos.sync']

        # Bildirim öncesi şirkete ait mesaj sayısı
        mail_msg_count_before = self.env['mail.message'].search_count([
            ('model', '=', 'res.company'),
            ('res_id', '=', self.company.id),
        ])

        sync._notify_admin(self.company, 'cron_test', 'Test hata mesajı')

        mail_msg_count_after = self.env['mail.message'].search_count([
            ('model', '=', 'res.company'),
            ('res_id', '=', self.company.id),
        ])
        # Sonraki sayı öncekinden büyük olmalı (en az 1 yeni mesaj)
        self.assertGreater(mail_msg_count_after, mail_msg_count_before)

    def test_notify_admin_sends_email_when_admin_email_set(self):
        """
        v6.1 YENİ: x_sovos_admin_email doluysa mail.mail (gerçek e-posta) de gönderilmeli.

        İki tür bildirim:
            mail.message → Odoo chatter'da görünür (dahili)
            mail.mail    → gerçek e-posta gönderilir (dışsal)

        mail.mail.send() mock'lanıyor: gerçekten e-posta atmıyoruz,
        sadece "mail.mail kaydı oluşturuldu mu?" diye bakıyoruz.
        """
        self.company.x_sovos_admin_email = 'admin@test.com'
        sync = self.env['sovos.sync']

        with patch.object(
            self.env['mail.mail'].__class__, 'send', return_value=None
        ) as mock_send:
            mail_count_before = self.env['mail.mail'].search_count([
                ('email_to', '=', 'admin@test.com'),
            ])
            sync._notify_admin(self.company, 'test_task', 'Hata')
            mail_count_after = self.env['mail.mail'].search_count([
                ('email_to', '=', 'admin@test.com'),
            ])

        # Admin e-postası oluşturulmuş olmalı
        self.assertGreater(mail_count_after, mail_count_before,
            'Admin e-postası oluşturulmalı')

    def test_cron_continues_after_single_company_failure(self):
        """
        Bir şirket için cron başarısız olursa diğer şirketler ETKILENMEMELI.

        Multi-company ortamda kritik:
            Şirket A'nın Sovos bağlantısı kopuk → Şirket A için hata
            Şirket B normal çalışmalı — A'nın hatası B'yi durdurmamalı

        Test stratejisi:
            Şirket 1 exception fırlatan, Şirket 2 normal çalışan mock yaz.
            İkisi de çalıştırıldı mı? call_order listesiyle doğrula.
        """
        # İkinci şirket oluştur
        company2 = self.env['res.company'].create({
            'name': 'Test Şirket 2',
            'x_sovos_invoice_user': 'user2',
        })

        sync = self.env['sovos.sync']
        call_order = []

        def failing_then_ok(company):
            """Şirket 1 için exception, Şirket 2 için normal çalış."""
            call_order.append(company.id)
            if company.id == self.company.id:
                raise Exception('Şirket 1 hatası')

        # patch.object: sync instance'ının metodunu değiştir
        with patch.object(sync, '_sync_incoming_for_company', side_effect=failing_then_ok), \
             patch.object(sync, '_notify_admin'):   # bildirim de mock'la (gereksiz log)
            sync._cron_run_for_all_companies('cron_sync_incoming_invoices')

        # Şirket 2 çağrıldı mı? (Şirket 1 çaksa bile)
        self.assertIn(company2.id, call_order,
            'Şirket 1 başarısız olsa da Şirket 2 çalışmalı')

    # ════════════════════════════════════════════════════════════════════
    # 8 GÜN UYARISI
    # TICARIFATURA yanıt süresi dolmak üzere
    # ════════════════════════════════════════════════════════════════════

    def test_8day_warning_cron_posts_message_on_expiring_invoices(self):
        """
        Deadline bugün veya yarın olan TICARIFATURA'lara chatter mesajı ekle.

        v6.1 NOT: store=False compute field bypass — x_show_8day_warning computed
        field'ini doğrudan okumak yerine, cron kendi tarih hesabını yapıyor.
        (store=False: DB'ye yazılmıyor, her okumada hesaplanıyor — cron bunu bypass eder)
        """
        inv = self._create_sent_invoice(scenario='TICARIFATURA')
        inv.write({
            'x_inv_response_deadline': date.today(),   # bugün son gün!
            'x_inv_response_status': 'beklemede',
        })

        # Cron öncesi mesaj sayısı
        msg_count_before = self.env['mail.message'].search_count([
            ('model', '=', 'account.move'),
            ('res_id', '=', inv.id),
        ])

        self.env['sovos.sync']._check_8day_for_company(self.company)

        msg_count_after = self.env['mail.message'].search_count([
            ('model', '=', 'account.move'),
            ('res_id', '=', inv.id),
        ])
        # En az 1 yeni mesaj eklenmiş olmalı
        self.assertGreater(msg_count_after, msg_count_before)

    def test_8day_warning_cron_skips_already_responded(self):
        """
        Kabul/red almış faturalara uyarı mesajı EKLENMEMELI.

        Alıcı zaten yanıt verdi → artık deadline uyarısı anlamsız.
        patch.object(inv, 'message_post'): bu faturanın mesaj ekleme metodunu izle.
        assert_not_called(): hiç çağrılmadı = mesaj eklenmedi.
        """
        inv = self._create_sent_invoice(scenario='TICARIFATURA')
        inv.write({
            'x_inv_response_deadline': date.today(),
            'x_inv_response_status': 'kabul',    # zaten kabul geldi
        })

        with patch.object(inv, 'message_post') as mock_post:
            self.env['sovos.sync']._check_8day_for_company(self.company)
        # Kabul almış faturaya mesaj eklenmemeli
        mock_post.assert_not_called()

    # ════════════════════════════════════════════════════════════════════
    # VKN CACHE CRON
    # ════════════════════════════════════════════════════════════════════

    def test_vkn_cache_cron_refreshes_stale_partners(self):
        """
        31 günlük bayat cache → cron refresh_efatura_type() çağırmalı.

        Cron her gece çalışır, bayat cache'li müşterileri yeniler.
        """
        self.partner_efatura.write({
            'x_efatura_type_updated': date.today() - timedelta(days=31),
            'customer_rank': 1,   # müşteri olarak işaretli (cron filtresi)
        })

        with patch(
            'l10n_tr_sovos_efatura.models.res_partner.ResPartner.refresh_efatura_type'
        ) as mock_refresh:
            self.env['sovos.sync']._refresh_vkn_for_company(self.company)

        # Bayat partner için refresh çağrıldı mı?
        mock_refresh.assert_called()

    def test_vkn_cache_cron_skips_fresh_partners(self):
        """
        10 günlük taze cache → cron yenileme YAPMAMALIIDIR.

        Performans: Gereksiz Sovos API çağrılarını engelle.
        """
        self.partner_efatura.write({
            'x_efatura_type_updated': date.today() - timedelta(days=10),
            'customer_rank': 1,
        })

        with patch(
            'l10n_tr_sovos_efatura.models.res_partner.ResPartner.refresh_efatura_type'
        ) as mock_refresh:
            self.env['sovos.sync']._refresh_vkn_for_company(self.company)

        # Taze partner için refresh çağrılmamalı
        mock_refresh.assert_not_called()
