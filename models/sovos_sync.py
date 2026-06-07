# -*- coding: utf-8 -*-
import logging
from datetime import date, timedelta

from odoo import models, api, fields, _

_logger = logging.getLogger(__name__)


class SovosSync(models.Model):
    _name = 'sovos.sync'
    _description = 'Sovos Senkronizasyon Görevleri'

    # ═════════════════════════════════════════════════════════════════════
    # Çok Şirket Döngüsü
    # ═════════════════════════════════════════════════════════════════════
    @api.model
    def _cron_run_for_all_companies(self, task_fn_name):
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
        """Cron hatasında admin kullanıcıya Odoo bildirimi."""
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
            # E-posta bildirimi
            if company.x_sovos_admin_email:
                self.env['mail.mail'].create({
                    'subject': '[Odoo e-Fatura] Cron Hatası — %s' % company.name,
                    'body_html': '<p>%s cron görevi başarısız: %s</p>' % (task_name, error_msg),
                    'email_to': company.x_sovos_admin_email,
                }).send()
        except Exception as e:
            _logger.error('Admin bildirimi gönderilemedi: %s', e)

    # ═════════════════════════════════════════════════════════════════════
    # Cron: Gelen Fatura Senkronizasyonu (15 dk)
    # ═════════════════════════════════════════════════════════════════════
    @api.model
    def cron_sync_incoming_invoices(self):
        self._cron_run_for_all_companies('_sync_incoming_for_company')

    def _sync_incoming_for_company(self, company):
        from ..services.sovos_invoice_service import SovosInvoiceService
        svc = SovosInvoiceService(company)
        invoices = svc.get_inbound_list()
        AccountMove = self.env['account.move'].with_company(company)

        for inv_data in invoices:
            uuid = inv_data.get('uuid')
            if not uuid:
                continue
            existing = AccountMove.search([
                ('x_sovos_uuid', '=', uuid),
                ('move_type', '=', 'in_invoice'),
            ], limit=1)
            if existing:
                continue

            # Partner eşleştir
            partner = self._find_partner_by_vkn(inv_data.get('sender_vkn'))

            move_vals = {
                'move_type': 'in_invoice',
                'partner_id': partner.id if partner else False,
                'invoice_date': inv_data.get('invoice_date'),
                'x_sovos_uuid': uuid,
                'x_efatura_status': 'accepted',
                'x_efatura_type': 'efatura',
            }
            move = AccountMove.create(move_vals)
            _logger.info('Gelen fatura oluşturuldu: %s (UUID: %s)', move.id, uuid)

    def _find_partner_by_vkn(self, vkn):
        if not vkn:
            return False
        return self.env['res.partner'].search([('vat', '=', vkn)], limit=1)

    # ═════════════════════════════════════════════════════════════════════
    # Cron: e-Fatura Durum Takibi (30 dk)
    # ═════════════════════════════════════════════════════════════════════
    @api.model
    def cron_sync_efatura_status(self):
        self._cron_run_for_all_companies('_sync_efatura_status_for_company')

    def _sync_efatura_status_for_company(self, company):
        from ..services.sovos_invoice_service import SovosInvoiceService
        svc = SovosInvoiceService(company)
        pending = self.env['account.move'].with_company(company).search([
            ('x_efatura_status', 'in', ('sent', 'sending')),
            ('x_efatura_type', '=', 'efatura'),
            ('x_sovos_envelope_uuid', '!=', False),
        ])
        for move in pending:
            try:
                status_code, status_msg = svc.get_envelope_status(move.x_sovos_envelope_uuid)
                move._process_gib_status(status_code, status_msg)
            except Exception as e:
                _logger.warning('Durum sorgusu başarısız (%s): %s', move.x_sovos_uuid, e)

    # ═════════════════════════════════════════════════════════════════════
    # Cron: e-Arşiv Durum Takibi (30 dk) — AYRI
    # ═════════════════════════════════════════════════════════════════════
    @api.model
    def cron_sync_earsiv_status(self):
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

    # ═════════════════════════════════════════════════════════════════════
    # Cron: TICARIFATURA KABUL/RED Takibi (1 saat)
    # ═════════════════════════════════════════════════════════════════════
    @api.model
    def cron_sync_inv_responses(self):
        self._cron_run_for_all_companies('_sync_inv_responses_for_company')

    def _sync_inv_responses_for_company(self, company):
        from ..services.sovos_invoice_service import SovosInvoiceService
        svc = SovosInvoiceService(company)
        responses = svc.get_inv_responses_outbound()
        for resp in responses:
            uuid = resp.get('uuid')
            if not uuid:
                continue
            move = self.env['account.move'].with_company(company).search([
                ('x_sovos_uuid', '=', uuid)
            ], limit=1)
            if move:
                status_code = resp.get('status_code')
                move._process_gib_status(status_code)

    # ═════════════════════════════════════════════════════════════════════
    # Cron: 8 Gün Uyarısı (Günlük)
    # ═════════════════════════════════════════════════════════════════════
    @api.model
    def cron_check_8day_warnings(self):
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
            # Chatter mesajı
            move.message_post(
                body=_('⚠ TICARIFATURA yanıt süresi dolmak üzere! Son gün: %s') % move.x_inv_response_deadline,
                subtype_id=self.env.ref('mail.mt_note').id,
            )

    # ═════════════════════════════════════════════════════════════════════
    # Cron: VKN Cache Güncelleme (Günlük)
    # ═════════════════════════════════════════════════════════════════════
    @api.model
    def cron_refresh_vkn_cache(self):
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
