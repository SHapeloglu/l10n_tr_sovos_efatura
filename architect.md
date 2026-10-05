# architect.md — 🧾 l10n_tr_sovos_efatura Mimari Referansı

Bu dosya projenin yapısının hızlı-referans özetidir. Kod değiştikçe güncel tutun.

## Genel Bakış

**Odoo 18 Community × Sovos e-Fatura / e-Arşiv Entegrasyon Modülü** **Teknik Entegrasyon Spesifikasyonu v6.0 — Haziran 2026 — Final** Satış + Alış + Muhasebe + PDF Arşivi + Kur Farkı + XSD/Schematron Validasyon + Atomik Fatura Numarası

## Teknoloji Yığını

- Odoo 18 modülü (Python + XML view)

## Dizin Yapısı

```
"kaynaklar/
  Sovos R&D -S\304\261k Sorulan Sorular.xlsx"
README.md
__init__.py
__manifest__.py
__pycache__/
data/
dokumanlar/
  Odoo18_Sovos_eFatura_BRD.docx
  Odoo18_Sovos_eFatura_Spec.docx
  efatura_test_analiz_raporu.docx
  egitim_notlari.md
  odoo_gelistirici_sozlugu.md
  sovos_test_rehberi.docx
kaynaklar/
  GIB DETAYLI DURUM KODLARI TR.pdf
  Sovos R&D - UBL-TR Catalogue.xlsx
  setup.exe
  turkey-cloud-sample-api-client-main.zip
models/
  __init__.py
  account_move.py
  product_uom.py
  res_company.py
  res_partner.py
  sovos_sync.py
security/
  ir.model.access.csv
services/
  __init__.py
  constants.py
  schemas/
  sovos_archive_service.py
  sovos_invoice_service.py
  ubl_builder.py
  ubl_validator.py
static/
tests/
  __init__.py
  common.py
  …
```

## Modüller / Kaynak Dosyalar

- `__manifest__.py`
- `models/account_move.py` — account_move.py — e-Fatura / e-Arşiv ana model
- `models/product_uom.py` — product_uom.py — Ölçü Birimi Genişletmesi
- `models/res_company.py` — res_company.py — Şirket Ayarları Genişletmesi
- `models/res_partner.py` — res_partner.py — Müşteri/Tedarikçi Kart Genişletmesi
- `models/sovos_sync.py` — sovos_sync.py — Sovos Arka Plan Görevleri (Cron İşleri)
- `services/constants.py` — constants.py — GİB Durum Kodu Setleri — TEK KAYNAK
- `services/sovos_archive_service.py` — sovos_archive_service.py — Sovos ArchiveService SOAP İstemcisi
- `services/sovos_invoice_service.py` — sovos_invoice_service.py — Sovos InvoiceService SOAP İstemcisi
- `services/ubl_builder.py` — ubl_builder.py — UBL-TR 2.1 Fatura XML Üreticisi
- `services/ubl_validator.py` — ubl_validator.py — UBL-TR İki Katmanlı Validasyon Servisi
- `wizards/cancel_invoice_wizard.py` — cancel_invoice_wizard.py — Fatura İptal Sihirbazı
- `wizards/kur_farki_wizard.py` — kur_farki_wizard.py — Kur Farkı Faturası Sihirbazı
- `wizards/resend_invoice_wizard.py` — resend_invoice_wizard.py — Tekrar Gönderim Sihirbazı

## Giriş Noktaları ve Yapılandırma

- `__manifest__.py`
- `static/description/index.html`

## Dağıtım / Çalışma Ortamı

- GitHub: https://github.com/SHapeloglu/l10n_tr_sovos_efatura

## Diğer Dokümanlar

- `README.md`

## Mimari Kararlar

_Önemli tasarım kararlarını ve gerekçelerini buraya ekleyin (ör. "X yerine Y seçildi çünkü ...")._
