#!/bin/bash
# =============================================================================
# setup_schemas.sh — GİB Şema Dosyalarını Projeye Kur
# =============================================================================
# Kullanım:
#   bash setup_schemas.sh <UBL_PAKETI_ZIP> <EFATURA_PAKETI_ZIP> [SCHEMAS_DIR]
#
# Örnek:
#   bash setup_schemas.sh UBL-TR1.2.1_Paketi.zip e-FaturaPaketi.zip
#   bash setup_schemas.sh UBL-TR1.2.1_Paketi.zip e-FaturaPaketi.zip /opt/odoo/addons/l10n_tr_sovos_efatura/services/schemas
#
# Kaynaklar:
#   UBL Paketi    : https://ebelge.gib.gov.tr/dosyalar/kilavuzlar/UBL-TR1.2.1_Paketi.zip
#   e-Fatura Paketi: https://ebelge.gib.gov.tr/dosyalar/kilavuzlar/e-FaturaPaketi.zip
# =============================================================================

set -e

UBL_ZIP="${1:-}"
EFATURA_ZIP="${2:-}"
SCHEMAS_DIR="${3:-$(dirname "$0")/services/schemas}"

# ── Argüman kontrolü ──────────────────────────────────────────────────────────
if [[ -z "$UBL_ZIP" || -z "$EFATURA_ZIP" ]]; then
    echo "Kullanım: bash setup_schemas.sh <UBL_PAKETI_ZIP> <EFATURA_PAKETI_ZIP> [SCHEMAS_DIR]"
    echo ""
    echo "Örnek:"
    echo "  bash setup_schemas.sh UBL-TR1.2.1_Paketi.zip e-FaturaPaketi.zip"
    exit 1
fi

if [[ ! -f "$UBL_ZIP" ]]; then
    echo "HATA: UBL paketi bulunamadı: $UBL_ZIP"
    exit 1
fi

if [[ ! -f "$EFATURA_ZIP" ]]; then
    echo "HATA: e-Fatura paketi bulunamadı: $EFATURA_ZIP"
    exit 1
fi

echo "=== GİB Şema Kurulum Başlıyor ==="
echo "UBL Paketi   : $UBL_ZIP"
echo "eFatura Paketi: $EFATURA_ZIP"
echo "Hedef dizin  : $SCHEMAS_DIR"
echo ""

# ── Dizinleri oluştur ─────────────────────────────────────────────────────────
mkdir -p "$SCHEMAS_DIR/maindoc"
mkdir -p "$SCHEMAS_DIR/common"

# ── Katman 1: XSD Dosyaları (UBL-TR1.2.1_Paketi.zip) ─────────────────────────
echo "[1/2] XSD dosyaları çıkarılıyor..."

# Ana fatura XSD — maindoc/ altına
unzip -p "$UBL_ZIP" "UBLTR_1.2.1_Paketi/xsdrt/maindoc/UBL-Invoice-2.1.xsd" \
    > "$SCHEMAS_DIR/maindoc/UBL-Invoice-2.1.xsd"
echo "  ✓ maindoc/UBL-Invoice-2.1.xsd"

# Bağımlı common XSD'leri — common/ altına
COMMON_FILES=(
    "CCTS_CCT_SchemaModule-2.1.xsd"
    "UBL-CommonAggregateComponents-2.1.xsd"
    "UBL-CommonBasicComponents-2.1.xsd"
    "UBL-CommonExtensionComponents-2.1.xsd"
    "UBL-CommonSignatureComponents-2.1.xsd"
    "UBL-CoreComponentParameters-2.1.xsd"
    "UBL-ExtensionContentDataType-2.1.xsd"
    "UBL-QualifiedDataTypes-2.1.xsd"
    "UBL-SignatureAggregateComponents-2.1.xsd"
    "UBL-SignatureBasicComponents-2.1.xsd"
    "UBL-UnqualifiedDataTypes-2.1.xsd"
    "UBL-XAdESv132-2.1.xsd"
    "UBL-XAdESv141-2.1.xsd"
    "UBL-xmldsig-core-schema-2.1.xsd"
)

for fname in "${COMMON_FILES[@]}"; do
    unzip -p "$UBL_ZIP" "UBLTR_1.2.1_Paketi/xsdrt/common/$fname" \
        > "$SCHEMAS_DIR/common/$fname"
    echo "  ✓ common/$fname"
done

# ── Katman 2: Schematron Dosyaları (e-FaturaPaketi.zip) ──────────────────────
echo ""
echo "[2/2] Schematron dosyaları çıkarılıyor..."

# Ana Schematron (include direktifleri içerir)
unzip -p "$EFATURA_ZIP" "e-FaturaPaketi/schematron/UBL-TR_Main_Schematron.xml" \
    > "$SCHEMAS_DIR/UBL-TR_Main_Schematron.xml"
echo "  ✓ UBL-TR_Main_Schematron.xml"

# Ortak kurallar (abstract rule'lar)
unzip -p "$EFATURA_ZIP" "e-FaturaPaketi/schematron/UBL-TR_Common_Schematron.xml" \
    > "$SCHEMAS_DIR/UBL-TR_Common_Schematron.xml"
echo "  ✓ UBL-TR_Common_Schematron.xml"

# Kod listeleri (ProfileID, InvoiceTypeCode vb. kontrolleri)
unzip -p "$EFATURA_ZIP" "e-FaturaPaketi/schematron/UBL-TR_Codelist.xml" \
    > "$SCHEMAS_DIR/UBL-TR_Codelist.xml"
echo "  ✓ UBL-TR_Codelist.xml"

# ── Doğrulama ─────────────────────────────────────────────────────────────────
echo ""
echo "=== Kurulum Tamamlandı ==="
echo ""
echo "Dizin yapısı:"
echo "  $SCHEMAS_DIR/"
echo "  ├── maindoc/"
echo "  │   └── UBL-Invoice-2.1.xsd"
echo "  ├── common/  ($(ls "$SCHEMAS_DIR/common/" | wc -l) dosya)"
echo "  ├── UBL-TR_Main_Schematron.xml"
echo "  ├── UBL-TR_Common_Schematron.xml"
echo "  └── UBL-TR_Codelist.xml"
echo ""

# Python ile hızlı doğrulama
# NOT: GİB Schematron dosyaları (UBL-TR_Main_Schematron.xml vb.) runtime'da
# okunmaz; ubl_validator.py GİB iş kurallarını doğrudan lxml XPath ile
# uygular. lxml.isoschematron GİB'in XSLT 2.0 gerektiren Schematron kurallarını
# derleyemediğinden burada yalnızca XSD yüklemesi doğrulanır.
python3 - "$SCHEMAS_DIR" <<'PYEOF'
import sys
import os

schemas_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), 'services/schemas')

print("Python doğrulama:")
try:
    from lxml import etree

    # XSD testi — UBL-Invoice-2.1.xsd common/ bağımlılıklarıyla birlikte yüklenir
    xsd_path = os.path.join(schemas_dir, 'maindoc', 'UBL-Invoice-2.1.xsd')
    if not os.path.isfile(xsd_path):
        print("  ✗ XSD bulunamadı:", xsd_path)
        sys.exit(1)
    xsd = etree.XMLSchema(etree.parse(xsd_path))
    print("  ✓ XSD yüklendi — UBL-Invoice-2.1.xsd (lxml)")

    # Schematron dosyaları referans amaçlı — parse edilebilir olmaları yeterli
    for sch_name in (
        'UBL-TR_Main_Schematron.xml',
        'UBL-TR_Common_Schematron.xml',
        'UBL-TR_Codelist.xml',
    ):
        sch_path = os.path.join(schemas_dir, sch_name)
        if not os.path.isfile(sch_path):
            print("  ✗ Schematron bulunamadı:", sch_name)
            sys.exit(1)
        etree.parse(sch_path)   # parse edilebilirlik kontrolü
        print("  ✓ Schematron parse edildi (referans) —", sch_name)

    print("")
    print("Kurulum başarılı. Validasyon servisi (ubl_validator.py) kullanıma hazır.")

except ImportError as e:
    print("  ✗ lxml kurulu değil:", e)
    print("    pip install lxml")
    sys.exit(1)
except Exception as e:
    print("  ✗ Hata:", e)
    sys.exit(1)
PYEOF
