"""Strict JAN / EAN barcode extraction for product scrape auto-fill.

Accepts only well-formed retail barcodes so random analytics IDs
(e.g. BASE page shared numbers) are not treated as JAN.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from bs4 import BeautifulSoup

# Japan retail JAN-13 commonly starts with 45 or 49.
# Also allow EAN-13 from other regions when check digit + label are strong.
_JP_PREFIXES = ("45", "49")

# Digits only after normalization (hyphens / spaces removed).
_DIGIT_RE = re.compile(r"^\d{8}$|^\d{13}$")

# Labeled JAN in text / HTML (capture group = candidate digits with optional separators).
_LABELED_JAN_RE = re.compile(
    r"(?:"
    r"JAN(?:\s*コード|\s*ｺｰﾄﾞ|\s*Code|\s*CODE)?"
    r"|バーコード|ﾊﾞｰｺｰﾄﾞ|Barcode|BARCODE"
    r"|GTIN(?:-?13|-?8)?"
    r"|EAN(?:-?13|-?8)?"
    r")"
    r"\s*[:：]?\s*"
    r"([0-9][0-9\-\s]{6,20}[0-9])",
    re.IGNORECASE,
)

# JSON-LD / meta product identifiers.
_GTIN_KEYS = (
    "gtin13",
    "gtin8",
    "gtin",
    "gtin14",
    "isbn",
    "ean",
    "jan",
)


def normalize_jan_digits(value: str) -> str:
    return re.sub(r"[\s\-]", "", (value or "").strip())


def _ean_check_digit(body: str) -> str:
    """Compute EAN/JAN check digit for an 7- or 12-digit body."""
    total = 0
    # Weights from the right: odd positions ×3, even ×1 (1-based from right).
    for i, ch in enumerate(reversed(body)):
        n = int(ch)
        total += n * 3 if i % 2 == 0 else n
    return str((10 - (total % 10)) % 10)


def is_valid_jan(value: str, *, require_jp_prefix: bool = False) -> bool:
    """True if value is a valid JAN-8 / JAN-13 (EAN check digit)."""
    digits = normalize_jan_digits(value)
    if not _DIGIT_RE.fullmatch(digits):
        return False
    if len(digits) == 13 and require_jp_prefix and not digits.startswith(_JP_PREFIXES):
        return False
    body, check = digits[:-1], digits[-1]
    return _ean_check_digit(body) == check


def canonicalize_jan(value: str, *, require_jp_prefix: bool = False) -> Optional[str]:
    digits = normalize_jan_digits(value)
    if len(digits) == 12 and digits.isdigit():
        # UPC-A → EAN-13 with leading zero (common in Shopify barcodes).
        digits = "0" + digits
    if is_valid_jan(digits, require_jp_prefix=require_jp_prefix):
        return digits
    return None


def _pick_best(candidates: list[str]) -> Optional[str]:
    """Prefer Japan-prefix JAN-13, then any valid 13, then 8."""
    normalized: list[str] = []
    for raw in candidates:
        jan = canonicalize_jan(raw, require_jp_prefix=False)
        if jan and jan not in normalized:
            normalized.append(jan)
    if not normalized:
        return None
    jp13 = [j for j in normalized if len(j) == 13 and j.startswith(_JP_PREFIXES)]
    if jp13:
        return jp13[0]
    d13 = [j for j in normalized if len(j) == 13]
    if d13:
        return d13[0]
    return normalized[0]


def _from_json_ld_node(node: Any, out: list[str]) -> None:
    if isinstance(node, list):
        for item in node:
            _from_json_ld_node(item, out)
        return
    if not isinstance(node, dict):
        return
    for key in _GTIN_KEYS:
        val = node.get(key)
        if isinstance(val, (str, int)):
            out.append(str(val))
    for nested_key in ("offers", "itemOffered", "product", "mainEntity"):
        if nested_key in node:
            _from_json_ld_node(node[nested_key], out)


def extract_jan_from_json_ld(soup: BeautifulSoup) -> Optional[str]:
    import json

    candidates: list[str] = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            # Fall back to regex on malformed JSON-LD.
            for key in _GTIN_KEYS:
                for m in re.finditer(
                    rf'"{key}"\s*:\s*"?(?P<v>\d[\d\-\s]{{6,20}}\d)"?',
                    raw,
                    flags=re.I,
                ):
                    candidates.append(m.group("v"))
            continue
        _from_json_ld_node(data, candidates)
        # Regex backup for string values nested oddly.
        for key in _GTIN_KEYS:
            for m in re.finditer(
                rf'"{key}"\s*:\s*"?(?P<v>\d[\d\-\s]{{6,20}}\d)"?',
                raw,
                flags=re.I,
            ):
                candidates.append(m.group("v"))
    return _pick_best(candidates)


def extract_jan_from_meta(soup: BeautifulSoup) -> Optional[str]:
    candidates: list[str] = []
    for key in ("product:retailer_item_id", "og:upc", "product:upc", "barcode", "gtin"):
        tag = soup.find("meta", attrs={"property": key}) or soup.find(
            "meta", attrs={"name": key}
        )
        if tag and tag.get("content"):
            candidates.append(str(tag["content"]))
    return _pick_best(candidates)


def extract_jan_from_labeled_text(text: str) -> Optional[str]:
    candidates = [m.group(1) for m in _LABELED_JAN_RE.finditer(text or "")]
    return _pick_best(candidates)


def extract_jan_from_definition_lists(soup: BeautifulSoup) -> Optional[str]:
    """dt/dd or th/td rows labeled JAN / バーコード."""
    candidates: list[str] = []
    label_re = re.compile(
        r"^(?:JAN(?:\s*コード|\s*ｺｰﾄﾞ|\s*Code)?|バーコード|ﾊﾞｰｺｰﾄﾞ|Barcode|GTIN(?:-?13|-?8)?|EAN(?:-?13|-?8)?)\s*[:：]?$",
        re.IGNORECASE,
    )
    for dt in soup.find_all("dt"):
        if not label_re.match(dt.get_text(" ", strip=True)):
            continue
        dd = dt.find_next_sibling("dd")
        if dd:
            candidates.append(dd.get_text(" ", strip=True))
    for cell in soup.find_all(["th", "td"]):
        label = cell.get_text(" ", strip=True)
        if label_re.match(label):
            sibling = cell.find_next_sibling(["td", "th"])
            if sibling:
                candidates.append(sibling.get_text(" ", strip=True))
        # Same cell: "JANコード：490123..."
        if len(label) <= 48:
            candidates.extend(m.group(1) for m in _LABELED_JAN_RE.finditer(label))
    return _pick_best(candidates)


def extract_jan_from_shopify_product(item: dict[str, Any]) -> Optional[str]:
    candidates: list[str] = []
    for variant in item.get("variants") or []:
        if not isinstance(variant, dict):
            continue
        for key in ("barcode", "sku"):
            val = variant.get(key)
            if val is None:
                continue
            text = str(val).strip()
            # SKU is often not JAN; only accept if it validates as JAN.
            jan = canonicalize_jan(text, require_jp_prefix=False)
            if jan:
                candidates.append(jan)
    # body_html labeled JAN
    body = str(item.get("body_html") or "")
    if body:
        text = BeautifulSoup(body, "html.parser").get_text(" ", strip=True)
        labeled = extract_jan_from_labeled_text(text)
        if labeled:
            candidates.append(labeled)
    return _pick_best(candidates)


def extract_jan_from_html(html: str, soup: Optional[BeautifulSoup] = None) -> Optional[str]:
    """
    Extract a single best JAN from a product page.

    Priority:
      1) JSON-LD / meta gtin*
      2) Labeled table / definition list rows
      3) Labeled text patterns (JANコード：…)
    Never picks unlabeled bare 13-digit runs (avoids analytics IDs).
    """
    soup = soup or BeautifulSoup(html or "", "html.parser")
    for getter in (
        lambda: extract_jan_from_json_ld(soup),
        lambda: extract_jan_from_meta(soup),
        lambda: extract_jan_from_definition_lists(soup),
        lambda: extract_jan_from_labeled_text(soup.get_text(" ", strip=True)),
    ):
        try:
            found = getter()
        except Exception:
            found = None
        if found:
            return found
    return None


def extract_jan_near_product_name(text: str, product_name: str) -> Optional[str]:
    """
    For order-history pages: JAN often appears as Name (4582764...) nearby.
    Only accept parenthetical 13/8-digit with valid check digit.
    """
    if not text or not product_name:
        return None
    # Prefer pattern: product name ... (digits)
    escaped = re.escape(product_name[:40])
    m = re.search(
        rf"{escaped}.{{0,120}}?\((\d{{8}}|\d{{13}})\)",
        text,
        flags=re.DOTALL,
    )
    if m:
        return canonicalize_jan(m.group(1))
    # Generic: any labeled JAN in the same blob
    return extract_jan_from_labeled_text(text)
