"""ecbeing 購入履歴詳細 HTML (movic.jp, store.kadokawa.co.jp).

Paste one logged-in 購入履歴詳細 page. The history list has no qty or unit price.
The detail table column 合計 is the line total; unit_cost = 合計 / 数量.
Prices are tax-inclusive. 送料 is the order shipping row; 手数料 stays out of shipping_fee.
A 13-digit 商品コード is used as JAN only when the check digit passes.
Do not read metatag:cart_item. That payload can be a different SKU.
Shipment tables repeat the same lines and are ignored.
The order page has no product image. The goods page main image is
img.js-img-source under /img/goods/L/, with og:image as fallback.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from bs4 import BeautifulSoup, Tag  # type: ignore[import-untyped]

from app.scrapers.jan import canonicalize_jan

SHOP = "movic.jp"
BASE = "https://www.movic.jp"

_YEN_RE = re.compile(r"([\d,]+)\s*円")
_DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_GOODS_HREF_RE = re.compile(r"/shop/g/g([^/?#]+)/?", re.I)


def is_movic_order_detail_html(html: str) -> bool:
    """Detect ecbeing 購入履歴詳細 (Movic or Kadokawa), not the list page."""
    text = html or ""
    if "block-purchase-history-detail--order-detail-items" not in text:
        return False
    if "block-purchase-history-detail--goods-qty" not in text:
        return False
    if "block-purchase-history-detail--goods-name" not in text:
        return False
    lower = text.lower()
    if (
        "kadokawa.co.jp" in lower
        or "movic.jp" in lower
        or "page-historydetail" in lower
        or "カドスト" in text
        or "ムービック" in text
        or "購入履歴詳細" in text
    ):
        return True
    return False


def _shop_and_base(html: str) -> tuple[str, str]:
    lower = (html or "").lower()
    if "kadokawa.co.jp" in lower or "カドスト" in (html or ""):
        return "store.kadokawa.co.jp", "https://store.kadokawa.co.jp"
    return SHOP, BASE


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
    digits = re.sub(r"[^\d]", "", text or "")
    if not digits:
        return 1
    try:
        return max(1, int(digits))
    except ValueError:
        return 1


def _iso_date(text: str) -> Optional[str]:
    match = _DATE_RE.search(text or "")
    if not match:
        return None
    year, month, day = (int(match.group(i)) for i in (1, 2, 3))
    return f"{year:04d}-{month:02d}-{day:02d}"


def _class_text(node: Optional[Tag]) -> str:
    """Class may sit on the tr (Movic) or on the td itself (Kadokawa)."""
    if node is None:
        return ""
    if node.name == "td":
        return _text(node)
    cell = node.find("td")
    return _text(cell) if cell else _text(node)


def _goods_url(code: str, href: str, base: str) -> str:
    href = (href or "").strip()
    if href.startswith("//"):
        href = "https:" + href
    if href.startswith("/"):
        href = base + href
    if href.startswith("http"):
        return href.split("?")[0]
    code = (code or "").strip()
    if not code:
        return ""
    return f"{base}/shop/g/g{code}/"


def _absolute_image(src: str, page_url: str) -> str:
    src = (src or "").strip()
    if not src or src.startswith("data:"):
        return ""
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("http://") or src.startswith("https://"):
        return src
    origin = re.match(r"https?://[^/]+", page_url or "")
    if origin and src.startswith("/"):
        return origin.group(0) + src
    return ""


def image_url_from_goods_page(html: str, page_url: str) -> str:
    """Main image on an ecbeing goods page. Skip banners and site logos."""
    soup = BeautifulSoup(html or "", "html.parser")
    candidates: list[str] = []
    for img in soup.select("img.js-img-source"):
        src = str(img.get("src") or "")
        if "/img/goods/" in src:
            candidates.append(src)
    og = soup.find("meta", attrs={"property": "og:image"})
    if og is not None:
        content = str(og.get("content") or "")
        if "/img/goods/" in content:
            candidates.append(content)

    def rank(src: str) -> int:
        if "/img/goods/L/" in src:
            return 0
        if "/img/goods/1/" in src:
            return 1
        return 2

    if not candidates:
        return ""
    return _absolute_image(sorted(candidates, key=rank)[0], page_url)


def _barcode_from_code(code: str) -> str:
    digits = re.sub(r"\D", "", code or "")
    if len(digits) != 13:
        return ""
    return canonicalize_jan(digits) or ""


def extract_movic_order_ref(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    value = _class_text(soup.select_one(".block-purchase-history-detail--order-id"))
    if value:
        return value
    match = re.search(r"order_id=([A-Za-z0-9-]+)", html or "")
    return match.group(1) if match else ""


_AMOUNT_CLASS = {
    "送料": "block-purchase-history-detail--shipping-fee",
    "手数料": "block-purchase-history-detail--fee",
    "支払金額合計": "block-purchase-history-detail--order-total",
    "注文金額合計": "block-purchase-history-detail--order-total",
}


def _payment_yen(soup: BeautifulSoup, labels: tuple[str, ...]) -> Optional[float]:
    """Order summary only. Shipment blocks reuse the shipping-fee class on tracking numbers."""
    for tr in soup.select(".block-purchase-history-detail--payment-info-items tr"):
        if _text(tr.find("th")) in labels:
            value = _parse_yen(_text(tr.find("td")))
            if value is not None:
                return value
    for label in labels:
        class_name = _AMOUNT_CLASS.get(label)
        if not class_name:
            continue
        for node in soup.select(f".{class_name}"):
            if (
                node.find_parent(class_="block-purchase-history-detail--shipment-item")
                is not None
            ):
                continue
            value = _parse_yen(_class_text(node))
            if value is not None:
                return value
    return None


def _line_from_row(row: Tag, shop: str, base: str) -> Optional[dict[str, Any]]:
    name = _text(row.select_one(".block-purchase-history-detail--goods-name"))
    if not name:
        return None
    variation = _text(row.select_one(".variation-name"))
    if variation and variation not in name:
        name = f"{name} {variation}"
    code = _text(row.select_one(".block-purchase-history-detail--goods-code"))
    link = row.select_one("a[href*='/shop/g/g']")
    href = str(link.get("href") or "") if link else ""
    if not code:
        match = _GOODS_HREF_RE.search(href)
        code = match.group(1) if match else ""
    qty = _parse_qty(_text(row.select_one(".block-purchase-history-detail--goods-qty")))
    line_total = _parse_yen(
        _text(row.select_one(".block-purchase-history-detail--goods-total-price"))
    )
    unit_cost = None
    if line_total is not None and qty > 0:
        unit_cost = round(line_total / qty, 2)
    return {
        "name": name,
        "shop": shop,
        "unit_cost": unit_cost,
        "image_url": "",
        "source_url": _goods_url(code, href, base),
        "ip": "",
        "barcode": _barcode_from_code(code),
        "expected_ship_at": None,
        "expected_ship_period": None,
        "release_date": None,
        "qty": qty,
        "product_id": code,
    }


def parse_movic_order_detail_lines(html: str) -> list[dict[str, Any]]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one(".block-purchase-history-detail--order-detail-items")
    if table is None:
        return []
    shop, base = _shop_and_base(html)
    lines: list[dict[str, Any]] = []
    for row in table.find_all("tr"):
        line = _line_from_row(row, shop, base)
        if line:
            lines.append(line)
    return lines


def _expected_ship(soup: BeautifulSoup) -> Optional[str]:
    row = soup.select_one(".block-purchase-history-detail--delivey-plan-dt")
    if row is None:
        return None
    return _iso_date(_text(row.find("td")))


def merge_movic_products(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for line in lines:
        key = (
            (line.get("product_id") or "").strip()
            or (line.get("source_url") or "").strip()
            or (line.get("name") or "").strip()
        )
        if not key:
            continue
        if key not in merged:
            merged[key] = dict(line)
            order.append(key)
            continue
        cur = merged[key]
        cur["qty"] = int(cur.get("qty") or 0) + int(line.get("qty") or 1)
        if cur.get("unit_cost") is None and line.get("unit_cost") is not None:
            cur["unit_cost"] = line["unit_cost"]
    return [merged[k] for k in order]


def parse_movic_order_detail_html(html: str) -> dict[str, Any]:
    empty = {
        "products": [],
        "order_ref": "",
        "shipping_fee": None,
        "order_total": None,
        "handling_fee": None,
        "raw_line_count": 0,
    }
    if not is_movic_order_detail_html(html):
        return empty
    soup = BeautifulSoup(html, "html.parser")
    lines = parse_movic_order_detail_lines(html)
    ship_at = _expected_ship(soup)
    if ship_at:
        for line in lines:
            line["expected_ship_at"] = ship_at
    return {
        "products": merge_movic_products(lines),
        "order_ref": extract_movic_order_ref(html),
        "shipping_fee": _payment_yen(soup, ("送料",)),
        "order_total": _payment_yen(soup, ("支払金額合計", "注文金額合計")),
        "handling_fee": _payment_yen(soup, ("手数料",)),
        "raw_line_count": len(lines),
    }
