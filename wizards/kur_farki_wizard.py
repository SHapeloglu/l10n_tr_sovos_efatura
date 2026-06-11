# -*- coding: utf-8 -*-
"""
kur_farki_wizard.py — Kur Farkı Faturası Sihirbazı
====================================================
Dövizli TICARIFATURA veya e-Arşiv faturalar için kur farkı faturası oluşturur.

Ne zaman kullanılır?
    Dövizli bir fatura kesildi; ödeme günü ile fatura tarihi arasında kur farkı oluştu.
    VUK md.280 gereği kur farkı faturası ile bu fark belgelenir.

Çalışma mantığı:
    Orijinal faturayı kopyalar (copy()), e-Fatura alanlarını sıfırlar,
    satırları temizler ve tek kalemlik kur farkı satırı ekler.
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
          2. Orijinal faturayı kopyala (copy())
          3. Kopyada e-Fatura alanlarını sıfırla
          4. Tüm satırları temizle → tek kur farkı satırı ekle
          5. Oluşturulan faturayı form view'da aç

        copy() neden kullanılıyor?
            Odoo'nun copy() metodu fatura başlık bilgilerini (partner, döviz, dergi vb.)
            kopyalar. Biz sadece satırları ve e-Fatura alanlarını değiştiriyoruz.
            Bu sayede müşteri, tarih gibi alanları manuel doldurmak zorunda kalmıyoruz.
        """
        self.ensure_one()
        original = self.original_invoice_id

        # Kur farkı faturası sadece gönderilmiş veya kabul edilmiş faturalar için
        if original.x_efatura_status not in ('accepted', 'sent'):
            raise UserError(_(
                'Kur farkı faturası sadece gönderilmiş/kabul edilmiş faturalar için oluşturulabilir.'
            ))

        # Orijinal faturayı kopyala; bazı alanları override et
        new_invoice = original.copy({
            'invoice_date':          self.kur_farki_date,
            'x_kur_farki':           True,     # "Kur farkı faturası" işareti
            'x_efatura_status':      'draft',  # Yeni fatura taslaktan başlar
            'x_sovos_uuid':          False,    # Yeni UUID atanacak (gönderimde)
            'x_sovos_envelope_uuid': False,
            'x_reserved_number':     False,    # Yeni numara alınacak (gönderimde)
            'x_number_status':       False,
            # (5, 0, 0): Tüm satırları sil
            # ORM komutları: (0,0,vals)=ekle, (1,id,vals)=güncelle, (2,id)=sil, (5,0,0)=hepsini sil
            'invoice_line_ids':      [(5, 0, 0)],
        })

        # Kur farkı satırını ekle
        new_invoice.write({
            'invoice_line_ids': [(0, 0, {
                # (0, 0, vals): Yeni satır ekle
                'name':       self.description or 'Kur Farkı — %s' % original.name,
                'quantity':   1,
                'price_unit': self.kur_farki_amount,
                # Varsayılan muhasebe hesabı: journal'ın default hesabı
                # Kullanıcı faturayı düzenlerken değiştirebilir
                'account_id': new_invoice.journal_id.default_account_id.id,
            })]
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
