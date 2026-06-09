# -*- coding: utf-8 -*-
"""
GİB Durum Kodu Setleri — TEK KAYNAK
====================================
Bu modülde tanımlanan setler hem account_move.py (_process_gib_status)
hem de resend_invoice_wizard.py (Tekrar Gönder akışı) tarafından import edilir.
Bir set burada güncellenir, her yer otomatik güncel olur.

Referans: Logo Tiger durum kodu listesi + Spec v6.2 Bölüm 11
"""

# Teknik hata — aynı UUID ile düzelt + tekrar gönder
GIB_RETRY_SAME_UUID = {
    1101,  # XML/Yapı hatası
    1103,  # Zorunlu alan boş
    1110,  # ZIP dosyası değil
    1111,  # Zarf ID uzunluğu geçersiz
    1120,  # Zarf arşivden kopyalanamadı
    1130,  # ZIP açılamadı
    1131,  # ZIP bir dosya içermeli
    1132,  # XML dosyası değil
    1133,  # Zarf ID ve XML adı uyuşmuyor
    1140,  # Doküman ayrıştırılamadı
    1141,  # Zarf ID yok
    1142,  # Zarf ID ve ZIP adı uyuşmuyor
    1143,  # Geçersiz UBL versiyonu
    1150,  # Schematron kontrol hatalı
    1160,  # XML şema kontrolünden geçemedi
    1162,  # İmza kaydedilemedi
    1170,  # Şematron uyumsuz
    1175,  # İmza yetkisi kontrol edilemedi
    1210,  # Alıcıda işlenemedi (1. deneme) — iptal gerekmez
    1230,  # Alıcıda işlenemedi (devam)
}

# İçerik hatası — iptal + yeni fatura gerekli
GIB_CANCEL_AND_NEW = {
    1104,  # Numara tekrarı / benzersiz değil
    1163,  # Zarf sistemde kayıtlı — mükerrer UUID
}

# İmza / yetki — Sovos teknik destek
GIB_SOVOS_SUPPORT = {
    1161,  # İmza sahibi TCKN/VKN alınamadı
    1171,  # Gönderici birim yetkisi yok
    1172,  # Posta kutusu yetkisi yok
}

# Başarı — GİB onayladı (kesinlikle tekrar gönderme)
GIB_SUCCESS = {1300}

# Alıcı kabul etti — TICARIFATURA ApplicationResponse
GIB_ACCEPTED_BY_RECEIVER = {1305}

# Alıcı reddetti
GIB_REJECTED = {1310}

# Kuyrukta / İşleniyor — cron bir sonraki döngüde tekrar sorgular
GIB_PENDING = {1000, 1100}

# 4 deneme başarısız — admin bildirim + manuel müdahale
# NOT: Bu kod için x_efatura_status 'sent' KALIR (error'a geçirilmez),
# böylece cron bir sonraki döngüde tekrar sorgulayabilir.
# Kullanıcıya hata mesajı gösterilir + admin bildirim gönderilir.
GIB_NOTIFY_ADMIN = {1215}
