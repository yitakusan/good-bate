"""online.aniplex.co.jp order detail (Demandware Order-Details).

Unit price is the tax-inclusive 単価. The line 合計 is qty times that price.
Product codes such as MD23-0440001 are not JAN codes.
Do not read the address, name, or phone block.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag  # type: ignore[import-untyped]

SHOP = "online.aniplex.co.jp"
BASE = "https://online.aniplex.co.jp/"
_PERIOD = {"上旬": "early", "中旬": "mid", "下旬": "late"}
_SKU_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{4,}$")
_SHIP_JA_RE = re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(上旬|中旬|下旬)?")
_SHIP_ISO_RE = re.compile(r"(\d{4})-(\d{2})-\d{2}")
_ORDER_RE = re.compile(r"注文番号\s*[:：]\s*([A-Za-z0-9-]+)")
_ORDER_QS_RE = re.compile(r"orderID=([A-Za-z0-9-]+)")


def is_aniplex_order_html(html: str) -> bool:
    text = html or ""
    if "product-summary__item" not in text:
        return False
    if "Order-Details" not in text and "orderID=" not in text:
        return False
    lower = text.lower()
    return (
        "aniplex" in lower
        or "sites-anx-site" in lower
        or "product-summary__item-unit-price" in text
    )


def _text(node: Optional[Tag]) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())


def _parse_qty(text: str) -> int:
    folded = (text or "").translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    digits = re.sub(r"\D", "", folded)
    return int(digits) if digits else 0


def _parse_yen(text: str) -> Optional[float]:
    folded = (text or "").translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    match = re.search(r"(\d[\d,]*)", folded)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _order_refs(soup: BeautifulSoup) -> list[str]:
    found: list[str] = []
    for page in soup.select("[data-querystring]"):
        match = _ORDER_QS_RE.search(str(page.get("data-querystring") or ""))
        if match:
            found.append(match.group(1))
    for title in soup.select("h1.page-title"):
        match = _ORDER_RE.search(_text(title))
        if match:
            found.append(match.group(1))
    if not found:
        match = _ORDER_RE.search(soup.get_text(" ", strip=True)[:4000])
        if match:
            found.append(match.group(1))
    unique: list[str] = []
    for ref in found:
        if ref not in unique:
            unique.append(ref)
    return unique


def _ship_from_text(text: str) -> tuple[Optional[str], Optional[str]]:
    match = _SHIP_JA_RE.search(text or "")
    if match:
        year, month, period = match.groups()
        return f"{int(year):04d}-{int(month):02d}", _PERIOD.get(period or "")
    iso = _SHIP_ISO_RE.search(text or "")
    if iso:
        return f"{iso.group(1)}-{iso.group(2)}", None
    return None, None


def _sku_and_ship(item: Tag) -> tuple[str, Optional[str], Optional[str]]:
    sku = ""
    ship_at: Optional[str] = None
    ship_period: Optional[str] = None
    for node in item.select(".product-summary__item-attributes .attribute"):
        label = _text(node)
        if not sku and _SKU_RE.fullmatch(label) and any(ch.isdigit() for ch in label):
            sku = label
            continue
        if ship_at is None:
            at, period = _ship_from_text(label)
            if at and "年" in label:
                ship_at, ship_period = at, period
    return sku, ship_at, ship_period


def _ip_from_name(name: str) -> str:
    for sep in (" / ", "／"):
        if sep in name:
            tail = name.split(sep)[-1].strip()
            if tail and not _SKU_RE.fullmatch(tail):
                return tail
    return ""


def _line_from_item(item: Tag) -> Optional[dict[str, Any]]:
    name = _text(item.select_one(".product-summary__item-attributes .product-summary__item-title"))
    if not name:
        name = _text(item.select_one(".product-summary__item-title"))
    if not name:
        return None
    sku, ship_at, ship_period = _sku_and_ship(item)
    image = item.select_one(".product-summary__item-image img[src]")
    image_url = ""
    if image is not None:
        src = str(image.get("src") or "").strip()
        if src:
            image_url = urljoin(BASE, src)
    unit = _parse_yen(_text(item.select_one(".product-summary__item-unit-price .price")))
    qty = _parse_qty(_text(item.select_one(".product-summary__item-quantity .value")))
    if qty < 1:
        qty = 1
    return {
        "name": name,
        "shop": SHOP,
        "unit_cost": unit,
        "image_url": image_url,
        "source_url": "",
        "ip": _ip_from_name(name),
        "barcode": "",
        "expected_ship_at": ship_at,
        "expected_ship_period": ship_period,
        "release_date": None,
        "qty": qty,
        "product_id": sku,
    }


def parse_aniplex_order_html(html: str) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "products": [],
        "order_ref": "",
        "shipping_fee": None,
        "order_total": None,
        "raw_line_count": 0,
        "multi": False,
    }
    if not is_aniplex_order_html(html):
        return empty
    soup = BeautifulSoup(html, "html.parser")
    refs = _order_refs(soup)
    if len(refs) > 1:
        empty["multi"] = True
        return empty
    lines: list[dict[str, Any]] = []
    for item in soup.select(".product-summary__item"):
        line = _line_from_item(item)
        if line:
            lines.append(line)
    fallback_at, fallback_period = _ship_from_text(_text(soup.select_one(".deliveryDate")))
    if fallback_at:
        for line in lines:
            if not line.get("expected_ship_at"):
                line["expected_ship_at"] = fallback_at
                line["expected_ship_period"] = fallback_period
    shipping = _parse_yen(_text(soup.select_one(".shipping-discount-total")))
    total = _parse_yen(_text(soup.select_one(".order-total .grand-total-sum")))
    if total is None:
        total = _parse_yen(_text(soup.select_one(".grand-total-sum")))
    return {
        "products": lines,
        "order_ref": refs[0] if refs else "",
        "shipping_fee": shipping,
        "order_total": total,
        "raw_line_count": len(lines),
        "multi": False,
    }
