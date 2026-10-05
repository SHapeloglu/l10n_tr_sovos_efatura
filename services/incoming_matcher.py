# -*- coding: utf-8 -*-
"""
incoming_matcher.py — Gelen Fatura Eşleme Motoru
=================================================
UBL parser'dan gelen veriyi Odoo kayıtlarıyla eşleştirir.

Faz 1: Partner (VKN kesin eşleme)
Faz 2: Ürün (öğrenen tablo + UBL kodu)
Faz 3: difflib benzerlik + kural motoru + skor bazlı sınıflandırma

Benzerlik eşikleri:
    >= 0.85 → Otomatik (kullanıcı onayı yok)
    0.60-0.84 → Öneri (kullanıcı seçsin)
    < 0.60  → Manuel (bekletme kuyruğu)
"""
import logging
from difflib import SequenceMatcher

_logger = logging.getLogger(__name__)

MATCH_AUTO    = 0.85
MATCH_SUGGEST = 0.60


def _sim(a, b):
    """İki string benzerlik skoru 0.0-1.0."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


class IncomingMatcher:
    """
    Gelen fatura verilerini Odoo kayıtlarıyla eşleştiren motor.
    Tüm Faz 1, 2 ve 3 burada uygulanır.
    """

    def __init__(self, env):
        self.env = env

    # ═══════════════════════════════════════════════════════════════════════
    # FAZ 1: Partner Eşleme
    # ═══════════════════════════════════════════════════════════════════════

    def find_partner(self, vkn, name=''):
        """
        FAZ 1: Tedarikçi eşleme.
        Adımlar:
          1. VKN kesin eşleme (ana cari önce)
          2. VKN yoksa ticari unvan benzerliği (Faz 3 — fuzzy)
          3. Hiç bulunamazsa False → bekletme kuyruğuna düşer

        Returns: (res.partner|False, confidence: float, source: str)
        """
        Partner = self.env['res.partner']

        if vkn:
            # 1a. Ana cari VKN eşleşme
            p = Partner.search([('vat', '=', vkn), ('parent_id', '=', False)], limit=1)
            if p:
                return p, 1.0, 'vkn_exact'

            # 1b. Alt cari / şube dahil
            p = Partner.search([('vat', '=', vkn)], limit=1)
            if p:
                return p, 0.95, 'vkn_child'

        # FAZ 3: Ticari unvan fuzzy match
        if name:
            best_p, best_score = None, 0.0
            candidates = Partner.search([
                ('supplier_rank', '>', 0),
                ('parent_id', '=', False),
            ], limit=200)
            for c in candidates:
                score = _sim(name, c.name or '')
                if score > best_score:
                    best_score, best_p = score, c

            if best_score >= MATCH_AUTO:
                _logger.info('Partner fuzzy (%.0f%%): %s → %s', best_score * 100, name, best_p.name)
                return best_p, best_score, 'fuzzy_auto'
            elif best_score >= MATCH_SUGGEST:
                _logger.info('Partner öneri (%.0f%%): %s → %s', best_score * 100, name, best_p.name)
                return best_p, best_score, 'fuzzy_suggest'

        _logger.warning('Partner bulunamadı: VKN=%s İsim=%s', vkn, name)
        return False, 0.0, 'none'

    # ═══════════════════════════════════════════════════════════════════════
    # FAZ 2 + 3: Ürün Eşleme
    # ═══════════════════════════════════════════════════════════════════════

    def find_product(self, supplier_id, description, ubl_code=''):
        """
        Ürün eşleme — tüm fazlar:
          FAZ 2: Öğrenen tablo → kesin eşleme
          FAZ 2: UBL tedarikçi kodu (SellersItemIdentification)
          FAZ 3: difflib benzerlik skoru
          FAZ 3: Tedarikçi bazlı kural motoru (prefix/suffix temizleme)

        Returns: dict {product, account, tax_ids, uom, confidence, source}
        """
        Mapping = self.env['efatura.product.mapping']

        # ── FAZ 2: Öğrenen Tablo ─────────────────────────────────────────
        if supplier_id and description:
            mapping = Mapping.find_mapping(supplier_id, description)
            if mapping and mapping.product_id:
                mapping.increment_usage()
                return {
                    'product': mapping.product_id,
                    'account': mapping.account_id,
                    'tax_ids': mapping.tax_ids,
                    'uom':     mapping.uom_id,
                    'confidence': 1.0,
                    'source':  'learned_mapping',
                }

        # ── FAZ 2: UBL Tedarikçi Kodu ────────────────────────────────────
        if ubl_code:
            prod = self.env['product.product'].search(
                [('default_code', '=', ubl_code)], limit=1
            )
            if prod:
                return self._result(prod, 0.95, 'ubl_code')

        # ── FAZ 3: Kural Motoru — Tedarikçi Özel Prefix/Suffix ──────────
        # Önce açıklamayı normalleştir (tedarikçi bazlı kural)
        normalized = self._apply_supplier_rules(supplier_id, description)

        # ── FAZ 3: difflib Benzerlik ──────────────────────────────────────
        if normalized:
            products = self.env['product.product'].search([
                ('purchase_ok', '=', True),
                ('active', '=', True),
            ], limit=300)

            best_prod, best_score = None, 0.0
            for prod in products:
                for field_val in [prod.name or '', prod.description_purchase or '']:
                    score = _sim(normalized, field_val)
                    if score > best_score:
                        best_score, best_prod = score, prod

            if best_score >= MATCH_AUTO:
                return self._result(best_prod, best_score, 'difflib_auto')
            elif best_score >= MATCH_SUGGEST:
                return self._result(best_prod, best_score, 'difflib_suggest')

        return {'product': False, 'account': False, 'tax_ids': False,
                'uom': False, 'confidence': 0.0, 'source': 'none'}

    def _result(self, product, confidence, source):
        return {
            'product':    product,
            'account':    False,
            'tax_ids':    False,
            'uom':        False,
            'confidence': confidence,
            'source':     source,
        }

    # ═══════════════════════════════════════════════════════════════════════
    # FAZ 3: Kural Motoru
    # ═══════════════════════════════════════════════════════════════════════

    def _apply_supplier_rules(self, supplier_id, description):
        """
        FAZ 3 — Tedarikçi bazlı metin normalleştirme kuralları.

        Örnek kurallar:
          - "TR- " öneki → kaldır
          - "ADET" / "KG" soneki → kaldır
          - Çoklu boşluk → tek boşluk
          - Büyük harf normalize

        Kural tablosu şu an hardcoded; ilerleyen versiyonda
        DB'ye (efatura.supplier.rule) taşınabilir.

        Returns: normalleştirilmiş açıklama (str)
        """
        if not description:
            return description

        text = description.strip()

        # Genel normalleştirme
        import re
        text = re.sub(r'\s+', ' ', text)           # Çoklu boşluk
        text = re.sub(r'\s*-\s*$', '', text)       # Sondaki tire
        text = text.strip()

        # Tedarikçi özel kural yoksa direkt döndür
        if not supplier_id:
            return text

        # Tedarikçi bazlı prefix/suffix kuralları
        # Not: Gerçek uygulamada bu kurallar bir DB tablosunda tutulur
        supplier = self.env['res.partner'].browse(supplier_id)
        vkn = supplier.vat or ''

        # Örnek: "TR-" prefix'ini kaldır (bazı tedarikçiler ürün kodunu önüne koyar)
        if text.upper().startswith('TR-'):
            text = text[3:].strip()

        # Örnek: Parantez içindeki kodu kaldır — "ÜRÜN ADI (TR123)" → "ÜRÜN ADI"
        text = re.sub(r'\s*\([A-Z0-9\-]+\)\s*$', '', text).strip()

        return text

    # ═══════════════════════════════════════════════════════════════════════
    # Yardımcı Eşlemeler
    # ═══════════════════════════════════════════════════════════════════════

    def find_tax(self, tax_percent, company):
        """Vergi oranı ile Odoo alış vergisi bul."""
        if not tax_percent:
            return False
        return self.env['account.tax'].search([
            ('amount', '=', tax_percent),
            ('type_tax_use', '=', 'purchase'),
            ('company_id', '=', company.id),
            ('active', '=', True),
        ], limit=1)

    def find_uom(self, ubl_code):
        """UBL birim kodu ile Odoo UoM bul."""
        if not ubl_code:
            return False
        return self.env['uom.uom'].search(
            [('x_ubl_code', '=', ubl_code)], limit=1
        )

    def find_expense_account(self, company):
        """Ürün eşleşemezse genel gider hesabı."""
        return self.env['account.account'].search([
            ('company_id', '=', company.id),
            ('account_type', '=', 'expense'),
            ('deprecated', '=', False),
        ], limit=1)
