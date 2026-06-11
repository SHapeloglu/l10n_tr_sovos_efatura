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

Referans: Logo Tiger durum kodu listesi + Spec v6.2 Bölüm 11
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
}

# ─────────────────────────────────────────────────────────────────────────────
# GIB_SUCCESS
# ─────────────────────────────────────────────────────────────────────────────
# GİB faturayı başarıyla işledi ve onayladı.
# x_efatura_status → 'accepted' yapılır.
# DİKKAT: 1305 (alıcı kabulü) buraya dahil DEĞİLDİR; ayrı blokta işlenir.
GIB_SUCCESS = {1300}  # GİB onayladı, fatura tamamlandı

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
# Fatura GİB sisteminde kuyrukta veya işleniyor.
# Hiçbir şey yapılmaz — cron bir sonraki döngüde (30 dk) tekrar sorgular.
GIB_PENDING = {
    1000,  # GİB kuyruğunda bekliyor (henüz işleme alınmadı)
    1100,  # GİB tarafından işleniyor (ara durum)
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
