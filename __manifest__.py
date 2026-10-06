# -*- coding: utf-8 -*-
{
    'name': 'TR Sovos e-Fatura / e-Arşiv Entegrasyonu',
    'version': '18.0.8.0.6',
    'category': 'Accounting/Localizations',
    'summary': 'Odoo 18 Community × Sovos GİB e-Fatura & e-Arşiv entegrasyonu (v8)',
    'description': """
        Sovos özel entegratörü üzerinden GİB e-Fatura ve e-Arşiv gönderimi.
        - XSD (lxml) + GİB iş kuralları (XPath) validasyon
        - Atomik fatura numarası (çakışma sıfır)
        - Toplu gönderim + rate limit koruması
        - VKN cache + otomatik yenileme (30 gün)
        - Tam GİB durum kodu yönetimi (tüm Sovos PDF kodları)
        - Cron başarısızlık bildirimi
        - e-Fatura dashboard (7 filtreli görünüm)
        - Gelen e-Fatura: tam UBL parse + 3 fazlı ürün eşleme
          Faz 1: VKN kesin + fuzzy partner eşleme
          Faz 2: Öğrenen tablo + UBL kodu eşleme
          Faz 3: difflib benzerlik + kural motoru + toplu onay ekranı
        - VKN/TCKN format ve benzersizlik doğrulaması
        - Kredi notu (iade faturası) e-Fatura akışı
        - GİB kodları tek kaynak (constants.py)
    """,
    'author': 'Geliştirici',
    # saxonche kaldırıldı: UBL validasyonu artık lxml + XPath ile yapılıyor.
    # GİB Schematron kuralları doğrudan XPath sorguları olarak implement edildi.
    # lxml Odoo'nun standart bağımlılığıdır; ek kurulum gerekmez.
    'external_dependencies': {
        'python': [],
    },
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
        'wizards/incoming_invoice_match_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
