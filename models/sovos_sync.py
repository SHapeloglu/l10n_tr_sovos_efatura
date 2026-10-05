# -*- coding: utf-8 -*-
"""
sovos_sync.py — Sovos Arka Plan Görevleri (Cron İşleri)
=========================================================
Tüm cron görevlerini içerir.

MADDE 5 GÜNCELLEMESİ — _sync_incoming_for_company() artık:
  FAZ 1: Partner VKN kesin eşleme + fuzzy match
  FAZ 2: UBL XML tam parse (satır detayları dahil)
  FAZ 2: Öğrenen tablo ile ürün eşleme
  FAZ 3: difflib benzerlik + kural motoru
  FAZ 3: Düşük güvenli eşlemeler → bekletme kuyruğu (x_efatura_match_status)
  FAZ 3: Toplu onay wizard'ı ile kullanıcı onayı
"""
import base64
import logging
from datetime import date, timedelta

from odoo import models, api, fields, _

_logger = logging.getLogger(__name__)


class SovosSync(models.Model):
    _name = 'sovos.sync'
    _description = 'Sovos Senkronizasyon Görevleri'

    # ── Ortak Yardımcılar ─────────────────────────────────────────────────

    @api.model
    def _cron_run_for_all_companies(self, task_fn_name):
        """Tüm şirketler için belirtilen görevi çalıştırır."""
        companies = self.env['res.company'].search([
            ('x_sovos_invoice_user', '!=', False)
        ])
        task_fn = getattr(self, task_fn_name)
        for company in companies:
            try:
                task_fn(company)
            except Exception as e:
                _logger.error('[%s] %s hatası: %s', company.name, task_fn_name, e)
                self._notify_admin(company, task_fn_name, str(e))
                continue

    def _notify_admin(self, company, task_name, error_msg):
        """Cron hatalarında admin bildirim gönderir."""
        try:
            admin = self.env.ref('base.user_admin')
            self.env['mail.message'].create({
                'model': 'res.company',
                'res_id': company.id,
                'message_type': 'comment',
                'subtype_id': self.env.ref('mail.mt_note').id,
                'body': '<p><strong>⚠ e-Fatura Cron Hatası — %s</strong><br/>%s: %s</p>' % (
                    company.name, task_name, error_msg
                ),
                'partner_ids': [(4, admin.partner_id.id)],
                'author_id': self.env.ref('base.user_root').partner_id.id,
            })
            if company.x_sovos_admin_email:
                self.env['mail.mail'].create({
                    'subject': '[Odoo e-Fatura] Cron Hatası — %s' % company.name,
                    'body_html': '<p>%s cron görevi başarısız: %s</p>' % (task_name, error_msg),
                    'email_to': company.x_sovos_admin_email,
                }).send()
        except Exception as e:
            _logger.error('Admin bildirimi gönderilemedi: %s', e)

    # ══════════════════════════════════════════════════════════════════════
    # MADDE 5: Gelen Fatura Senkronizasyonu (15 dk)
    # FAZ 1 + 2 + 3 tam implementasyon
    # ══════════════════════════════════════════════════════════════════════

    @api.model
    def cron_sync_incoming_invoices(self):
        """Cron entry point — gelen faturaları senkronize eder (15 dk)."""
        self._cron_run_for_all_companies('_sync_incoming_for_company')

    def _sync_incoming_for_company(self, company):
        """
        FAZ 1 + 2 + 3: Gelen faturaları Sovos'tan çek, parse et, eşle, kaydet.

        Akış:
          1. Sovos'tan gelen fatura listesini al
          2. Her fatura için UUID duplikasyon kontrolü
          3. UBL XML'ini Sovos'tan tam çek (FAZ 2)
          4. parse et (UblParser)
          5. Partner eşle (FAZ 1 + FAZ 3 fuzzy)
          6. Fatura başlığı oluştur
          7. Satırları eşle ve oluştur (FAZ 2 + FAZ 3)
          8. Düşük güvenli satırlar → bekletme kuyruğu (FAZ 3)
        """
        from ..services.sovos_invoice_service import SovosInvoiceService
        from ..services.ubl_parser import UblParser
        from ..services.incoming_matcher import IncomingMatcher

        svc     = SovosInvoiceService(company)
        parser  = UblParser()
        matcher = IncomingMatcher(self.env)

        AccountMove = self.env['account.move'].with_company(company)

        # 1. Gelen fatura listesi
        invoice_list = svc.get_inbound_list()

        for inv_header in invoice_list:
            uuid = inv_header.get('uuid')
            if not uuid:
                continue

            # 2. Duplikasyon kontrolü
            if AccountMove.search([
                ('x_sovos_uuid', '=', uuid),
                ('move_type', '=', 'in_invoice'),
            ], limit=1):
                continue  # Zaten var

            try:
                self._process_single_incoming(
                    uuid, inv_header, company, svc, parser, matcher, AccountMove
                )
            except Exception as e:
                _logger.error('Gelen fatura işlenemedi (UUID=%s): %s', uuid, e)
                continue  # Diğer faturalar etkilenmesin

    def _process_single_incoming(self, uuid, inv_header, company, svc, parser, matcher, AccountMove):
        """Tek bir gelen faturayı işle."""

        # 3. UBL XML'ini Sovos'tan tam çek (FAZ 2)
        try:
            xml_bytes = svc.get_invoice_ubl(uuid)
        except Exception as e:
            _logger.warning('UBL çekilemedi (UUID=%s): %s — başlık bilgisi kullanılır', uuid, e)
            xml_bytes = None

        # 4. Parse et
        parsed = None
        if xml_bytes:
            try:
                parsed = parser.parse(xml_bytes)
            except Exception as e:
                _logger.warning('UBL parse hatası (UUID=%s): %s — başlık bilgisi kullanılır', uuid, e)

        # Parsed yoksa başlık verisini kullan (geriye dönük uyumluluk)
        sender_vkn  = (parsed or inv_header).get('sender_vkn', '') or inv_header.get('sender_vkn', '')
        sender_name = (parsed or {}).get('sender_name', '')
        inv_date    = (parsed or inv_header).get('invoice_date') or inv_header.get('invoice_date')

        # 5. Partner eşle (FAZ 1 + FAZ 3)
        partner, p_confidence, p_source = matcher.find_partner(sender_vkn, sender_name)

        # Eşleme durumu belirleme
        # Yüksek güven → matched, Orta → review, Düşük/Yok → pending
        if p_confidence >= 0.85 and parsed:
            match_status = 'matched_auto'
        elif p_confidence >= 0.60:
            match_status = 'review'
        else:
            match_status = 'pending'

        # 6. Fatura başlığı oluştur
        move_vals = {
            'move_type':           'in_invoice',
            'partner_id':          partner.id if partner else False,
            'invoice_date':        inv_date,
            'currency_id':         self._find_currency(parsed, company),
            'x_sovos_uuid':        uuid,
            'x_efatura_status':    'accepted',
            'x_efatura_type':      'efatura',
            'x_efatura_match_status': match_status,
        }

        # Notları müşteri notuna ekle
        if parsed and parsed.get('notes'):
            move_vals['narration'] = '\n'.join(parsed['notes'])

        move = AccountMove.create(move_vals)

        # 7. Satırları oluştur (FAZ 2 + FAZ 3) — sadece UBL parse başarılıysa
        if parsed and parsed.get('lines'):
            has_unmatched = self._create_invoice_lines(
                move, parsed['lines'], partner, company, matcher
            )
            # 8. Eşleşemeyen satır varsa bekletme kuyruğuna al (FAZ 3)
            if has_unmatched and match_status not in ('pending',):
                move.write({'x_efatura_match_status': 'review'})

        _logger.info(
            'Gelen fatura oluşturuldu: UUID=%s partner=%s status=%s satır=%d',
            uuid,
            partner.name if partner else 'BULUNAMADI',
            match_status,
            len(parsed['lines']) if parsed else 0,
        )

    def _create_invoice_lines(self, move, lines, partner, company, matcher):
        """
        Fatura kalemlerini oluşturur.
        Returns: bool — eşleşemeyen satır var mı?
        """
        has_unmatched = False
        supplier_id = partner.id if partner else False

        for line_data in lines:
            description = line_data.get('description', '')
            ubl_code    = line_data.get('ubl_code', '')
            quantity    = line_data.get('quantity', 1.0)
            unit_price  = line_data.get('unit_price', 0.0)
            tax_percent = line_data.get('tax_percent', 0.0)
            uom_code    = line_data.get('uom_code', 'C62')

            # Ürün eşle (FAZ 2 + FAZ 3)
            product_match = matcher.find_product(supplier_id, description, ubl_code)
            product  = product_match.get('product')
            account  = product_match.get('account')
            tax_rec  = product_match.get('tax_ids')
            uom_rec  = product_match.get('uom')
            conf     = product_match.get('confidence', 0.0)
            source   = product_match.get('source', 'none')

            # Vergi bul
            if not tax_rec:
                tax_rec = matcher.find_tax(tax_percent, company)

            # Birim bul
            if not uom_rec:
                uom_rec = matcher.find_uom(uom_code)

            # Hesap bul (ürün eşleşemediyse genel gider)
            if not account and not product:
                account = matcher.find_expense_account(company)
                has_unmatched = True

            # Satır oluştur
            line_vals = {
                'move_id':     move.id,
                'name':        description or _('e-Fatura Kalemi'),
                'quantity':    quantity,
                'price_unit':  unit_price,
            }
            if product:
                line_vals['product_id'] = product.id
            if account:
                line_vals['account_id'] = account.id
            if tax_rec:
                tax_list = tax_rec if hasattr(tax_rec, '__iter__') else [tax_rec]
                line_vals['tax_ids'] = [(6, 0, [t.id for t in tax_list if t])]
            if uom_rec:
                line_vals['product_uom_id'] = uom_rec.id

            # Eşleme meta bilgisini nota ekle (FAZ 3 — kullanıcı görebilsin)
            if conf < 1.0 or source not in ('learned_mapping', 'ubl_code'):
                note = _('e-Fatura: %s | Eşleme: %s (%.0f%%)') % (description, source, conf * 100)
                line_vals['name'] = ('%s\n[%s]' % (description, note)) if conf < MATCH_AUTO_THRESHOLD else description

            self.env['account.move.line'].create(line_vals)

        return has_unmatched

    def _find_currency(self, parsed, company):
        """UBL'deki para birimi koduna göre Odoo currency bul."""
        if not parsed:
            return company.currency_id.id
        currency_code = parsed.get('currency', 'TRY')
        currency = self.env['res.currency'].search(
            [('name', '=', currency_code)], limit=1
        )
        return currency.id if currency else company.currency_id.id

    # ── e-Fatura GİB Durum Takibi (30 dk) ────────────────────────────────

    @api.model
    def cron_sync_efatura_status(self):
        """e-Fatura GİB durum takibi (30 dk)."""
        self._cron_run_for_all_companies('_sync_efatura_status_for_company')

    def _sync_efatura_status_for_company(self, company):
        from ..services.sovos_invoice_service import SovosInvoiceService
        from datetime import datetime, timedelta
        svc = SovosInvoiceService(company)

        # x_gib_admin_notified=True olan faturalar (1215 durumu) 4 saatte bir sorgulanır.
        # Neden: 1215 alan fatura 'sent' kalır (cron takip etsin diye — DÜZELTME #1).
        # Her 30 dakikada sorgulamak Sovos rate-limit riskini artırır (SSS S5).
        # 4 saatlik pencere: write_date < (şimdi - 4 saat) koşuluyla sağlanır;
        # cron son 4 saatte sorguladıysa write_date yenilenir, tekrar gelene kadar atlanır.
        threshold_1215 = datetime.now() - timedelta(hours=4)

        pending = self.env['account.move'].with_company(company).search([
            ('x_efatura_status', 'in', ('sent', 'sending')),
            ('x_efatura_type', '=', 'efatura'),
            ('x_sovos_envelope_uuid', '!=', False),
            '|',
            ('x_gib_admin_notified', '=', False),        # Normal faturalar: her 30 dk
            ('write_date', '<', threshold_1215),          # 1215 faturalar: 4 saatte bir
        ])
        for move in pending:
            try:
                status_code, status_msg = svc.get_envelope_status(move.x_sovos_envelope_uuid)
                move._process_gib_status(status_code, status_msg)
            except Exception as e:
                _logger.warning('Durum sorgusu başarısız (%s): %s', move.x_sovos_uuid, e)

    # ── e-Arşiv Durum Takibi (30 dk) ─────────────────────────────────────

    @api.model
    def cron_sync_earsiv_status(self):
        """e-Arşiv durum takibi (30 dk)."""
        self._cron_run_for_all_companies('_sync_earsiv_status_for_company')

    def _sync_earsiv_status_for_company(self, company):
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

    # ── TICARIFATURA KABUL/RED (1 saat) ──────────────────────────────────

    @api.model
    def cron_sync_inv_responses(self):
        """TICARIFATURA ApplicationResponse takibi (1 saat)."""
        self._cron_run_for_all_companies('_sync_inv_responses_for_company')

    def _sync_inv_responses_for_company(self, company):
        from ..services.sovos_invoice_service import SovosInvoiceService
        svc = SovosInvoiceService(company)
        responses = svc.get_inv_responses_outbound()
        for resp in responses:
            uuid = resp.get('uuid')
            if not uuid:
                continue
            move = self.env['account.move'].with_company(company).search(
                [('x_sovos_uuid', '=', uuid)], limit=1
            )
            if move:
                move._process_gib_status(resp.get('status_code'))

    # ── 8 Gün Uyarısı (Günlük) ───────────────────────────────────────────

    @api.model
    def cron_check_8day_warnings(self):
        """8 günlük TICARIFATURA yanıt süresi uyarısı (günlük)."""
        self._cron_run_for_all_companies('_check_8day_for_company')

    def _check_8day_for_company(self, company):
        tomorrow = date.today() + timedelta(days=1)
        expiring = self.env['account.move'].with_company(company).search([
            ('x_inv_response_status', '=', 'beklemede'),
            ('x_inv_response_deadline', '<=', tomorrow),
            ('x_efatura_scenario', '=', 'TICARIFATURA'),
        ])
        for move in expiring:
            _logger.warning('8 gün uyarısı: %s (son gün: %s)', move.name, move.x_inv_response_deadline)
            move.message_post(
                body=_('⚠ TICARIFATURA yanıt süresi dolmak üzere! Son gün: %s') % move.x_inv_response_deadline,
                subtype_id=self.env.ref('mail.mt_note').id,
            )

    # ── VKN Cache Güncelleme (Günlük) ────────────────────────────────────

    @api.model
    def cron_refresh_vkn_cache(self):
        """Eski VKN cache'lerini yeniler (günlük)."""
        self._cron_run_for_all_companies('_refresh_vkn_for_company')

    def _refresh_vkn_for_company(self, company):
        stale_date = date.today() - timedelta(days=30)
        partners = self.env['res.partner'].search([
            '|',
            ('x_efatura_type_updated', '<', stale_date),
            ('x_efatura_type_updated', '=', False),
            ('vat', '!=', False),
            ('customer_rank', '>', 0),
        ])
        for partner in partners:
            partner.refresh_efatura_type(company)


# Sabit: otomatik eşleme eşiği (incoming_matcher.py ile tutarlı)
MATCH_AUTO_THRESHOLD = 0.85
