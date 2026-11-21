"""Yahoo!ショッピング 注文履歴詳細 HTML.

Paste the logged-in order detail source (odhistory.shopping.yahoo.co.jp).
`.elPrice` is the tax-inclusive unit price; `.elNum` is quantity (`×N`).
Same item URL with a different option stays a separate line.
The order page has no JAN field. Image filenames are store item codes.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag  # type: ignore[import-untyped]

BASE = "https://store.shopping.yahoo.co.jp"

_YEN_RE = re.compile(r"([\d,]+)\s*円")
_QTY_RE = re.compile(r"[×xX*]\s*([\d,]+)")
_STORE_ITEM_RE = re.compile(
    r"store\.shopping\.yahoo\.co\.jp/([^/?#]+)/([^/?#]+)\.html",
    re.I,
)
_VARIANT_RE = re.compile(r"[:：]\s*(.+)$")


def is_yahoo_shopping_order_html(html: str) -> bool:
    """Detect Yahoo Shopping 注文履歴詳細 (full source or item fragment)."""
    text = html or ""
    if not text:
        return False
    has_items = "mdOrderItem" in text or "ご注文商品" in text
    has_line = "elPrice" in text and ("elNum" in text or "×" in text)
    has_order = "注文番号" in text or "elOrderNumber" in text
    if not (has_items and has_line and has_order):
        return False
    lower = text.lower()
    if "shopping.yahoo.co.jp" in lower or "odhistory" in lower:
        return True
    return "mdOrderItem" in text and "elOrderMainInfo" in text


def _text(el: Optional[Tag]) -> str:
    if not el:
        return ""
    return el.get_text(" ", strip=True)


def _parse_yen(text: str) -> Optional[float]:
    match = _YEN_RE.search(text or "")
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_qty(text: str) -> int:
    match = _QTY_RE.search(text or "")
    if not match:
        return 1
    try:
        return max(1, int(match.group(1).replace(",", "")))
    except ValueError:
        return 1


def _abs_url(src: str) -> str:
    src = (src or "").strip()
    if not src:
        return ""
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return urljoin(BASE + "/", src.lstrip("/"))
    return src


def _store_slug(href: str) -> str:
    match = _STORE_ITEM_RE.search(href or "")
    return match.group(1) if match else ""


def _variant_label(item: Tag) -> str:
    root = item.select_one(".elItemOptionExpand")
    if root is None:
        return ""
    parts: list[str] = []
    for node in root.select("p"):
        text = _text(node)
        if not text or text.startswith("発送目安"):
            continue
        parts.append(text)
    raw = " / ".join(parts).strip()
    if not raw:
        return ""
    match = _VARIANT_RE.search(raw)
    if match:
        return match.group(1).strip()
    return raw


def extract_yahoo_order_ref(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for node in soup.select(".elOrderNumber .elOrderList li"):
        raw = _text(node)
        if raw:
            return raw
    hidden = soup.select_one("input[name='h_oid']")
    if hidden:
        value = str(hidden.get("value") or "").strip()
        if value:
            return value
    return ""


def _receipt_amount(soup: BeautifulSoup, *, kind: str) -> Optional[float]:
    for dl in soup.select(".elTotalAmount dl, .mdOrderReceipt dl"):
        label = _text(dl.find("dt"))
        if not label:
            continue
        if kind == "shipping":
            if label == "送料" or label.startswith("送料"):
                return _parse_yen(_text(dl.find("dd")))
            continue
        if "商品合計" in label:
            continue
        if "合計金額" in label:
            value = _parse_yen(_text(dl.find("dd")))
            if value is not None:
                return value
    return None


def _line_from_item(item: Tag) -> Optional[dict[str, Any]]:
    link = item.select_one("dd.elName a[href], a[href*='.html']")
    href = str(link.get("href") or "") if link else ""
    name = ""
    name_el = item.select_one("dd.elName span, dd.elName a")
    if name_el:
        name = _text(name_el)
    if not name:
        img = item.select_one("img[alt]")
        name = str(img.get("alt") or "").strip() if img else ""
    if not name:
        return None

    price_el = item.select_one(".elPrice")
    qty_el = item.select_one(".elNum")
    unit_cost = _parse_yen(_text(price_el)) if price_el else None
    qty = _parse_qty(_text(qty_el)) if qty_el else 1
    variant = _variant_label(item)
    if variant and variant not in name:
        name = f"{name} ({variant})"

    img = item.select_one("img[src]")
    image_src = str(img.get("src") or "") if img else ""
    source_url = _abs_url(href)
    return {
        "name": name,
        "shop": _store_slug(href),
        "unit_cost": unit_cost,
        "image_url": _abs_url(image_src),
        "source_url": source_url,
        "ip": "",
        "barcode": "",
        "expected_ship_at": None,
        "expected_ship_period": None,
        "release_date": None,
        "qty": qty,
        "product_id": "",
        "variant": variant,
    }


def parse_yahoo_shopping_order_lines(html: str) -> list[dict[str, Any]]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".mdOrderItem") or soup
    lines: list[dict[str, Any]] = []
    for item in root.select("ul.elList > li"):
        line = _line_from_item(item)
        if line:
            lines.append(line)
    return lines


def merge_yahoo_shopping_products(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Same item URL and option merge. Different options stay separate."""
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for line in lines:
        key = "|".join(
            [
                (line.get("source_url") or "").strip(),
                (line.get("variant") or "").strip(),
                (line.get("name") or "").strip(),
            ]
        )
        if key == "||":
            continue
        if key not in merged:
            copied = dict(line)
            copied.pop("variant", None)
            merged[key] = copied
            order.append(key)
            continue
        cur = merged[key]
        cur["qty"] = int(cur.get("qty") or 0) + int(line.get("qty") or 1)
        if cur.get("unit_cost") is None and line.get("unit_cost") is not None:
            cur["unit_cost"] = line["unit_cost"]
        if not cur.get("image_url") and line.get("image_url"):
            cur["image_url"] = line["image_url"]
    return [merged[k] for k in order]


def _store_name(soup: BeautifulSoup) -> str:
    node = soup.select_one(".mdStoreInfo .elName a, .mdOrderReceipt .elStore span")
    return _text(node)


def parse_yahoo_shopping_order_html(html: str) -> dict[str, Any]:
    empty = {
        "products": [],
        "order_ref": "",
        "shipping_fee": None,
        "order_total": None,
        "raw_line_count": 0,
        "store_name": "",
        "shop": "",
    }
    if not is_yahoo_shopping_order_html(html):
        return empty
    soup = BeautifulSoup(html, "html.parser")
    lines = parse_yahoo_shopping_order_lines(html)
    products = merge_yahoo_shopping_products(lines)
    shop = ""
    for line in lines:
        if line.get("shop"):
            shop = str(line["shop"])
            break
    return {
        "products": products,
        "order_ref": extract_yahoo_order_ref(html),
        "shipping_fee": _receipt_amount(soup, kind="shipping"),
        "order_total": _receipt_amount(soup, kind="total"),
        "raw_line_count": len(lines),
        "store_name": _store_name(soup),
        "shop": shop,
    }
