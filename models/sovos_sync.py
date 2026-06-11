# -*- coding: utf-8 -*-
"""
sovos_sync.py — Sovos Arka Plan Görevleri (Cron İşleri)
=========================================================
Bu model, Odoo'nun zamanlı görev sistemi (ir.cron) tarafından düzenli
aralıklarla çağrılan senkronizasyon işlevlerini içerir.

Tüm cron görevleri data/ir_cron_data.xml dosyasında tanımlanmıştır.

Görev Özeti:
  cron_sync_incoming_invoices  → Gelen faturaları Sovos'tan çeker (15 dk)
  cron_sync_efatura_status     → e-Fatura GİB durum takibi (30 dk)
  cron_sync_earsiv_status      → e-Arşiv durum takibi (30 dk, ayrı servis)
  cron_sync_inv_responses      → TICARIFATURA KABUL/RED yanıtları (1 saat)
  cron_check_8day_warnings     → 8 gün yanıt uyarısı (günlük)
  cron_refresh_vkn_cache       → Partner VKN cache yenileme (günlük)

Multi-company Desteği:
  _cron_run_for_all_companies() tüm görevlerde kullanılır.
  Sovos hesabı olan her şirket için ilgili görevi ayrı ayrı çalıştırır.
  Bir şirkette hata olursa diğerleri etkilenmez (try/except + continue).
"""
import logging
from datetime import date, timedelta

from odoo import models, api, fields, _

_logger = logging.getLogger(__name__)


class SovosSync(models.Model):
    # Tamamen yeni bir model; mevcut modeli genişletmiyor.
    # _name: Odoo veritabanında bu adla tablo oluşturur (sovos_sync).
    _name = 'sovos.sync'
    _description = 'Sovos Senkronizasyon Görevleri'

    # ── Ortak Yardımcılar ─────────────────────────────────────────────────

    @api.model
    def _cron_run_for_all_companies(self, task_fn_name):
        """
        Tüm şirketler için belirtilen görevi çalıştırır.

        Parametreler:
            task_fn_name (str): Bu sınıftaki metod adı (ör: '_sync_efatura_status_for_company')

        Neden string kullanılıyor?
            cron XML dosyasından doğrudan method ismi geçirilemiyor;
            string alıp getattr ile dinamik çağrı yapıyoruz.

        Hata yönetimi:
            Bir şirkette hata olursa: loglanır + admin bildirilir + sonraki şirkete geçilir.
            Bu sayede bir şirketin sorunu diğer şirketlerin cron'unu durdurmaz.
        """
        # Sovos hesabı tanımlı olan şirketleri al
        companies = self.env['res.company'].search([
            ('x_sovos_invoice_user', '!=', False)
        ])

        # getattr: string metod adından fonksiyon referansı alır
        # Örnek: getattr(self, '_sync_efatura_status_for_company')
        task_fn = getattr(self, task_fn_name)

        for company in companies:
            try:
                task_fn(company)
            except Exception as e:
                _logger.error('[%s] %s hatası: %s', company.name, task_fn_name, e)
                # Hata oluştu ama diğer şirketler için devam et
                self._notify_admin(company, task_fn_name, str(e))
                continue  # Bir sonraki şirkete geç

    def _notify_admin(self, company, task_name, error_msg):
        """
        Cron hatalarında sistem yöneticisine Odoo iç bildirimi ve e-posta gönderir.

        İki kanaldan bildirim:
          1. Odoo mail.message → şirket kaydı üzerine not olarak görünür
          2. E-posta → x_sovos_admin_email doluysa harici bildirim

        Hata toleransı:
            Bildirim gönderme de başarısız olursa sadece loglanır;
            exception fırlatılmaz (sonsuz hata döngüsü önlenir).
        """
        try:
            # base.user_admin: Odoo'nun varsayılan sistem yöneticisi
            admin = self.env.ref('base.user_admin')

            # mail.message: Odoo chatter sistemine not ekler
            self.env['mail.message'].create({
                'model': 'res.company',         # Nereye ekleneceği (şirket kaydı)
                'res_id': company.id,            # Hangi şirketin üzerine
                'message_type': 'comment',       # Yorum türünde not
                'subtype_id': self.env.ref('mail.mt_note').id,  # Not alt türü (log)
                'body': '<p><strong>⚠ e-Fatura Cron Hatası — %s</strong><br/>%s: %s</p>' % (
                    company.name, task_name, error_msg
                ),
                'partner_ids': [(4, admin.partner_id.id)],  # (4, id) = many2many'e ekle
                'author_id': self.env.ref('base.user_root').partner_id.id,
            })

            # Harici e-posta bildirimi (admin e-postası tanımlıysa)
            if company.x_sovos_admin_email:
                self.env['mail.mail'].create({
                    'subject': '[Odoo e-Fatura] Cron Hatası — %s' % company.name,
                    'body_html': '<p>%s cron görevi başarısız: %s</p>' % (task_name, error_msg),
                    'email_to': company.x_sovos_admin_email,
                }).send()

        except Exception as e:
            # Bildirim göndermek de başarısız oldu — sadece logla, exception fırlatma
            _logger.error('Admin bildirimi gönderilemedi: %s', e)

    # ── Gelen Fatura Senkronizasyonu (15 dk) ──────────────────────────────

    @api.model
    def cron_sync_incoming_invoices(self):
        """
        Cron entry point — gelen faturaları senkronize eder.
        ir_cron_data.xml'de 15 dakikada bir çalışmak üzere tanımlanmıştır.

        @api.model: self'in belirli bir kaydı temsil etmediği, model metodlarında kullanılır.
        """
        self._cron_run_for_all_companies('_sync_incoming_for_company')

    def _sync_incoming_for_company(self, company):
        """
        Tek şirket için gelen faturaları Sovos'tan çekip Odoo'ya kaydeder.

        Duplikasyon önlemi:
            UUID zaten varsa fatura tekrar oluşturulmaz.
            Bu sayede cron her çalıştığında aynı fatura ikinci kez eklenmez.

        Limitasyon:
            Gelen fatura satır detayları (kalemler) şu an alınmıyor; sadece başlık bilgisi.
            Tam implementasyon için Sovos'tan UBL XML çekilip parse edilmesi gerekir.
        """
        from ..services.sovos_invoice_service import SovosInvoiceService
        svc = SovosInvoiceService(company)

        # Sovos'tan gelen faturaların listesini al
        invoices = svc.get_inbound_list()

        # with_company(company): Çok şirketli ortamda doğru şirket bağlamında çalıştır
        AccountMove = self.env['account.move'].with_company(company)

        for inv_data in invoices:
            uuid = inv_data.get('uuid')
            if not uuid:
                continue  # UUID yoksa bu kaydı atla

            # Aynı UUID ile daha önce oluşturulmuş alış faturası var mı?
            existing = AccountMove.search([
                ('x_sovos_uuid', '=', uuid),
                ('move_type', '=', 'in_invoice'),  # in_invoice = alış faturası
            ], limit=1)

            if existing:
                continue  # Zaten var → atla (duplikasyon önlemi)

            # Gönderici VKN ile partner bul
            partner = self._find_partner_by_vkn(inv_data.get('sender_vkn'))

            # Yeni alış faturası oluştur (taslak olarak)
            AccountMove.create({
                'move_type': 'in_invoice',                   # Alış faturası
                'partner_id': partner.id if partner else False,
                'invoice_date': inv_data.get('invoice_date'),
                'x_sovos_uuid': uuid,
                'x_efatura_status': 'accepted',              # Gelen fatura zaten kabul edilmiş
                'x_efatura_type': 'efatura',
            })

    def _find_partner_by_vkn(self, vkn):
        """
        VKN/TCKN ile Odoo'daki eşleşen partneri bulur.

        Returns: res.partner kaydı veya False (bulunamazsa)
        Kullanım: Gelen fatura için gönderici firma tespiti.
        """
        if not vkn:
            return False
        # limit=1: Birden fazla partner aynı VKN ile kayıtlıysa ilkini al
        return self.env['res.partner'].search([('vat', '=', vkn)], limit=1)

    # ── e-Fatura GİB Durum Takibi (30 dk) ────────────────────────────────

    @api.model
    def cron_sync_efatura_status(self):
        """
        Cron entry point — e-Fatura GİB durum takibi.
        Gönderilmiş ('sent', 'sending') e-Faturaların GİB durumunu Sovos'tan sorgular.
        ir_cron_data.xml'de 30 dakikada bir çalışır.
        """
        self._cron_run_for_all_companies('_sync_efatura_status_for_company')

    def _sync_efatura_status_for_company(self, company):
        """
        Tek şirket için beklemedeki e-Faturaların durumlarını günceller.

        Filtre: sent veya sending + efatura + envelope_uuid dolu
        Neden envelope_uuid? GetEnvelopeStatus çağrısı bu UUID'ye ihtiyaç duyar.

        Hata toleransı:
            Tek bir faturanın sorgusu başarısız olursa diğerleri etkilenmez.
            Örnek: Bir fatura için Sovos zaman aşımı → sadece o fatura atlanır.
        """
        from ..services.sovos_invoice_service import SovosInvoiceService
        svc = SovosInvoiceService(company)

        # Durumu hâlâ belirsiz olan e-Faturaları bul
        pending = self.env['account.move'].with_company(company).search([
            ('x_efatura_status', 'in', ('sent', 'sending')),
            ('x_efatura_type', '=', 'efatura'),
            ('x_sovos_envelope_uuid', '!=', False),  # Envelope UUID olmalı
        ])

        for move in pending:
            try:
                # Sovos'tan durum kodu al (ör: 1300, 1215, 1104 vb.)
                status_code, status_msg = svc.get_envelope_status(move.x_sovos_envelope_uuid)
                # Koda göre Odoo durumunu güncelle
                move._process_gib_status(status_code, status_msg)
            except Exception as e:
                # Bu fatura için sorgu başarısız → logla, sonrakine geç
                _logger.warning('Durum sorgusu başarısız (%s): %s', move.x_sovos_uuid, e)

    # ── e-Arşiv Durum Takibi (30 dk — AYRI SERVİS) ────────────────────────

    @api.model
    def cron_sync_earsiv_status(self):
        """
        Cron entry point — e-Arşiv durum takibi.
        e-Arşiv faturalar ArchiveService üzerinden sorgulanır (InvoiceService değil).
        ir_cron_data.xml'de 30 dakikada bir çalışır.

        Neden ayrı cron?
            e-Fatura InvoiceService.GetEnvelopeStatus kullanırken
            e-Arşiv ArchiveService.GetInvoiceStatus kullanır.
            Her ikisi farklı SOAP endpoint'leridir.
        """
        self._cron_run_for_all_companies('_sync_earsiv_status_for_company')

    def _sync_earsiv_status_for_company(self, company):
        """
        Tek şirket için beklemedeki e-Arşiv faturalarının durumlarını günceller.

        Filtre: sent veya sending + earsiv + sovos_uuid dolu
        NOT: e-Arşiv'de envelope_uuid yoktur; x_sovos_uuid ile sorgu yapılır.
        """
        from ..services.sovos_archive_service import SovosArchiveService
        svc = SovosArchiveService(company)

        pending = self.env['account.move'].with_company(company).search([
            ('x_efatura_status', 'in', ('sent', 'sending')),
            ('x_efatura_type', '=', 'earsiv'),
            ('x_sovos_uuid', '!=', False),
        ])

        for move in pending:
            try:
                status_code, status_msg = svc.get_invoice_status(move.x_sovos_uuid)
                move._process_gib_status(status_code, status_msg)
            except Exception as e:
                _logger.warning('e-Arşiv durum sorgusu başarısız (%s): %s', move.x_sovos_uuid, e)

    # ── TICARIFATURA KABUL/RED Yanıt Takibi (1 saat) ──────────────────────

    @api.model
    def cron_sync_inv_responses(self):
        """
        Cron entry point — TICARIFATURA ApplicationResponse takibi.
        GİB'e kayıtlı alıcı firmalar 8 gün içinde KABUL veya RED yanıtı gönderebilir.
        Bu yanıtlar Sovos'tan periyodik olarak sorgulanır (1 saatte bir).
        """
        self._cron_run_for_all_companies('_sync_inv_responses_for_company')

    def _sync_inv_responses_for_company(self, company):
        """
        TICARIFATURA KABUL/RED yanıtlarını Sovos'tan alır ve ilgili faturalara işler.

        GetInvResponses OUTBOUND: Bizim gönderdiklerimize gelen yanıtları alır.
        UUID eşleştirmesi ile hangi faturaya ait olduğu belirlenir.
        Yanıt kodu: 1305 = Kabul, 1310 = Red (constants.py'de tanımlı)
        """
        from ..services.sovos_invoice_service import SovosInvoiceService
        svc = SovosInvoiceService(company)

        # Sovos'tan bekleyen tüm yanıtları al
        responses = svc.get_inv_responses_outbound()

        for resp in responses:
            uuid = resp.get('uuid')
            if not uuid:
                continue

            # UUID ile Odoo'daki faturayı bul
            move = self.env['account.move'].with_company(company).search([
                ('x_sovos_uuid', '=', uuid)
            ], limit=1)

            if move:
                # İlgili durum kodunu işle (1305 veya 1310)
                move._process_gib_status(resp.get('status_code'))

    # ── 8 Gün Yanıt Süresi Uyarısı (Günlük) ──────────────────────────────

    @api.model
    def cron_check_8day_warnings(self):
        """
        Cron entry point — 8 günlük TICARIFATURA yanıt süresi uyarısı.
        Süresi dolmak üzere olan faturalar için chatter'a uyarı notu eklenir.
        ir_cron_data.xml'de günlük çalışır.

        GİB Kuralı: TICARIFATURA gönderildiğinde alıcının 8 gün içinde
        yanıt vermesi gerekir. Süre dolarsa fatura hukuki olarak geçerli sayılır
        ancak sistem üzerinde takip kaybı oluşabilir.
        """
        self._cron_run_for_all_companies('_check_8day_for_company')

    def _check_8day_for_company(self, company):
        """
        TICARIFATURA'larda 8 günlük süresinin dolmasına 1 gün kalan faturaları bulur
        ve chatter'a uyarı mesajı ekler.

        Neden 'tomorrow' (yarın) ile karşılaştırma?
            Bugün son gün olan faturalar için yarın çok geç olur.
            1 gün önceden uyararak hesap yöneticisine müdahale şansı verilir.

        Not: x_show_8day_warning alanı store=False (computed) olduğundan
        domain filtresinde kullanılamaz; burada manuel tarih hesabı yapılır.
        """
        tomorrow = date.today() + timedelta(days=1)

        # Yanıt beklenen ve süresi yaklaşan TICARIFATURA'ları bul
        expiring = self.env['account.move'].with_company(company).search([
            ('x_inv_response_status', '=', 'beklemede'),
            ('x_inv_response_deadline', '<=', tomorrow),  # Yarın veya daha önce doluyor
            ('x_efatura_scenario', '=', 'TICARIFATURA'),
        ])

        for move in expiring:
            _logger.warning(
                '8 gün uyarısı: %s (son gün: %s)',
                move.name,
                move.x_inv_response_deadline
            )
            # Fatura chatter'ına (log) uyarı notu ekle
            # message_post: mail.thread mixin'den gelir (account.move bunu inherit eder)
            move.message_post(
                body=_('⚠ TICARIFATURA yanıt süresi dolmak üzere! Son gün: %s') % move.x_inv_response_deadline,
                subtype_id=self.env.ref('mail.mt_note').id,  # mt_note = iç not (harici gönderilmez)
            )

    # ── VKN Cache Güncelleme (Günlük) ─────────────────────────────────────

    @api.model
    def cron_refresh_vkn_cache(self):
        """
        Cron entry point — eski VKN cache'lerini yeniler.
        30 günden eski veya hiç güncellenmemiş partner VKN bilgilerini Sovos'tan sorgular.
        ir_cron_data.xml'de günlük çalışır.

        Neden toplu yenileme?
            Fatura gönderimi sırasında bireysel yenileme de yapılır (res_partner.py).
            Bu cron ise sadece müşteri olan ve VKN'i olan tüm partnerleri günlük tarar.
            Böylece fatura anında gecikme yaşanmadan cache her zaman taze olur.
        """
        self._cron_run_for_all_companies('_refresh_vkn_for_company')

    def _refresh_vkn_for_company(self, company):
        """
        Tek şirket için eski/eksik VKN cache'lerini Sovos'tan yeniler.

        Filtre mantığı:
          - x_efatura_type_updated < stale_date VEYA güncelleme tarihi hiç yok
          - VKN girilmiş olmalı (vat != False)
          - Müşteri olmalı (customer_rank > 0) — tedarikçileri yenilemeye gerek yok

        NOT: Bu işlem çok sayıda Sovos API çağrısı yapabilir.
        Büyük partner listelerinde Sovos rate limit'ine dikkat edilmelidir.
        """
        stale_date = date.today() - timedelta(days=30)  # 30 gün öncesi

        # | → Odoo domain'de OR operatörü (ön ek notasyonu)
        partners = self.env['res.partner'].search([
            '|',
            ('x_efatura_type_updated', '<', stale_date),   # 30+ gün önce güncellendi
            ('x_efatura_type_updated', '=', False),         # Hiç güncellenmemiş
            ('vat', '!=', False),                            # VKN girilmiş olmalı
            ('customer_rank', '>', 0),                       # Müşteri olmalı
        ])

        for partner in partners:
            # Her partner için Sovos'tan VKN sorgusu yap ve cache güncelle
            partner.refresh_efatura_type(company)
