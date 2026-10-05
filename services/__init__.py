# -*- coding: utf-8 -*-
# Bu dosya Python'ın services/ dizinini paket olarak tanıması için gereklidir.
#
# Servisler (UblBuilder, SovosInvoiceService vb.) model dosyalarında
# fonksiyon içinde lazy import edilir:
#
#   from ..services.ubl_builder import UblBuilder
#
# Lazy import tercih edilmesinin nedeni: model dosyaları Odoo registry'ye
# yüklenirken servisler henüz tam başlatılmamış olabilir; fonksiyon içinde
# import edilince circular import riski ortadan kalkar ve import zamanı kısalır.
# services/__init__.py'de star-import veya doğrudan import yapmak GEREKMİYOR.
