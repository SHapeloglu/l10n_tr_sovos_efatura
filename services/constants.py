# -*- coding: utf-8 -*-
"""
constants.py — GİB Durum Kodu Setleri — TEK KAYNAK
====================================================

Bu modül, GİB'den dönen tüm durum kodlarını kategorilere ayırır.
Hem account_move.py (_process_gib_status) hem de resend_invoice_wizard.py
(Tekrar Gönder akışı) bu dosyadan import eder.

Neden tek kaynak?
    Eskiden her dosyada ayrı set tanımı vardı. Biri güncellenince diğeri
    unutulabiliyordu (senkronizasyon kayması). Şimdi burayı değiştirince
    her yer otomatik güncel olur.

Referans: kaynaklar/GIB DETAYLI DURUM KODLARI TR.pdf (Sovos, 2021)
          + kaynaklar/Sovos R&D - Sık Sorulan Sorular.xlsx
          + egitim_notlari.md Bölüm 3

v8.0 değişiklikleri:
    Eksik 11 GİB kodu eklendi (PDF kaynaklı):
    1176, 1177 → GIB_SOVOS_SUPPORT
    1180, 1181, 1182, 1183, 1190, 1195 → GIB_RETRY_SAME_UUID
    1200, 1220 → GIB_PENDING
    1300 → GIB_SUCCESS (önceden eksikti, else bloğuna düşüyordu)
"""

# ─────────────────────────────────────────────────────────────────────────────
# GIB_RETRY_SAME_UUID
# ─────────────────────────────────────────────────────────────────────────────
# Teknik hata — XML'i veya veriyi düzelttikten sonra AYNI UUID ile tekrar gönder.
# Fatura numarası değişmez. Yeni fatura kesmek YANLIŞTIR.
# Kullanım: resend_invoice_wizard.py → _resend_same_uuid()
GIB_RETRY_SAME_UUID = {
    1101,  # XML yapısında hata (UBL-TR şema ihlali)
    1103,  # Zorunlu alan boş bırakılmış (ör: VKN, fatura tarihi)
    1110,  # Gönderilen dosya ZIP formatında değil
    1111,  # Zarf UUID uzunluğu 36 karakter olmalı (UUID v4 formatı)
    1120,  # Zarf arşivden kopyalanamadı (sunucu tarafı geçici hata)
    1130,  # ZIP açılamadı (bozuk sıkıştırma)
    1131,  # ZIP içinde birden fazla dosya var; sadece 1 XML olmalı
    1132,  # ZIP içindeki dosya .xml uzantılı değil
    1133,  # ZIP adı ile içindeki XML dosya adı uyuşmuyor (her ikisi UUID.xml/UUID.zip olmalı)
    1140,  # XML belgesi ayrıştırılamadı (encoding sorunu veya bozuk XML)
    1141,  # Zarf UUID alanı XML içinde bulunamadı
    1142,  # Zarf UUID ile ZIP dosya adı uyuşmuyor
    1143,  # UBL versiyonu 2.1 olmalı; farklı versiyon gönderilmiş
    1150,  # Schematron iş kuralı kontrolü başarısız (GİB iş kuralı ihlali)
    1160,  # XSD şema doğrulaması başarısız (zorunlu eleman/attribute eksik veya yanlış tip)
    1162,  # Dijital imza kaydedilemedi (Sovos tarafı geçici hata)
    1170,  # Schematron versiyonu uyumsuz (GİB güncel schematron kullanılmalı)
    1175,  # İmza yetkisi kontrol edilemedi (geçici GİB erişim sorunu)
    1180,  # Alıcı adresi kontrol edilemedi — alıcı alias/VKN bilgisini doğrulayın
    1181,  # Alıcı adresi bulunamadı — alias ve VKN uyumsuz; GetUserList ile güncel alias alın
    1182,  # Kullanıcı eklenemedi (geçici sistem hatası) — tekrar gönder
    1183,  # Kullanıcı silinemedi (geçici sistem hatası) — tekrar gönder
    1190,  # Sistem yanıtı hazırlanamadı (GİB tarafı geçici hata) — tekrar gönder
    1195,  # Genel sistem hatası (GİB tarafı geçici hata) — tekrar gönder
    1210,  # Alıcı posta kutusunda işlenemedi — 1. deneme; iptal gerekmez, tekrar gönder
    1230,  # Alıcıda işlenemedi — devam eden hata; tekrar gönder
}

# ─────────────────────────────────────────────────────────────────────────────
# GIB_CANCEL_AND_NEW
# ─────────────────────────────────────────────────────────────────────────────
# İçerik hatası — Bu fatura artık kurtarılamaz. Adımlar:
#   1. Mevcut faturayı iptal et (cancel_invoice_wizard)
#   2. Yeni fatura kes (yeni numara + yeni UUID)
# Aynı UUID ile tekrar gönderme YANLIŞTIR ve 1163 üretir.
GIB_CANCEL_AND_NEW = {
    1104,  # Fatura numarası GİB'te zaten kayıtlı (numara tekrarı / çakışma)
    1163,  # Bu zarf UUID'si GİB sisteminde daha önce kayıt altına alınmış (mükerrer UUID)
}

# ─────────────────────────────────────────────────────────────────────────────
# GIB_SOVOS_SUPPORT
# ─────────────────────────────────────────────────────────────────────────────
# İmza veya yetki hatası — Geliştirici veya kullanıcı düzeltemez.
# Sovos teknik destek ile iletişime geçilmesi gerekir.
GIB_SOVOS_SUPPORT = {
    1161,  # Dijital imza sahibinin TCKN/VKN alınamadı (Sovos sertifika sorunu)
    1171,  # Gönderici birimin GİB'te yetkisi yok (Sovos hesap ayarı)
    1172,  # Posta kutusu (GB kodu) için yetki yok (Sovos hesap ayarı)
    1176,  # İmza sahibi yetkisiz — imzalayan sertifika GİB'te tanımlı değil
    1177,  # İmza doğrulama geçersiz — imzalama işlemi hatalı; Sovos desteğe bildirin
}

# ─────────────────────────────────────────────────────────────────────────────
# GIB_SUCCESS
# ─────────────────────────────────────────────────────────────────────────────
# GİB faturayı başarıyla işledi ve onayladı.
# x_efatura_status → 'accepted' yapılır.
# DİKKAT: 1305 (alıcı kabulü) buraya dahil DEĞİLDİR; ayrı blokta işlenir.
GIB_SUCCESS = {
    1300,  # Başarıyla tamamlandı — GİB onayladı, alıcıya iletildi
}

# ─────────────────────────────────────────────────────────────────────────────
# GIB_ACCEPTED_BY_RECEIVER
# ─────────────────────────────────────────────────────────────────────────────
# Alıcı firma TICARIFATURA'yı ApplicationResponse mesajıyla kabul etti.
# x_inv_response_status → 'kabul' yapılır.
# 1300'den ayrı tutulur çünkü ek olarak x_inv_response_status güncellenir.
GIB_ACCEPTED_BY_RECEIVER = {1305}  # Alıcı TICARIFATURA'yı kabul etti

# ─────────────────────────────────────────────────────────────────────────────
# GIB_REJECTED
# ─────────────────────────────────────────────────────────────────────────────
# Alıcı firma TICARIFATURA'yı reddetti.
# x_inv_response_status → 'red' yapılır.
# Yapılması gereken: faturayı iptal et + yeni fatura kes (alıcı ile mutabık kal).
GIB_REJECTED = {1310}  # Alıcı faturayı ApplicationResponse ile reddetti

# ─────────────────────────────────────────────────────────────────────────────
# GIB_PENDING
# ─────────────────────────────────────────────────────────────────────────────
# Fatura GİB sisteminde kuyrukta, işleniyor veya ara durumda.
# Hiçbir şey yapılmaz — cron bir sonraki döngüde (30 dk) tekrar sorgular.
#
# 1220 UYARISI — TEKRAR GÖNDERİLMEZ:
#   1220 "Hedeften Sistem Yanıtı Gelmedi" alındığında fatura alıcı sistemine
#   iletilmiş demektir; GİB alıcıdan onay bekliyor. Bu aşamada aynı zarfı
#   tekrar göndermek 1163 (mükerrer UUID) hatasına yol açar.
#   Cron beklemeye devam etmeli; alıcı sistemi GİB'e yanıt gönderince
#   durum 1300'e dönecektir. (Kaynak: egitim_notlari.md Bölüm 13.12)
GIB_PENDING = {
    1000,  # GİB kuyruğunda bekliyor (henüz işleme alınmadı)
    1100,  # GİB tarafından işleniyor (ara durum)
    1200,  # Zarf başarıyla işlendi, alıcıya gönderilecek (ara onay durumu)
    1220,  # Hedeften sistem yanıtı gelmedi — alıcı aldı ama GİB'e bildirmedi
           # ⚠️ TEKRAR GÖNDERİLMEZ — cron 1300 beklemeli
}

# ─────────────────────────────────────────────────────────────────────────────
# GIB_NOTIFY_ADMIN
# ─────────────────────────────────────────────────────────────────────────────
# Kritik durum — Sistem yöneticisine Odoo bildirimi + e-posta gönderilir.
#
# ÖNEMLI DAVRANIS (DÜZELTME #1):
#   1215 alındığında x_efatura_status 'error'a GEÇİRİLMEZ; 'sent' KALIR.
#   Neden? 'error'a geçirilseydi cron bu faturayı bir daha sorgulamazdı
#   (cron filtresi: x_efatura_status in ('sent', 'sending')).
#   'sent' kalınca cron takip etmeye devam eder.
#   Kullanıcıya hata mesajı gösterilir + admin tek seferlik bildirim alır.
#   Manuel müdahale gerekirse Tekrar Gönder wizard'ı kullanılır.
GIB_NOTIFY_ADMIN = {
    1215,  # 4 otomatik deneme başarısız — GİB sistemine erişilemiyor
}


# ─────────────────────────────────────────────────────────────────────────────
# _gib_msg — GİB Durum Kodu Kullanıcı Mesajları
# ─────────────────────────────────────────────────────────────────────────────
# MADDE 3 DÜZELTME: account_move.py'den buraya taşındı.
# GİB kod setleri (GIB_RETRY_SAME_UUID vb.) ve mesajlar artık tek dosyada.
# Yeni GİB kodu eklenince sadece constants.py güncellenir; deploy yeterli.
# Lazy tanımlama: _() her çağrıda aktif dil context'inde çevirilir.
from odoo import _

def _gib_msg(code):
    """
    GİB durum koduna karşılık gelen kullanıcı dostu mesajı döndürür.
    Lazy tanımlama: her çağrıda aktif dil context'inde _() çevrilir.
    (Module-level dict tanımı çeviriyi bozar — Odoo best practice)
    """
    msgs = {
        1000: _('GİB kuyruğunda bekliyor. Cron takip ediyor.'),
        1100: _('GİB tarafından işleniyor. Cron takip ediyor.'),
        1101: _('UBL-TR formatında sorun. Tekrar Gönder butonunu kullanın.'),
        1103: _('Zorunlu alan boş. Fatura bilgilerini tamamlayın.'),
        1104: _('Fatura numarası daha önce kullanılmış. Sistem yöneticisi ile iletişime geçin.'),
        1110: _('ZIP formatı hatalı. Tekrar Gönder butonunu kullanın.'),
        1111: _('Zarf ID uzunluğu geçersiz. Tekrar Gönder butonunu kullanın.'),
        1120: _('Zarf arşivden kopyalanamadı. Tekrar Gönder butonunu kullanın.'),
        1130: _('ZIP açılamadı. Tekrar Gönder butonunu kullanın.'),
        1131: _('ZIP bir dosya içermeli. Tekrar Gönder butonunu kullanın.'),
        1132: _('XML dosyası değil. Tekrar Gönder butonunu kullanın.'),
        1133: _('Dosya adı uyuşmuyor. Tekrar Gönder butonunu kullanın.'),
        1140: _('XML ayrıştırılamadı. Tekrar Gönder butonunu kullanın.'),
        1141: _('Zarf ID eksik. Tekrar Gönder butonunu kullanın.'),
        1142: _('Zarf ID ve ZIP adı uyuşmuyor. Tekrar Gönder butonunu kullanın.'),
        1143: _('Geçersiz UBL versiyonu (2.1 zorunlu). Tekrar Gönder butonunu kullanın.'),
        1150: _('GİB iş kuralı kontrolü başarısız. Tekrar Gönder butonunu kullanın.'),
        1160: _('XML şema kontrolü başarısız. Tekrar Gönder butonunu kullanın.'),
        1161: _('İmza hatası. Sovos teknik destek ile iletişime geçin.'),
        1162: _('İmza kaydedilemedi. Tekrar Gönder butonunu kullanın.'),
        1163: _('Bu fatura zaten GİB\'te kayıtlı. İptal edip yeni fatura kesin.'),
        1170: _('Schematron uyumsuz. Tekrar Gönder butonunu kullanın.'),
        1171: _('Gönderici birim yetkisi yok. Sovos teknik destek ile iletişime geçin.'),
        1172: _('Posta kutusu yetkisi yok. Sovos teknik destek ile iletişime geçin.'),
        1175: _('İmza yetkisi kontrol edilemedi. Tekrar Gönder butonunu kullanın.'),
        1176: _('İmza sahibi yetkisiz. Sovos teknik destek ile iletişime geçin.'),
        1177: _('İmza doğrulama geçersiz. Sovos teknik destek ile iletişime geçin.'),
        1180: _('Alıcı adresi kontrol edilemedi. Alıcı alias bilgisini doğrulayıp Tekrar Gönder.'),
        1181: _('Alıcı adresi bulunamadı. Müşteri kartındaki alias\'ı güncelleyip Tekrar Gönder.'),
        1182: _('Kullanıcı eklenemedi (geçici hata). Tekrar Gönder butonunu kullanın.'),
        1183: _('Kullanıcı silinemedi (geçici hata). Tekrar Gönder butonunu kullanın.'),
        1190: _('GİB sistem yanıtı hazırlanamadı (geçici hata). Tekrar Gönder butonunu kullanın.'),
        1195: _('GİB sistem hatası (geçici). Tekrar Gönder butonunu kullanın.'),
        1200: _('Zarf başarıyla işlendi, alıcıya iletilecek. Cron takip ediyor.'),
        1210: _('Alıcıya ulaşılamadı — iptal gerekmez. Tekrar Gönder.'),
        1215: _('GİB sistemi 4 denemede yanıt vermedi. Sistem yöneticisi bilgilendirildi. Cron takip ediyor.'),
        1220: _('Alıcı sistemi aldı, GİB\'e henüz bildirmedi. Cron 1300 bekliyor — tekrar göndermeyin.'),
        1230: _('Alıcıda işlenemedi. Tekrar Gönder.'),
        1300: _('Fatura başarıyla tamamlandı.'),
        1305: _('Alıcı faturayı kabul etti.'),
        1310: _('Alıcı faturayı reddetti. İptal edip yeni fatura kesin.'),
    }
    return msgs.get(code, _('GİB kodu %d — bilinmeyen durum. Sistem yöneticisi ile iletişime geçin.') % code)
