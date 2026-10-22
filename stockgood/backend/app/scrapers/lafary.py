"""lafary.shop（LAFARY ONLINE）Shopify 顾客注文详情 HTML 解析。

粘贴マイアカウント「注文 #xxxxx」整页源代码 → 多行商品 + 注文番号/送料/合计。
Prestige 主题：`table.order-summary` / `line-item`；单价取自 `sale-price`，数量取自同行
`td.text-center` 或「数量: N」。订单页通常无 JAN、无商品链接。相同品名自动合并数量。

样例：templates/lafary.shop.customers-order.fixture.html
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag  # type: ignore[import-untyped]

SHOP = "lafary.shop"
BASE = "https://www.lafary.shop"

_YEN_RE = re.compile(r"[¥￥]\s*([\d,]+)")
_ORDER_NO_RE = re.compile(r"注文\s*#\s*(\d+)")
_QTY_LABEL_RE = re.compile(r"数量\s*[:：]\s*([\d,]+)")
_PRODUCT_HANDLE_RE = re.compile(r"/products/([^/?#]+)", re.I)


def is_lafary_url(url: str) -> bool:
    host = urlparse(url or "").netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host == "lafary.shop" or host.endswith(".lafary.shop")


def is_lafary_order_html(html: str) -> bool:
    """Detect LAFARY ONLINE Shopify customers/order page."""
    text = html or ""
    if not text:
        return False
    lower = text.lower()
    has_site = (
        "lafary.shop" in lower
        or "lafary online" in lower
        or "lafaryshop.myshopify.com" in lower
    )
    has_page = (
        "order-summary" in lower
        and ("line-item" in lower or "customer-order" in lower)
    ) or (
        "account/orders" in lower
        and ("注文 #" in text or "に注文しました" in text)
    )
    has_items = ("¥" in text or "￥" in text) and (
        "sale-price" in lower or "order-summary__body" in lower
    )
    if has_items and has_site and has_page:
        return True
    return bool(has_site and has_page and has_items)


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


def _abs_url(src: str) -> str:
    src = (src or "").strip()
    if not src:
        return ""
    if src.startswith("//"):
        return "https:" + src
    return urljoin(BASE + "/", src)


def _product_id_from_href(href: str) -> str:
    m = _PRODUCT_HANDLE_RE.search(href or "")
    return m.group(1).strip() if m else ""


def _parse_order_ref(html: str, soup: BeautifulSoup) -> str:
    title = soup.find("title")
    for candidate in (_text(title), html[:8000]):
        m = _ORDER_NO_RE.search(candidate or "")
        if m:
            return m.group(1)
    h1 = soup.find(["h1", "h2", "h3"])
    if h1:
        m = _ORDER_NO_RE.search(_text(h1))
        if m:
            return m.group(1)
    return ""


def _parse_footer_amounts(soup: BeautifulSoup) -> tuple[Optional[float], Optional[float]]:
    fee: Optional[float] = None
    total: Optional[float] = None
    footer = soup.select_one("tfoot.order-summary__footer") or soup.select_one(
        "table.order-summary tfoot"
    )
    rows = footer.select("tr") if footer else []
    for row in rows:
        label = _text(row)
        amount = _parse_yen(label)
        if amount is None:
            continue
        if "送料" in label and fee is None:
            fee = amount
        elif "合計" in label or "合计" in label:
            total = amount
    return fee, total


def _line_from_row(row: Tag) -> Optional[dict[str, Any]]:
    line_item = row.select_one("line-item") or row.select_one(".line-item")
    if not line_item:
        return None

    name_el = line_item.select_one("p.h6") or line_item.select_one(".h6")
    name = _text(name_el)
    if not name:
        link = line_item.select_one("a[href*='/products/']")
        name = _text(link)
    if not name:
        return None

    unit_cost: Optional[float] = None
    sale = line_item.select_one("sale-price") or line_item.select_one(".sale-price")
    if sale:
        unit_cost = _parse_yen(_text(sale))
    if unit_cost is None:
        unit_cost = _parse_yen(_text(line_item))

    qty = 1
    qty_m = _QTY_LABEL_RE.search(_text(line_item))
    if qty_m:
        try:
            qty = max(1, int(qty_m.group(1).replace(",", "")))
        except ValueError:
            qty = 1
    else:
        cells = row.find_all("td", recursive=False)
        if len(cells) >= 2:
            try:
                qty = max(1, int(_text(cells[1]).replace(",", "")))
            except ValueError:
                pass

    href = ""
    link = line_item.select_one("a[href*='/products/']")
    if link:
        href = str(link.get("href") or "")
    product_id = _product_id_from_href(href)
    source_url = _abs_url(href) if href else ""

    img = line_item.select_one("img[src], img[data-src]")
    image_url = ""
    if img:
        image_url = _abs_url(str(img.get("src") or img.get("data-src") or ""))

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


def parse_lafary_order_lines(html: str) -> list[dict[str, Any]]:
    """Parse raw order lines from LAFARY customers/order HTML (before merge)."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    lines: list[dict[str, Any]] = []
    body = soup.select_one("tbody.order-summary__body")
    rows = body.find_all("tr", recursive=False) if body else []
    if not rows:
        rows = soup.select("table.order-summary tbody tr")
    for row in rows:
        line = _line_from_row(row)
        if line:
            lines.append(line)
    return lines


def merge_lafary_products(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        if not cur.get("source_url") and line.get("source_url"):
            cur["source_url"] = line["source_url"]
        if not cur.get("barcode") and line.get("barcode"):
            cur["barcode"] = line["barcode"]
        if not cur.get("product_id") and line.get("product_id"):
            cur["product_id"] = line["product_id"]
    return [merged[k] for k in order]


def parse_lafary_order_html(html: str) -> dict[str, Any]:
    """Parse LAFARY ONLINE customers/order HTML → products + order meta."""
    soup = BeautifulSoup(html or "", "html.parser")
    lines = parse_lafary_order_lines(html)
    products = merge_lafary_products(lines)
    fee, total = _parse_footer_amounts(soup)
    order_ref = _parse_order_ref(html or "", soup)
    return {
        "products": products,
        "raw_line_count": len(lines),
        "order_ref": order_ref,
        "shipping_fee": fee,
        "order_total": total,
    }
