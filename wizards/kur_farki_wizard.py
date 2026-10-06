# -*- coding: utf-8 -*-
"""
kur_farki_wizard.py — Kur Farkı Faturası Sihirbazı
====================================================
Dövizli TICARIFATURA veya e-Arşiv faturalar için kur farkı faturası oluşturur.

Ne zaman kullanılır?
    Dövizli bir fatura kesildi; ödeme günü ile fatura tarihi arasında kur farkı oluştu.
    VUK md.280 gereği kur farkı faturası ile bu fark belgelenir.

Çalışma mantığı:
    Orijinal faturanın başlık bilgileriyle (müşteri, döviz, dergi, senaryo)
    create() ile yeni taslak fatura açar ve tek kalemlik kur farkı satırı ekler.
    Oluşturulan fatura taslak olarak açılır; kullanıcı inceleyip gönderir.

Limitasyon:
    KDV hesaplaması otomatik yapılmıyor; kullanıcı fatura kalemini düzenleyerek
    doğru KDV oranını seçmelidir.
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class KurFarkiWizard(models.TransientModel):
    """
    TransientModel: Geçici model; wizard kapandıktan sonra DB'den silinir.
    """
    _name = 'sovos.kur.farki.wizard'
    _description = 'Kur Farkı Faturası Sihirbazı'

    original_invoice_id = fields.Many2one(
        'account.move',
        string='Orijinal Fatura',
        required=True,
        # action_open_kur_farki_wizard context'inden: {'default_original_invoice_id': self.id}
    )
    kur_farki_amount = fields.Float(
        string='Kur Farkı Tutarı (TRY)',
        required=True,
        # Negatif değer girilirse fatura tutarı negatif olur → kontrol eklenebilir
    )
    kur_farki_date = fields.Date(
        string='Kur Farkı Tarihi',
        required=True,
        default=fields.Date.today,  # Varsayılan: bugün
        # Genellikle ödeme tarihi kullanılır; kullanıcı değiştirebilir
    )
    description = fields.Text(
        string='Açıklama',
        default='Kur farkı faturası',
        # Fatura kalemine yazılacak açıklama; orijinal fatura numarası ekleniyor
    )

    def action_create_kur_farki(self):
        """
        Kur farkı faturasını oluşturur ve form view'da açar.

        Akış:
          1. Uygunluk kontrolü (orijinal fatura gönderilmiş/kabul edilmiş mi?)
          2. Orijinalin başlık bilgileriyle (müşteri, döviz, dergi, senaryo)
             create() ile yeni taslak fatura + tek kur farkı satırı oluştur
          3. Oluşturulan faturayı form view'da aç

        Gelir hesabı orijinal faturanın ilk ürün satırından alınır; yoksa
        Odoo dergi/ürün varsayılanını kullanır.
        """
        self.ensure_one()
        original = self.original_invoice_id

        # Kur farkı faturası sadece gönderilmiş veya kabul edilmiş faturalar için
        if original.x_efatura_status not in ('accepted', 'sent'):
            raise UserError(_(
                'Kur farkı faturası sadece gönderilmiş/kabul edilmiş faturalar için oluşturulabilir.'
            ))

        # Yeni faturayı create() ile oluştur.
        # Odoo 18'de copy() + invoice_line_ids (5,0,0) ve ardından journal'ın
        # default_account_id'si ile satır eklemek güvenilir değil (satış dergisinde
        # hesap boş olabiliyor, copy() satırları/dinamik alanları taşıyor).
        # Başlık alanlarını açıkça veriyoruz; e-Fatura alanları varsayılanlardan
        # (taslak, UUID/numara boş) başlar.
        line_vals = {
            'name':       self.description or 'Kur Farkı — %s' % original.name,
            'quantity':   1,
            'price_unit': self.kur_farki_amount,
            # KDV otomatik hesaplanmıyor (bkz. Limitasyon); kullanıcı düzenler
            'tax_ids':    [(6, 0, [])],
        }
        income_account = original.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product')[:1].account_id
        if income_account:
            line_vals['account_id'] = income_account.id

        new_invoice = self.env['account.move'].create({
            'move_type':          original.move_type,
            'partner_id':         original.partner_id.id,
            'currency_id':        original.currency_id.id,
            'journal_id':         original.journal_id.id,
            'company_id':         original.company_id.id,
            'invoice_date':       self.kur_farki_date,
            'x_kur_farki':        True,     # "Kur farkı faturası" işareti
            'x_efatura_scenario': original.x_efatura_scenario,
            'invoice_line_ids':   [(0, 0, line_vals)],
        })

        # Oluşturulan faturayı form view'da aç (kullanıcı inceleyip gönderecek)
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Kur Farkı Faturası'),
            'res_model': 'account.move',
            'res_id':    new_invoice.id,
            'view_mode': 'form',
            'target':    'current',  # Mevcut pencerede aç (new = popup)
        }
