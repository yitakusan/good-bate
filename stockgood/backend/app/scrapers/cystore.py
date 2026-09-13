"""cystore.com（CyStore / Cygames）購入履歴詳細 HTML 解析。

粘贴「購入履歴詳細」整页源代码 → 多行商品 + 注文番号/送料/合计。
订单页通常无 JAN；商品 ID 取自图片路径 `/Contents/ProductImages/.../{pid}_L.jpg`。
相同 pid / 品名自动合并数量。

样例：templates/cystore.order-detail.fixture.html
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

SHOP = "cystore.com"
BASE = "https://cystore.com"

_YEN_RE = re.compile(r"[¥￥]\s*([\d,]+)|&#165;\s*([\d,]+)")
_PID_IN_IMG_RE = re.compile(
    r"/Contents/ProductImages/\d+/(\d+)_(?:L|M|S)\.(?:jpe?g|png|webp)",
    re.I,
)
_ODID_RE = re.compile(r"(?:odid|ODID)=([A-Z]{2}\d{8,})", re.I)
_ORDER_NO_RE = re.compile(r"(CS\d{8,})")


def is_cystore_url(url: str) -> bool:
    host = urlparse(url or "").netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host == "cystore.com" or host.endswith(".cystore.com")


def is_cystore_order_detail_html(html: str) -> bool:
    """Detect CyStore 購入履歴詳細 page (full source or main fragment)."""
    text = html or ""
    if not text:
        return False
    lower = text.lower()
    has_site = (
        "cystore.com" in lower
        or "cystore" in lower
        or "CyStore" in text
        or "サイストア" in text
    )
    has_page = (
        "購入履歴詳細" in text
        or "OrderHistoryDetail.aspx" in text
        or "orderhistorydetail" in lower
        or "odid=" in lower
    )
    has_items = "cartitem" in lower and (
        "単価（税込）" in text or "注文数" in text or "小計（税込）" in text
    )
    if has_items and (has_site or has_page):
        return True
    return has_site and has_page and ("cartitem" in lower or "ご注文番号" in text)


def _text(el: Optional[Tag]) -> str:
    if not el:
        return ""
    return el.get_text(" ", strip=True)


def _parse_yen(text: str) -> Optional[float]:
    m = _YEN_RE.search(text or "")
    if not m:
        return None
    raw = m.group(1) or m.group(2) or ""
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _abs_url(src: str) -> str:
    src = (src or "").strip()
    if not src:
        return ""
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return urljoin(BASE + "/", src.lstrip("/"))
    return src


def _dd_for_dt(soup: BeautifulSoup, labels: tuple[str, ...]) -> str:
    for dt in soup.find_all("dt"):
        label = dt.get_text(" ", strip=True)
        if any(label == lb or lb in label for lb in labels):
            dd = dt.find_next_sibling("dd")
            if dd:
                return dd.get_text(" ", strip=True)
    return ""


def extract_cystore_order_ref(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    from_dt = _dd_for_dt(soup, ("ご注文番号",))
    m = _ORDER_NO_RE.search(from_dt or "")
    if m:
        return m.group(1)
    m = _ODID_RE.search(html or "")
    if m:
        return m.group(1).upper()
    m = _ORDER_NO_RE.search(html or "")
    return m.group(1) if m else ""


def extract_cystore_shipping_fee(html: str) -> Optional[float]:
    soup = BeautifulSoup(html or "", "html.parser")
    raw = _dd_for_dt(soup, ("配送料金", "送料"))
    value = _parse_yen(raw)
    if value is not None:
        return value
    m = re.search(
        r"(?:配送料金|送料)[^¥￥&#]{0,40}(?:[¥￥]|&#165;)\s*([\d,]+)",
        html or "",
    )
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def extract_cystore_order_total(html: str) -> Optional[float]:
    soup = BeautifulSoup(html or "", "html.parser")
    raw = _dd_for_dt(soup, ("総合計（税込）", "総合計(税込)", "総合計"))
    value = _parse_yen(raw)
    if value is not None:
        return value
    m = re.search(
        r"総合計[（(]?税込[）)]?[^¥￥&#]{0,40}(?:[¥￥]|&#165;)\s*([\d,]+)",
        html or "",
    )
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def _product_id_from_img(src: str) -> str:
    m = _PID_IN_IMG_RE.search(src or "")
    return m.group(1) if m else ""


def _product_name(item: Tag) -> str:
    # CyStore markup sometimes uses typo attribute clas= instead of class=
    node = item.find(attrs={"clas": "cartitem__name"}) or item.select_one(
        ".cartitem__name"
    )
    name = _text(node)
    if name:
        return name
    area = item.select_one(".cartitem__namearea")
    if not area:
        return ""
    raw = area.get_text("\n", strip=True)
    for line in raw.splitlines():
        line = line.strip()
        if (
            not line
            or line.startswith("単価")
            or line.startswith("¥")
            or line.startswith("￥")
        ):
            continue
        return line
    return _text(area)


def _line_from_cartitem(item: Tag) -> Optional[dict[str, Any]]:
    name = _product_name(item)
    if not name:
        return None

    unit_cost: Optional[float] = None
    price_dd = item.select_one(
        ".cartitem__pricearea .cartitem__price, dd.cartitem__price, .cartitem__price"
    )
    if price_dd:
        unit_cost = _parse_yen(_text(price_dd))
    if unit_cost is None:
        for row in item.select(".cartitem__row, dl"):
            heading = _text(row.select_one("dt, .cartitem__itemheading"))
            if "単価" in heading:
                unit_cost = _parse_yen(
                    _text(row.select_one("dd, .cartitem__itemdetail"))
                )
                break

    qty = 1
    qty_dd = item.select_one(".cartitem__quantityarea .cartitem__itemdetail")
    qty_raw = _text(qty_dd)
    if qty_raw.isdigit():
        qty = max(1, int(qty_raw))
    else:
        for row in item.select(".cartitem__row, dl"):
            heading = _text(row.select_one("dt, .cartitem__itemheading"))
            if "注文数" in heading or heading == "数量":
                q = _text(row.select_one("dd, .cartitem__itemdetail"))
                if q.isdigit():
                    qty = max(1, int(q))
                break

    img = item.select_one("img[src], img[data-src]")
    image_src = ""
    if img:
        image_src = str(img.get("src") or img.get("data-src") or "")
    image_url = _abs_url(image_src)
    product_id = _product_id_from_img(image_src) or _product_id_from_img(image_url)
    source_url = (
        f"{BASE}/Form/Product/ProductDetail.aspx?pid={product_id}"
        if product_id
        else ""
    )

    return {
        "name": name,
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


def parse_cystore_order_detail_lines(html: str) -> list[dict[str, Any]]:
    """Parse raw order lines from CyStore 購入履歴詳細 HTML (before merge)."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    lines: list[dict[str, Any]] = []
    for item in soup.select(".cartitem, div.cartitem"):
        line = _line_from_cartitem(item)
        if line:
            lines.append(line)
    return lines


def merge_cystore_products(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def parse_cystore_order_detail_html(html: str) -> dict[str, Any]:
    """Parse CyStore order-detail HTML → products + order meta."""
    if not is_cystore_order_detail_html(html):
        return {
            "products": [],
            "order_ref": "",
            "shipping_fee": None,
            "order_total": None,
            "raw_line_count": 0,
        }
    lines = parse_cystore_order_detail_lines(html)
    products = merge_cystore_products(lines)
    return {
        "products": products,
        "order_ref": extract_cystore_order_ref(html),
        "shipping_fee": extract_cystore_shipping_fee(html),
        "order_total": extract_cystore_order_total(html),
        "raw_line_count": len(lines),
    }
