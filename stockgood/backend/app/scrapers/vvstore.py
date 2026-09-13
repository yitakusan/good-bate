"""ヴィレッジヴァンガード公式通販 vvstore.jp 注文履歴詳細 HTML 解析。

粘贴「マイページ/ご注文履歴詳細」整页源代码 → 多行商品 + 注文番号/送料。
列表页无 JAN；相同商品 URL 自动合并数量。

模板说明：templates/vvstore.jp.order-history.md
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

SHOP = "vvstore.jp"
BASE = "https://vvstore.jp"

_PRICE_QTY_RE = re.compile(
    r"[￥¥]\s*([\d,]+)\s*[×xX✕]\s*(\d+)",
)
_YEN_RE = re.compile(r"[￥¥]\s*([\d,]+)")
_PRODUCT_ID_RE = re.compile(r"/products/detail/(\d+)", re.I)
_ORDER_NO_RE = re.compile(r"(?:ご注文番号|注文番号)\s*[:：]?\s*(\d{6,})", re.I)
_ORDER_NO_HREF_RE = re.compile(r"/mypage/receiptissue/(\d+)", re.I)


def is_vvstore_order_detail_html(html: str) -> bool:
    """Detect vvstore mypage order-history detail page (full or fragment)."""
    text = html or ""
    markers_site = ("vvstore.jp", "vvstore", "ヴィレッジヴァンガード", "Village Vanguard")
    markers_page = (
        "page_mypage_history",
        "page_mypage_history",
        "ご注文履歴詳細",
        "ec-orderRoleMyPageHistory",
        "ec-orderProduct__detailTitle",
        "ec-orderProduct__detailTitle",
        "ec-orderProduct__detailPrice",
        "ec-orderProduct__detailPrice",
    )
    has_site = any(m in text for m in markers_site)
    has_page = any(m in text for m in markers_page)
    has_cards = (
        ("ec-imageGrid" in text or "ec-imageGrid" in text)
        and (
            "ec-orderProduct__detailPrice" in text
            or "ec-orderProduct__detailPrice" in text
        )
    )
    if has_cards and (has_site or has_page or "購入商品" in text):
        return True
    return has_site and has_page


def _text(el: Optional[Tag]) -> str:
    if not el:
        return ""
    return el.get_text(" ", strip=True)


def _parse_yen(text: str) -> Optional[float]:
    m = _YEN_RE.search(text or "")
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_price_qty(text: str) -> tuple[Optional[float], int]:
    m = _PRICE_QTY_RE.search(text or "")
    if m:
        try:
            price = float(m.group(1).replace(",", ""))
        except ValueError:
            price = None
        return price, max(1, int(m.group(2)))
    price = _parse_yen(text)
    return price, 1


def _abs_url(src: str) -> str:
    src = (src or "").strip()
    if not src:
        return ""
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return urljoin(BASE + "/", src.lstrip("/"))
    return src


def _product_id_from_href(href: str) -> str:
    m = _PRODUCT_ID_RE.search(href or "")
    return m.group(1) if m else ""


def _stable_source_url(product_id: str, href: str = "") -> str:
    if product_id:
        return f"{BASE}/products/detail/{product_id}"
    href = (href or "").strip()
    if href.startswith("/"):
        return urljoin(BASE + "/", href.lstrip("/"))
    if href.startswith("http"):
        return href.split("?", 1)[0].split("#", 1)[0]
    return ""


def extract_vvstore_order_ref(html: str) -> str:
    text = html or ""
    m = _ORDER_NO_RE.search(text)
    if m:
        return m.group(1)
    m = _ORDER_NO_HREF_RE.search(text)
    if m:
        return m.group(1)
    soup = BeautifulSoup(text, "html.parser")
    for block in soup.select(".ec-definitions"):
        label = _text(block.select_one("dt"))
        if "注文番号" in label:
            value = _text(block.select_one("dd"))
            digits = re.sub(r"\D", "", value)
            if len(digits) >= 6:
                return digits
    return ""


def extract_vvstore_shipping_fee(html: str) -> Optional[float]:
    soup = BeautifulSoup(html or "", "html.parser")
    for dl in soup.select(
        "dl.ec-totalBox__spec, .ec-totalBox__spec, "
        "dl.ec-totalBox__spec, .ec-totalBox__spec"
    ):
        label = _text(dl.select_one("dt"))
        if label == "送料" or label.startswith("送料"):
            return _parse_yen(_text(dl.select_one("dd")))
    # Fallback: plain text near 送料
    m = re.search(r"送料\s*[：:]?\s*[￥¥]\s*([\d,]+)", html or "")
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def extract_vvstore_order_total(html: str) -> Optional[float]:
    soup = BeautifulSoup(html or "", "html.parser")
    price_el = soup.select_one(".ec-totalBox__price, .ec-totalBox__price")
    if price_el:
        return _parse_yen(_text(price_el))
    m = re.search(r"合計[^￥¥]*[￥¥]\s*([\d,]+)", html or "")
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def _line_from_grid(grid: Tag) -> Optional[dict[str, Any]]:
    title_a = grid.select_one(
        ".ec-orderProduct__detailTitle a[href], .ec-orderProduct__detailTitle a[href]"
    )
    title = (
        _text(title_a)
        if title_a
        else _text(
            grid.select_one(
                ".ec-orderProduct__detailTitle, .ec-orderProduct__detailTitle"
            )
        )
    )
    if not title:
        return None
    # Skip non-product rows if any
    if title in ("送料", "手数料"):
        return None

    href = ""
    if title_a:
        href = str(title_a.get("href") or "").strip()
    if not href:
        img_a = grid.select_one(
            ".ec-imageGrid__img a[href], .ec-imageGrid__img a[href]"
        )
        if img_a:
            href = str(img_a.get("href") or "").strip()

    product_id = _product_id_from_href(href)
    price_text = _text(
        grid.select_one(
            ".ec-orderProduct__detailPrice, .ec-orderProduct__detailPrice"
        )
    )
    unit_cost, qty = _parse_price_qty(price_text)

    image_url = ""
    img = grid.select_one(
        ".ec-imageGrid__img img[src], .ec-imageGrid__img img[src], img[src]"
    )
    if img:
        image_url = _abs_url(str(img.get("src") or ""))

    source_url = _stable_source_url(product_id, href)
    return {
        "name": title,
        "shop": SHOP,
        "unit_cost": unit_cost,
        "image_url": image_url,
        "source_url": source_url,
        "ip": "",
        "barcode": "",
        "expected_ship_at": None,
        "expected_ship_period": None,
        "release_date": None,
        "qty": qty,
        "product_id": product_id,
    }


def parse_vvstore_order_detail_lines(html: str) -> list[dict[str, Any]]:
    """Parse raw order lines from vvstore history-detail HTML (before merge)."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    lines: list[dict[str, Any]] = []
    # Prefer product block to avoid related-item carousels.
    root = soup.select_one(".ec-orderProduct, .ec-orderProduct") or soup
    for grid in root.select(".ec-imageGrid, .ec-imageGrid"):
        # Require price line so recommend widgets are skipped.
        if not grid.select_one(
            ".ec-orderProduct__detailPrice, .ec-orderProduct__detailPrice"
        ):
            continue
        line = _line_from_grid(grid)
        if line:
            lines.append(line)
    return lines


def merge_vvstore_products(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge duplicate SKUs by product_id / source_url / name → sum qty."""
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
            merged[key] = {
                "name": line.get("name") or "",
                "shop": line.get("shop") or SHOP,
                "unit_cost": line.get("unit_cost"),
                "image_url": line.get("image_url") or "",
                "source_url": line.get("source_url") or "",
                "ip": line.get("ip") or "",
                "barcode": line.get("barcode") or "",
                "expected_ship_at": line.get("expected_ship_at"),
                "expected_ship_period": line.get("expected_ship_period"),
                "release_date": line.get("release_date"),
                "qty": int(line.get("qty") or 1),
                "product_id": line.get("product_id") or "",
            }
            order.append(key)
            continue
        cur = merged[key]
        cur["qty"] = int(cur.get("qty") or 0) + int(line.get("qty") or 1)
        if cur.get("unit_cost") is None and line.get("unit_cost") is not None:
            cur["unit_cost"] = line["unit_cost"]
        if not cur.get("image_url") and line.get("image_url"):
            cur["image_url"] = line["image_url"]
    return [merged[k] for k in order]


def parse_vvstore_order_detail_html(html: str) -> dict[str, Any]:
    """Parse vvstore order-detail HTML → products + order meta."""
    if not is_vvstore_order_detail_html(html):
        return {
            "products": [],
            "order_ref": "",
            "shipping_fee": None,
            "order_total": None,
        }
    lines = parse_vvstore_order_detail_lines(html)
    products = merge_vvstore_products(lines)
    return {
        "products": products,
        "order_ref": extract_vvstore_order_ref(html),
        "shipping_fee": extract_vvstore_shipping_fee(html),
        "order_total": extract_vvstore_order_total(html),
        "raw_line_count": len(lines),
    }
