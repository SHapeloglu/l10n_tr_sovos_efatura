# -*- coding: utf-8 -*-
from . import (
    common,
    test_atomic_number,
    test_gib_status,
    test_vkn_cache,
    test_account_move,
    test_ubl_validator,
    test_wizards,
    test_cron,
    test_accounting,      # muhasebe fişi — TDHP 120/600/391 (AC-07/AC-08)
    test_extras,          # e-posta, bağlantı testi, kur farkı, dashboard
    test_multicompany,    # çok şirket credentials izolasyonu (AC-11)
    test_ubl_builder,     # UBL XML yapısı, ZIP içeriği, CopyIndicator (AC-12)
    test_incoming,        # gelen fatura: UBL parser, eşleme motoru, öğrenen tablo, sihirbaz
)
