# -*- coding: utf-8 -*-
"""
cancel_invoice_wizard.py — Fatura İptal Sihirbazı
===================================================
Fatura türüne ve GİB senaryosuna göre doğru iptal akışını yürütür.

İptal Akış Matrisi (Spec Bölüm 15.2):
  ┌─────────────────┬──────────────────────────────────────────────────┐
  │ Tür / Durum     │ İptal Yöntemi                                    │
  ├─────────────────┼──────────────────────────────────────────────────┤
  │ e-Arşiv         │ Sovos CancelInvoice() API — direkt iptal         │
  │ TEMELFATURA     │ Kullanıcı GİB portalında iptal + onay checkbox   │
  │ TICARIFATURA    │ Matris kontrolü (aşağıya bak)                    │
  └─────────────────┴──────────────────────────────────────────────────┘

TICARIFATURA İptal Matrisi (Spec Bölüm 15.2):
  Durum          │ İptal Edilebilir mi?
  ───────────────┼────────────────────────────────────────
  draft / error  │ EVET — GİB'e iletilmedi
  sent           │ HAYIR — alıcıya iletildi, yanıt bekleniyor (DÜZELTME #3)
  accepted       │ HAYIR — kabul edilmiş
  rejected       │ HAYIR — zaten reddedilmiş; yeni fatura kes
  8 gün dolmuş   │ HAYIR — hukuki süre geçmiş

DÜZELTME #3:
    Önceki versiyonda 'sent' durumundaki TICARIFATURA iptal edilebiliyordu.
    Bu hatalıydı: Alıcıya iletilmiş fatura tek taraflı iptal edilemez.
    Şimdi karşılıklı mutabakat mesajı gösterilir.
"""
import logging
from datetime import date

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CancelInvoiceWizard(models.TransientModel):
    """
    TransientModel: Geçici model; wizard kapatıldığında kayıtlar veritabanından silinir.
    Kalıcı kayıt tutmaz; sadece kullanıcı girdisi toplamak için.
    """
    _name = 'sovos.cancel.invoice.wizard'
    _description = 'e-Fatura / e-Arşiv İptal Sihirbazı'

    invoice_id = fields.Many2one(
        'account.move',
        string='Fatura',
        required=True,
        # context'ten otomatik dolar: action_open_cancel_wizard({'default_invoice_id': self.id})
    )
    cancel_reason = fields.Text(
        string='İptal Gerekçesi',
        required=True,
        # e-Arşiv iptali için Sovos API'ye gönderilir.
        # TICARIFATURA için kayıt amacıyla tutulur.
    )

    # related alanlar: invoice_id değişince otomatik güncellenir; readonly
    efatura_type = fields.Char(
        related='invoice_id.x_efatura_type',
        readonly=True,
    )
    efatura_scenario = fields.Selection(
        related='invoice_id.x_efatura_scenario',
        readonly=True,
    )

    # TEMELFATURA için GİB portal onayı zorunlu checkbox
    gib_portal_confirmed = fields.Boolean(
        string='GİB Portalında iptali tamamladım',
        default=False,
        # Kullanıcı GİB portalına gidip iptali tamamlamalı, sonra bunu işaretlemeli.
    )
    show_gib_portal_link = fields.Boolean(
        compute='_compute_show_gib_portal',
        # store=False: DB'de tutulmaz; her view açıldığında hesaplanır
    )

    @api.depends('efatura_scenario')
    def _compute_show_gib_portal(self):
        """
        TEMELFATURA ise GİB portal linkini ve onay checkbox'ını göster.
        @api.depends: efatura_scenario değiştiğinde otomatik tetiklenir.
        """
        for rec in self:
            rec.show_gib_portal_link = rec.efatura_scenario == 'TEMELFATURA'

    def action_cancel(self):
        """
        Wizard'ın ana aksiyonu — 'İptal Et' butonuna bağlı.

        Akış:
          1. TICARIFATURA → matris kontrolü (eligibility)
          2. e-Arşiv → Sovos API ile direkt iptal
          3. TEMELFATURA → portal onay kontrolü
          4. Diğer → Odoo statüsünü 'cancelled' yap
          5. Odoo faturasını iptal et (button_cancel)
        """
        self.ensure_one()
        invoice = self.invoice_id
        company = invoice.company_id

        # TICARIFATURA kontrolü her zaman önce yapılır
        if invoice.x_efatura_scenario == 'TICARIFATURA':
            self._check_ticarifatura_cancel_eligibility(invoice)

        if invoice.x_efatura_type == 'earsiv':
            # e-Arşiv: Sovos API üzerinden direkt iptal
            self._cancel_earsiv(invoice, company)

        elif invoice.x_efatura_scenario == 'TEMELFATURA':
            # TEMELFATURA: GİB portala gitme zorunlu; checkbox onayı kontrol et
            if not self.gib_portal_confirmed:
                raise UserError(_(
                    'TEMELFATURA iptali için önce GİB portalında iptali tamamlayın, '
                    'ardından onay kutucuğunu işaretleyin.'
                ))
            invoice.write({'x_efatura_status': 'cancelled'})
            _logger.info('TEMELFATURA iptali onaylandı (portal): %s', invoice.name)

        else:
            # TICARIFATURA (matris kontrolü geçti) veya diğer durumlar
            invoice.write({'x_efatura_status': 'cancelled'})

        # Odoo muhasebe kaydını iptal et
        # Sıra önemli: Sovos/GİB işlemi başarılı olduktan SONRA Odoo iptal edilir.
        # Tersi olursa Odoo iptal ama GİB'te fatura aktif kalır.
        invoice.button_cancel()

        return {'type': 'ir.actions.act_window_close'}

    def _check_ticarifatura_cancel_eligibility(self, invoice):
        """
        Spec Bölüm 15.2 — TICARIFATURA iptal uygunluk kontrolü.

        DÜZELTME #3:
            'sent' (gönderildi, yanıt bekleniyor) durumu artık bloklanıyor.
            Önceki kodda bu durum eksikti ve iptal gerçekleşebiliyordu.
            GİB kuralı: Alıcıya iletilmiş fatura tek taraflı iptal edilemez.

        Bu metod hata fırlatırsa iptal durur; fırlatmazsa devam edilir.
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

        # DÜZELTME #3: 'sent' = alıcıya iletildi; 8 gün içinde yanıt bekleniyor
        # GİB Spec: "Alıcıya Gönderildi → Hayır — karşılıklı mutabakat gerekli"
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
        """
        e-Arşiv CancelInvoice() API çağrısı ile faturayı iptal eder.

        e-Arşiv'de GİB portala gitmek gerekmez; API ile direkt iptal mümkün.
        TEMELFATURA veya TICARIFATURA'da bu yol geçerli değildir.

        Hata durumu:
            Sovos API'si başarısız dönerse UserError fırlatılır.
            Odoo'da durum değişmez (iptal yarım kalmaz).
        """
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
            raise  # Kendi oluşturduğumuz UserError'ları yukarıya ilet
        except Exception as e:
            raise UserError(_('e-Arşiv iptal hatası: %s') % str(e))
