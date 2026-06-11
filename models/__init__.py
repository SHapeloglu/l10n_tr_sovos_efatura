# -*- coding: utf-8 -*-
from . import res_company
#res.company — Şirket 
#Odoo'da her şey bir şirkete bağlıdır. 
#Kullanıcının hangi şirkette çalıştığı, para birimi, adresi, 
#muhasebe ayarları hep burada tutulur. 
#Multi-company kurulumda her şirket ayrı bir kayıttır. 
#Biz buraya Sovos kullanıcı adı/şifre, VKN, test modu gibi e-Fatura 
#bağlantı alanları ekledik.
from . import res_partner
#res.partner — Müşteri / Tedarikçi / Kişi
#Odoo'nun en merkezi modellerinden biri. 
#Müşteriler, tedarikçiler, çalışanlar, 
#şirket adresleri hepsi res.partner'da tutulur. 
#customer_rank > 0 ise müşteri, supplier_rank > 0 ise tedarikçidir. 
#Bir faturanın partner_id alanı buraya bağlıdır. 
#Biz buraya VKN cache (x_efatura_type), 
#vergi dairesi, GB kodu gibi alanlar ekledik.
from . import product_uom
#uom.uom — Ölçü Birimi (Unit of Measure)
#Ürün ve fatura kalemlerinde kullanılan birimler burada tanımlanır. 
#Adet, Kg, Metre, Litre gibi. uom modülü aktif olmazsa bu model 
#Odoo'da görünmez. Biz sadece tek alan ekledik: 
#x_ubl_code — GİB'in istediği UN/CEFACT kodu (C62, KGM vb.).
from . import account_move
from . import sovos_sync
