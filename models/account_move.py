# -*- coding: utf-8 -*-
import logging
import time
from uuid import uuid4
from datetime import date, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# GİB durum kodu grupları
GIB_RETRY_SAME_UUID = {
    1101, 1103, 1110, 1111, 1120, 1130, 1131, 1132, 1133,
    1140, 1141, 1142, 1143, 1150, 1160, 1162, 1170, 1175,
    1210, 1230,
}
GIB_CANCEL_AND_NEW = {1104, 1163}
GIB_SOVOS_SUPPORT = {1161, 1171, 1172}
GIB_SUCCESS = {1300, 1305}
GIB_REJECTED = {1310}

# Kullanıcıya gösterilecek hata mesajları
GIB_USER_MESSAGES = {
    1101: _('UBL-TR formatında sorun. Tekrar Gönder butonunu kullanın.'),
    1103: _('Zorunlu alan boş. Fatura bilgilerini tamamlayın.'),
    1104: _('Fatura numarası daha önce kullanılmış. Sistem yöneticisi ile iletişime geçin.'),
    1110: _('ZIP formatı hatalı. Tekrar Gönder butonunu kullanın.'),
    1111: _('Zarf ID uzunluğu geçersiz. Tekrar Gönder butonunu kullanın.'),
    1130: _('ZIP açılamadı. Tekrar Gönder butonunu kullanın.'),
    1132: _('XML dosyası değil. Tekrar Gönder butonunu kullanın.'),
    1133: _('Dosya adı uyuşmuyor. Tekrar Gönder butonunu kullanın.'),
    1140: _('XML ayrıştırılamadı. Tekrar Gönder butonunu kullanın.'),
    1141: _('Zarf ID eksik. Tekrar Gönder butonunu kullanın.'),
    1142: _('Zarf ID ve ZIP adı uyuşmuyor. Tekrar Gönder butonunu kullanın.'),
    1143: _('Geçersiz UBL versiyonu. Tekrar Gönder butonunu kullanın.'),
    1150: _('Schematron kontrolü başarısız. Tekrar Gönder butonunu kullanın.'),
    1160: _('XML şema kontrolü başarısız. Tekrar Gönder butonunu kullanın.'),
    1161: _('İmza hatası. Sovos teknik destek ile iletişime geçin.'),
    1162: _('İmza kaydedilemedi. Tekrar Gönder butonunu kullanın.'),
    1163: _('Bu fatura zaten GİB\'te kayıtlı. İptal edip yeni fatura kesin.'),
    1170: _('Schematron uyumsuz. Tekrar Gönder butonunu kullanın.'),
    1171: _('Gönderici birim yetkisi yok. Sovos teknik destek ile iletişime geçin.'),
    1172: _('Posta kutusu yetkisi yok. Sovos teknik destek ile iletişime geçin.'),
    1175: _('İmza yetkisi kontrol edilemedi. Tekrar Gönder butonunu kullanın.'),
    1210: _('Alıcıya ulaşılamadı — iptal gerekmez. Tekrar Gönder.'),
    1215: _('GİB sistemine ulaşılamıyor. Sistem yöneticisi bilgilendirildi.'),
    1230: _('Alıcıda işlenemedi. Tekrar Gönder.'),
    1300: _('Fatura başarıyla tamamlandı.'),
    1305: _('Alıcı faturayı kabul etti.'),
    1310: _('Alıcı faturayı reddetti. İptal edip yeni fatura kesin.'),
}


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ── e-Fatura Alanları ─────────────────────────────────────────────────
    x_sovos_uuid = fields.Char(
        string='Sovos UUID', size=36, copy=False, readonly=True,
    )
    x_sovos_envelope_uuid = fields.Char(
        string='Zarf UUID', size=36, copy=False, readonly=True,
    )
    x_efatura_status = fields.Selection(
        selection=[
            ('draft', 'Taslak'),
            ('sending', 'Gönderiliyor'),
            ('sent', 'Gönderildi'),
            ('accepted', 'Kabul Edildi'),
            ('rejected', 'Reddedildi'),
            ('cancelled', 'İptal Edildi'),
            ('error', 'Hata'),
        ],
        string='e-Fatura Durumu',
        default='draft',
        copy=False,
        readonly=True,
        tracking=True,
    )
    x_efatura_type = fields.Char(
        string='e-Fatura Türü', size=10, copy=False, readonly=True,
        help='efatura / earsiv',
    )
    x_efatura_scenario = fields.Selection(
        selection=[
            ('TICARIFATURA', 'TİCARİFATURA'),
            ('TEMELFATURA', 'TEMELFATURA'),
            ('EARSIVFATURA', 'e-Arşiv Fatura'),
        ],
        string='Senaryo',
        copy=False,
    )
    x_efatura_send_date = fields.Datetime(
        string='GİB İletim Tarihi', copy=False, readonly=True,
    )
    x_efatura_error_msg = fields.Text(
        string='Hata Mesajı', copy=False, readonly=True,
    )
    x_cust_inv_id = fields.Char(
        string='Sovos CUST_INV_ID', size=50, copy=False, readonly=True,
    )
    x_inv_response_status = fields.Selection(
        selection=[
            ('beklemede', 'Beklemede'),
            ('kabul', 'Kabul Edildi'),
            ('red', 'Reddedildi'),
        ],
        string='TICARIFATURA Yanıt Durumu',
        copy=False,
        readonly=True,
    )
    x_inv_response_deadline = fields.Date(
        string='8 Gün Yanıt Süresi', copy=False, readonly=True,
    )
    x_kur_farki = fields.Boolean(
        string='Kur Farkı Faturası', default=False, copy=False,
    )
    # ── v6 Yeni Alanlar ───────────────────────────────────────────────────
    x_reserved_number = fields.Char(
        string='Rezerve Numara', size=50, copy=False, readonly=True,
    )
    x_number_status = fields.Selection(
        selection=[
            ('reserved', 'Rezerve'),
            ('confirmed', 'Onaylandı'),
            ('released', 'Serbest Bırakıldı'),
        ],
        string='Numara Durumu',
        copy=False,
        readonly=True,
    )
    x_validation_errors = fields.Text(
        string='Validasyon Hataları', copy=False, readonly=True,
        groups='base.group_system',
    )
    x_gib_status_code = fields.Integer(
        string='Son GİB Durum Kodu', copy=False, readonly=True,
    )

    # ── Hesaplanan Uyarılar ───────────────────────────────────────────────
    x_show_8day_warning = fields.Boolean(
        compute='_compute_show_8day_warning', store=False,
    )

    @api.depends('x_inv_response_deadline', 'x_inv_response_status')
    def _compute_show_8day_warning(self):
        today = date.today()
        for move in self:
            if (
                move.x_inv_response_status == 'beklemede'
                and move.x_inv_response_deadline
                and move.x_inv_response_deadline <= today + timedelta(days=1)
            ):
                move.x_show_8day_warning = True
            else:
                move.x_show_8day_warning = False

    # ═════════════════════════════════════════════════════════════════════
    # action_post() override — atomik numara + UBL validasyon + Sovos gönderim
    # ═════════════════════════════════════════════════════════════════════
    def action_post(self):
        """Satış faturası → UBL validasyon → Sovos gönderim."""
        # Sadece satış faturalarını yakala; diğerleri normal akışa gitsin
        efatura_moves = self.filtered(
            lambda m: m.move_type == 'out_invoice' and m.state == 'draft'
        )
        other_moves = self - efatura_moves

        result = super(AccountMove, other_moves).action_post() if other_moves else True

        for move in efatura_moves:
            move._efatura_post_single()

        return result

    def _efatura_post_single(self):
        """Tek fatura için e-Fatura gönderim akışı."""
        company = self.company_id
        partner = self.partner_id

        # ── Ön Kontroller ─────────────────────────────────────────────────
        self._check_prerequisites(company, partner)

        # ── VKN Cache ─────────────────────────────────────────────────────
        efatura_type = self._resolve_efatura_type(company, partner)

        # ── Senaryo Belirle ───────────────────────────────────────────────
        scenario = self._resolve_scenario(efatura_type, partner)

        # ── Önce Odoo'da POSTED durumuna al ───────────────────────────────
        super(AccountMove, self).action_post()

        # ── Atomik Numara Rezervasyonu ─────────────────────────────────────
        invoice_number = self._reserve_invoice_number(company)

        # ── UUID üret ─────────────────────────────────────────────────────
        inv_uuid = str(uuid4())

        # ── UBL-TR Üret ───────────────────────────────────────────────────
        from ..services.ubl_builder import UblBuilder
        from ..services.ubl_validator import UblValidator

        try:
            xml_bytes = UblBuilder(company).build(self, inv_uuid, invoice_number, scenario)
        except Exception as e:
            self._release_number()
            self._set_error(_('UBL üretim hatası: %s') % str(e))
            raise UserError(_('UBL üretim hatası: %s') % str(e))

        # ── XSD + Schematron Validasyon ────────────────────────────────────
        valid, layer, errors = UblValidator().validate(xml_bytes)
        if not valid:
            self._release_number()
            err_detail = errors[0] if errors else ''
            self.write({'x_validation_errors': '\n'.join(errors)})
            self._set_error(_('UBL validasyon hatası [%s]: %s') % (layer, err_detail))
            raise UserError(_('UBL validasyon hatası [%s]: %s') % (layer, err_detail))

        # ── Sovos Gönderim ─────────────────────────────────────────────────
        self.write({'x_efatura_status': 'sending'})
        try:
            if efatura_type == 'efatura':
                from ..services.sovos_invoice_service import SovosInvoiceService
                svc = SovosInvoiceService(company)
                envelope_uuid = svc.send_ubl(xml_bytes, inv_uuid, partner, scenario)
            else:
                from ..services.sovos_archive_service import SovosArchiveService
                svc = SovosArchiveService(company)
                envelope_uuid = svc.send_invoice(xml_bytes, inv_uuid, partner)

            self.write({
                'name': invoice_number,
                'x_sovos_uuid': inv_uuid,
                'x_sovos_envelope_uuid': envelope_uuid,
                'x_efatura_type': efatura_type,
                'x_efatura_scenario': scenario,
                'x_efatura_status': 'sent',
                'x_efatura_send_date': fields.Datetime.now(),
                'x_cust_inv_id': invoice_number,
                'x_number_status': 'confirmed',
                'x_efatura_error_msg': False,
                'x_validation_errors': False,
            })
            # TICARIFATURA → 8 günlük deadline başlat
            if scenario == 'TICARIFATURA':
                self.write({
                    'x_inv_response_status': 'beklemede',
                    'x_inv_response_deadline': date.today() + timedelta(days=8),
                })
            _logger.info('e-Fatura gönderildi: %s → %s', invoice_number, inv_uuid)

        except Exception as e:
            self._release_number()
            self._set_error(_('Sovos gönderim hatası: %s') % str(e))
            raise UserError(_('Sovos gönderim hatası: %s') % str(e))

    # ── Yardımcı Metodlar ─────────────────────────────────────────────────
    def _check_prerequisites(self, company, partner):
        """Temel ön kontroller."""
        if not company.x_sovos_invoice_user:
            raise UserError(_('Sovos e-Fatura kullanıcı bilgileri eksik. Ayarlar\'dan yapılandırın.'))
        if not company.x_sovos_sender_vkn:
            raise UserError(_('Şirket VKN girilmemiş.'))
        if not partner.vat:
            raise UserError(_('Müşteri VKN/TCKN girilmemiş.'))
        if not self.invoice_date:
            raise UserError(_('Fatura tarihi boş.'))

    def _resolve_efatura_type(self, company, partner):
        """VKN cache'den veya canlı sorgudan e-Fatura tipini belirle."""
        if partner.efatura_type_needs_refresh():
            _logger.info('VKN cache yenileniyor: %s', partner.vat)
            partner.refresh_efatura_type(company)
        return partner.x_efatura_type or 'earsiv'

    def _resolve_scenario(self, efatura_type, partner):
        """Senaryo belirleme — kullanıcı seçimi önce, sonra partner default."""
        if efatura_type == 'earsiv':
            return 'EARSIVFATURA'
        if self.x_efatura_scenario:
            return self.x_efatura_scenario
        return partner.x_default_scenario or 'TICARIFATURA'

    def _reserve_invoice_number(self, company):
        """Atomik numara rezervasyonu — PostgreSQL savepoint ile."""
        if not company.x_invoice_sequence_id:
            raise UserError(_('e-Fatura numara serisi tanımlanmamış.'))
        with self.env.cr.savepoint():
            invoice_number = self.env['ir.sequence'].browse(
                company.x_invoice_sequence_id.id
            ).next_by_id()
            self.write({
                'x_reserved_number': invoice_number,
                'x_number_status': 'reserved',
            })
        return invoice_number

    def _release_number(self):
        """Hata durumunda rezerve numarayı serbest bırak."""
        self.write({'x_number_status': 'released'})
        _logger.warning('Fatura numarası serbest bırakıldı: %s (boşluk logu)', self.x_reserved_number)

    def _set_error(self, msg):
        """Hata mesajını kaydet, durumu error yap."""
        self.write({
            'x_efatura_status': 'error',
            'x_efatura_error_msg': msg,
        })

    # ═════════════════════════════════════════════════════════════════════
    # Toplu Gönderim
    # ═════════════════════════════════════════════════════════════════════
    def action_send_efatura_bulk(self):
        """Seçili faturaları toplu gönderir. Liste görünümünden tetiklenir."""
        invoices = self.filtered(
            lambda m: m.move_type == 'out_invoice'
            and m.state == 'posted'
            and m.x_efatura_status in ('draft', 'error')
        )
        if not invoices:
            raise UserError(_('Gönderilebilir fatura bulunamadı.'))

        # Alıcı VKN'e göre sırala (cache avantajı)
        invoices = invoices.sorted(key=lambda m: (m.partner_id.vat or '', m.invoice_date))

        sent_count = 0
        error_list = []
        validation_error_list = []
        skip_count = 0

        for move in invoices:
            try:
                move._efatura_post_single()
                sent_count += 1
                # Rate limit: 500ms bekleme
                time.sleep(0.5)
            except UserError as e:
                err_msg = str(e)
                if 'validasyon' in err_msg.lower():
                    validation_error_list.append('%s: %s' % (move.name or move.id, err_msg))
                else:
                    error_list.append('%s: %s' % (move.name or move.id, err_msg))
            except Exception as e:
                _logger.error('Toplu gönderim beklenmeyen hata (%s): %s', move.id, e)
                error_list.append('%s: Beklenmeyen hata' % (move.name or move.id))

        # Özet rapor
        summary_lines = [_('Toplu Gönderim Sonucu:')]
        summary_lines.append(_('✅ Gönderildi: %d') % sent_count)
        if validation_error_list:
            summary_lines.append(_('⚠ Validasyon Hatası: %d') % len(validation_error_list))
        if error_list:
            summary_lines.append(_('❌ Gönderim Hatası: %d') % len(error_list))
        if skip_count:
            summary_lines.append(_('⏭ Atlandı: %d') % skip_count)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Toplu e-Fatura Gönderimi'),
                'message': '\n'.join(summary_lines),
                'type': 'success' if not error_list else 'warning',
                'sticky': True,
            },
        }

    # ═════════════════════════════════════════════════════════════════════
    # Fatura Önizleme
    # ═════════════════════════════════════════════════════════════════════
    def action_preview_efatura(self):
        """UBL-TR XML üretir ve HTML modal olarak gösterir."""
        self.ensure_one()
        company = self.company_id
        partner = self.partner_id

        efatura_type = self._resolve_efatura_type(company, partner)
        scenario = self._resolve_scenario(efatura_type, partner)

        from ..services.ubl_builder import UblBuilder
        from ..services.ubl_validator import UblValidator

        temp_uuid = str(uuid4())
        temp_number = self.name or 'ONIZLEME'

        try:
            xml_bytes = UblBuilder(company).build(self, temp_uuid, temp_number, scenario)
        except Exception as e:
            raise UserError(_('UBL üretim hatası: %s') % str(e))

        valid, layer, errors = UblValidator().validate(xml_bytes)

        # Basit HTML önizleme
        validation_html = ''
        if not valid:
            err_lines = ''.join('<li>%s</li>' % e for e in errors)
            validation_html = (
                '<div style="background:#fdd;padding:8px;border-radius:4px;">'
                '<strong>⚠ Validasyon Hatası [%s]:</strong><ul>%s</ul></div>'
            ) % (layer, err_lines)

        xml_preview = xml_bytes.decode('utf-8')[:3000] + ('...' if len(xml_bytes) > 3000 else '')
        html = (
            '<h3>e-Fatura Önizleme</h3>'
            '%s'
            '<p><strong>UUID:</strong> %s</p>'
            '<p><strong>Senaryo:</strong> %s | <strong>Tür:</strong> %s</p>'
            '<pre style="background:#f5f5f5;padding:8px;overflow:auto;max-height:400px;">'
            '%s</pre>'
        ) % (validation_html, temp_uuid, scenario, efatura_type, xml_preview)

        return {
            'type': 'ir.actions.act_url',
            'url': 'data:text/html;charset=utf-8,' + html,
            'target': 'new',
        }

    # ═════════════════════════════════════════════════════════════════════
    # PDF İndirme
    # ═════════════════════════════════════════════════════════════════════
    def action_download_efatura_pdf(self):
        """Sovos'tan fatura PDF'ini indirir ve ir.attachment olarak kaydeder."""
        self.ensure_one()
        if not self.x_sovos_uuid:
            raise UserError(_('Henüz gönderilmiş UUID yok.'))

        company = self.company_id
        if self.x_efatura_type == 'earsiv':
            from ..services.sovos_archive_service import SovosArchiveService
            svc = SovosArchiveService(company)
            pdf_bytes = svc.get_invoice_pdf(self.x_sovos_uuid)
        else:
            from ..services.sovos_invoice_service import SovosInvoiceService
            svc = SovosInvoiceService(company)
            pdf_bytes = svc.get_invoice_pdf(self.x_sovos_uuid)

        attachment = self.env['ir.attachment'].create({
            'name': '%s.pdf' % (self.name or self.x_sovos_uuid),
            'type': 'binary',
            'datas': pdf_bytes,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d?download=true' % attachment.id,
            'target': 'self',
        }

    # ═════════════════════════════════════════════════════════════════════
    # GİB Durum Kodu İşleme
    # ═════════════════════════════════════════════════════════════════════
    def _process_gib_status(self, status_code, status_message=''):
        """Cron tarafından çağrılır. GİB durum koduna göre Odoo statüsü günceller."""
        self.ensure_one()
        code = int(status_code) if status_code else 0
        user_msg = GIB_USER_MESSAGES.get(code, _('GİB kodu %d: %s') % (code, status_message))

        self.write({'x_gib_status_code': code})

        if code in GIB_SUCCESS:
            self.write({
                'x_efatura_status': 'accepted',
                'x_efatura_error_msg': False,
            })
        elif code == 1305:
            self.write({'x_inv_response_status': 'kabul'})
        elif code == 1310:
            self.write({
                'x_efatura_status': 'rejected',
                'x_inv_response_status': 'red',
                'x_efatura_error_msg': user_msg,
            })
        elif code in GIB_CANCEL_AND_NEW:
            self._set_error(user_msg)
            if code == 1104:
                # Admin bildirim
                self._notify_admin_gib_error(code, user_msg)
        elif code in GIB_SOVOS_SUPPORT:
            self._set_error(user_msg)
        elif code == 1215:
            self._set_error(user_msg)
            self._notify_admin_gib_error(code, user_msg)
        elif code in GIB_RETRY_SAME_UUID:
            self.write({
                'x_efatura_status': 'error',
                'x_efatura_error_msg': user_msg,
            })
        elif code in (1000, 1100):
            # Kuyrukta / İşleniyor — bekle
            pass

    def _notify_admin_gib_error(self, code, msg):
        """Admin kullanıcıya Odoo bildirimi gönderir."""
        try:
            admin = self.env.ref('base.user_admin')
            self.env['mail.message'].create({
                'model': self._name,
                'res_id': self.id,
                'message_type': 'comment',
                'subtype_id': self.env.ref('mail.mt_note').id,
                'body': '<p><strong>⚠ GİB Hata %d:</strong> %s<br/>Fatura: %s</p>' % (
                    code, msg, self.name or self.id
                ),
                'partner_ids': [(4, admin.partner_id.id)],
                'author_id': self.env.ref('base.user_root').partner_id.id,
            })
        except Exception as e:
            _logger.error('Admin bildirimi gönderilemedi: %s', e)
