# -*- coding: utf-8 -*-
{
    'name': 'TR Sovos e-Fatura / e-Arşiv Entegrasyonu',
    'version': '18.0.6.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'Odoo 18 Community × Sovos GİB e-Fatura & e-Arşiv entegrasyonu (v6 Final)',
    'description': """
        Sovos özel entegratörü üzerinden GİB e-Fatura ve e-Arşiv gönderimi.
        - XSD + Schematron validasyon
        - Atomik fatura numarası (çakışma sıfır)
        - Toplu gönderim + rate limit koruması
        - VKN cache + akıllı güncelleme
        - Tam GİB durum kodu yönetimi
        - Cron başarısızlık bildirimi
        - e-Fatura dashboard
    """,
    'author': 'Geliştirici',
    'depends': ['account', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'views/res_company_views.xml',
        'views/res_partner_views.xml',
        'views/account_move_views.xml',
        'views/account_move_list_views.xml',
        'wizards/resend_invoice_wizard_views.xml',
        'wizards/cancel_invoice_wizard_views.xml',
        'wizards/kur_farki_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
