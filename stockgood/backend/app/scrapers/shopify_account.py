"""Shopify new customer-account order page (rendered DOM).

View-source is an empty #app shell. Paste the rendered order block:
h3 注文アイテム, div[role=row], 数量, ￥n/ユニット, 配送, 合計.
Unit price on the page is tax-inclusive. Variant text stays in the name so
same-title options do not merge. Shop host and 注文番号 are filled only when
the paste still contains them.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from bs4 import BeautifulSoup, Tag  # type: ignore[import-untyped]

_YEN_RE = re.compile(r"[¥￥]\s*([\d,]+)")
_UNIT_RE = re.compile(r"[¥￥]\s*([\d,]+)\s*/\s*ユニット")
_QTY_RE = re.compile(r"数量\s*([\d,]+)")
_ORDER_PAREN_RE = re.compile(r"注文\s*[（(]\s*(\d+)\s*[）)]")
_ORDER_HASH_RE = re.compile(r"注文\s*#\s*(\d+)")
_HOST_RE = re.compile(r"https?://([a-z0-9.-]+)", re.I)

_SKIP_HOST_SUFFIXES = (
    "shopify.com",
    "shopifycdn.com",
    "myshopify.com",
    "shopifycloud.com",
)


def is_shopify_customer_order_html(html: str) -> bool:
    text = html or ""
    if "注文アイテム" not in text:
        return False
    if 'role="row"' not in text and "role='row'" not in text:
        return False
    return "ユニット" in text or "注文合計" in text


def _parse_yen(text: str) -> Optional[float]:
    match = _YEN_RE.search(text or "")
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _shop_host(html: str) -> str:
    for match in _HOST_RE.finditer(html or ""):
        host = match.group(1).lower()
        if host.startswith("www."):
            host = host[4:]
        if any(host == suffix or host.endswith("." + suffix) for suffix in _SKIP_HOST_SUFFIXES):
            continue
        if "." not in host:
            continue
        return host
    return ""


def _order_ref(text: str) -> str:
    for pattern in (_ORDER_PAREN_RE, _ORDER_HASH_RE):
        match = pattern.search(text or "")
        if match:
            return match.group(1)
    return ""


def _items_table(soup: BeautifulSoup) -> Optional[Tag]:
    heading = None
    for h3 in soup.find_all("h3"):
        if "注文アイテム" in h3.get_text(" ", strip=True):
            heading = h3
            break
    if heading is None:
        return None
    heading_id = str(heading.get("id") or "")
    if heading_id:
        labelled = soup.find(attrs={"aria-labelledby": heading_id, "role": "table"})
        if isinstance(labelled, Tag):
            return labelled
    table = heading.find_next(attrs={"role": "table"})
    return table if isinstance(table, Tag) else None


def _line_from_row(row: Tag, shop: str) -> Optional[dict[str, Any]]:
    img = row.find("img")
    name = ""
    image_url = ""
    if isinstance(img, Tag):
        name = str(img.get("alt") or "").strip()
        image_url = str(img.get("src") or "").strip()
    qty = 1
    qty_match = _QTY_RE.search(row.get_text(" ", strip=True))
    if qty_match:
        try:
            qty = max(1, int(qty_match.group(1).replace(",", "")))
        except ValueError:
            qty = 1

    variant = ""
    unit_cost: Optional[float] = None
    for small in row.find_all("small"):
        text = small.get_text(" ", strip=True)
        if not text:
            continue
        unit_match = _UNIT_RE.search(text)
        if unit_match:
            try:
                unit_cost = float(unit_match.group(1).replace(",", ""))
            except ValueError:
                unit_cost = None
            continue
        if _parse_yen(text) is None and "数量" not in text:
            variant = text
    if not name:
        return None
    if variant and variant not in name:
        name = f"{name} ({variant})"
    return {
        "name": name,
        "shop": shop,
        "unit_cost": unit_cost,
        "image_url": image_url,
        "source_url": "",
        "ip": "",
        "barcode": "",
        "expected_ship_at": None,
        "expected_ship_period": None,
        "release_date": None,
        "qty": qty,
        "product_id": variant,
    }


def _money(soup: BeautifulSoup) -> tuple[Optional[float], Optional[float]]:
    fee: Optional[float] = None
    total: Optional[float] = None
    for row in soup.find_all(attrs={"role": "row"}):
        header = row.find(attrs={"role": "rowheader"})
        if not isinstance(header, Tag):
            continue
        label = header.get_text(" ", strip=True)
        cell = row.find(attrs={"role": "cell"})
        amount = _parse_yen(cell.get_text(" ", strip=True) if isinstance(cell, Tag) else "")
        if amount is None:
            continue
        if label.startswith("配送") and fee is None:
            fee = amount
        elif label == "合計" or (label.startswith("合計") and not label.startswith("小計")):
            total = amount
    return fee, total


def parse_shopify_customer_order_html(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html or "", "html.parser")
    shop = _shop_host(html or "")
    table = _items_table(soup)
    lines: list[dict[str, Any]] = []
    if table is not None:
        for row in table.find_all(attrs={"role": "row"}):
            if not isinstance(row, Tag):
                continue
            line = _line_from_row(row, shop)
            if line:
                lines.append(line)
    fee, total = _money(soup)
    page_text = soup.get_text(" ", strip=True)
    return {
        "products": lines,
        "raw_line_count": len(lines),
        "order_ref": _order_ref(page_text),
        "shipping_fee": fee,
        "order_total": total,
        "shop": shop,
    }
