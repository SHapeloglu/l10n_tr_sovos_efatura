# -*- coding: utf-8 -*-
"""
cancel_invoice_wizard.py — İptal Sihirbazı
===========================================
Fatura türüne ve durumuna göre doğru iptal akışını yürütür:

  e-Arşiv     → Sovos CancelInvoice() API — GİB portala gitme yok
  TEMELFATURA → GİB portal linki + checkbox onayı zorunlu
  TICARIFATURA→ iptal matrisi kontrolü (Spec Bölüm 15.2)

TICARIFATURA İptal Matrisi (Spec Bölüm 15.2):
  GİB'e Gönderilecek / Teknik Hata          → İptal edilebilir
  Gönderildi — yanıt bekleniyor (sent)      → HAYIR — karşılıklı mutabakat
  Kabul Edildi                               → HAYIR
  Reddedildi                                 → Yeni fatura kes
  8 gün geçmiş                               → HAYIR — hukuki uyarı
"""
import logging
from datetime import date

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CancelInvoiceWizard(models.TransientModel):
    _name = 'sovos.cancel.invoice.wizard'
    _description = 'e-Fatura / e-Arşiv İptal Sihirbazı'

    invoice_id = fields.Many2one('account.move', string='Fatura', required=True)
    cancel_reason = fields.Text(string='İptal Gerekçesi', required=True)
    efatura_type = fields.Char(
        related='invoice_id.x_efatura_type', readonly=True,
    )
    efatura_scenario = fields.Selection(
        related='invoice_id.x_efatura_scenario', readonly=True,
    )
    # TEMELFATURA için GİB portal onayı
    gib_portal_confirmed = fields.Boolean(
        string='GİB Portalında iptali tamamladım',
        default=False,
    )
    show_gib_portal_link = fields.Boolean(compute='_compute_show_gib_portal')

    @api.depends('efatura_scenario')
    def _compute_show_gib_portal(self):
        for rec in self:
            rec.show_gib_portal_link = rec.efatura_scenario == 'TEMELFATURA'

    def action_cancel(self):
        self.ensure_one()
        invoice = self.invoice_id
        company = invoice.company_id

        # TICARIFATURA iptal matrisi kontrolü — e-Arşiv ve TEMELFATURA'dan önce
        if invoice.x_efatura_scenario == 'TICARIFATURA':
            self._check_ticarifatura_cancel_eligibility(invoice)

        # e-Arşiv → Sovos API ile iptal
        if invoice.x_efatura_type == 'earsiv':
            self._cancel_earsiv(invoice, company)

        # TEMELFATURA → GİB portal onayı zorunlu
        elif invoice.x_efatura_scenario == 'TEMELFATURA':
            if not self.gib_portal_confirmed:
                raise UserError(_(
                    'TEMELFATURA iptali için önce GİB portalında iptali tamamlayın, '
                    'ardından onay kutucuğunu işaretleyin.'
                ))
            invoice.write({'x_efatura_status': 'cancelled'})
            _logger.info('TEMELFATURA iptali onaylandı (portal): %s', invoice.name)

        # TICARIFATURA veya diğer — matris kontrolü geçtiyse iptal
        else:
            invoice.write({'x_efatura_status': 'cancelled'})

        # Odoo faturasını iptal et (muhasebe fişini de geri alır)
        # Sıra: Sovos/API işlemi bitti → Odoo iptal
        invoice.button_cancel()
        return {'type': 'ir.actions.act_window_close'}

    def _check_ticarifatura_cancel_eligibility(self, invoice):
        """
        Spec Bölüm 15.2 TICARIFATURA İptal Matrisi:

        DÜZELTME #3: 'sent' durumu artık bloklanıyor.
        Alıcıya gönderildi ama henüz yanıt bekleniyor → karşılıklı mutabakat gerekli.
        Önceki kodda bu kontrol eksikti; fatura 'sent' durumdayken iptal edilebiliyordu.
        """
        status   = invoice.x_efatura_status
        deadline = invoice.x_inv_response_deadline

        if status == 'accepted':
            raise UserError(_('Kabul edilmiş TICARIFATURA iptal edilemez.'))

        if status == 'rejected':
            raise UserError(_(
                'Reddedilmiş fatura zaten iptal sürecindedir. '
                'Yeni fatura kesin.'
            ))

        # DÜZELTME #3: 'sent' = alıcıya iletildi, yanıt bekleniyor
        # Spec: "Alıcıya Gönderildi (8 gün dolmamış) → Hayır — karşılıklı mutabakat"
        if status == 'sent':
            raise UserError(_(
                'Bu fatura alıcıya iletilmiş ve yanıt bekleniyor (8 gün içinde).\n\n'
                'TICARIFATURA bu aşamada tek taraflı iptal edilemez.\n'
                'Alıcı ile mutabık kalarak karşılıklı iptal sürecini başlatın.'
            ))

        if deadline and date.today() > deadline:
            raise UserError(_(
                '⚠ Hukuki Uyarı: 8 günlük TICARIFATURA yanıt süresi dolmuştur.\n'
                'Bu fatura sistem tarafından bloke edilmiştir.\n'
                'Hukuki danışmanınız ile iletişime geçin.'
            ))

    def _cancel_earsiv(self, invoice, company):
        """e-Arşiv CancelInvoice() API çağrısı — GİB portala gitme gerekmez."""
        from ..services.sovos_archive_service import SovosArchiveService
        svc = SovosArchiveService(company)
        try:
            success = svc.cancel_invoice(invoice.x_sovos_uuid, self.cancel_reason)
            if success:
                invoice.write({'x_efatura_status': 'cancelled'})
                _logger.info('e-Arşiv iptali başarılı: %s', invoice.x_sovos_uuid)
            else:
                raise UserError(_(
                    'e-Arşiv iptal isteği reddedildi. Sovos desteğine başvurun.'
                ))
        except UserError:
            raise
        except Exception as e:
            raise UserError(_('e-Arşiv iptal hatası: %s') % str(e))
