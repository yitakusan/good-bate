"""animate-onlineshop.jp（アニメイト通販）注文履歴 HTML 解析。

粘贴マイページ「注文履歴」整页源代码（可含检索后的单笔注文）→ 多行商品 + 注文番号/送料/合计。
订单页通常无 JAN；商品 ID 取自链接 `/pd/{id}/`。
行内金额多为小计（点数 × 单价），入库单价 = 小计 / 点数。
特典块（.order_item_privilege）跳过。相同 pid / 品名自动合并数量。

样例：templates/animate-onlineshop.jp.order-history.fixture.html
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag  # type: ignore[import-untyped]

SHOP = "animate-onlineshop.jp"
BASE = "https://www.animate-onlineshop.jp"

_YEN_RE = re.compile(r"([\d,]+)\s*円")
_QTY_RE = re.compile(r"([\d,]+)\s*点")
_PD_RE = re.compile(r"/pd/(\d+)/?", re.I)
_ORDER_NO_RE = re.compile(r"注文番号\s*([0-9]{6,})")


def is_animate_url(url: str) -> bool:
    host = urlparse(url or "").netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host == "animate-onlineshop.jp" or host.endswith(
        ".animate-onlineshop.jp"
    )


def is_animate_order_history_html(html: str) -> bool:
    """Detect Animate 注文履歴 page (full source or main fragment)."""
    text = html or ""
    if not text:
        return False
    lower = text.lower()
    has_site = (
        "animate-onlineshop.jp" in lower
        or "techorus-cdn.com" in lower
        or "tc-animate" in lower
        or "アニメイト" in text
    )
    has_page = (
        "注文履歴" in text
        or "mypage/history" in lower
        or "order_histories" in lower
        or 'class="order"' in lower
        or "class='order'" in lower
    )
    has_items = (
        "order_item" in lower
        and ("注文番号" in text or "点" in text)
        and ("円" in text or "order_item_price" in lower)
    )
    if has_items and (has_site or has_page):
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


def _parse_qty(text: str) -> int:
    m = _QTY_RE.search(text or "")
    if not m:
        return 1
    try:
        return max(1, int(m.group(1).replace(",", "")))
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


def _product_id_from_href(href: str) -> str:
    m = _PD_RE.search(href or "")
    return m.group(1) if m else ""


def extract_animate_order_ref(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for node in soup.select(".order_id, .order-id, p.order_id"):
        raw = _text(node)
        m = _ORDER_NO_RE.search(raw)
        if m:
            return m.group(1)
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 6:
            return digits
    m = _ORDER_NO_RE.search(html or "")
    return m.group(1) if m else ""


def _bill_amount(soup: BeautifulSoup, labels: tuple[str, ...]) -> Optional[float]:
    for tr in soup.select(".order_bill tr, .order-bill tr, table tr"):
        cells = tr.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        label = _text(cells[0])
        if any(lb in label for lb in labels):
            value = _parse_yen(_text(cells[1]))
            if value is not None:
                return value
    return None


def extract_animate_shipping_fee(html: str) -> Optional[float]:
    soup = BeautifulSoup(html or "", "html.parser")
    value = _bill_amount(soup, ("配送料・手数料", "配送料", "送料"))
    if value is not None:
        return value
    m = re.search(
        r"(?:配送料・手数料|配送料|送料)[^\d]{0,40}([\d,]+)\s*円",
        html or "",
    )
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def extract_animate_order_total(html: str) -> Optional[float]:
    soup = BeautifulSoup(html or "", "html.parser")
    value = _bill_amount(soup, ("注文合計金額", "ご請求金額"))
    if value is not None:
        return value
    # Prefer explicit total over 商品小計.
    m = re.search(
        r"注文合計金額[^\d]{0,40}([\d,]+)\s*円",
        html or "",
    )
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def _line_from_order_item(item: Tag) -> Optional[dict[str, Any]]:
    classes = " ".join(item.get("class") or []).lower()
    if "privilege" in classes or "tokuten" in classes:
        return None
    if item.select_one(
        ".order_item_privilege_title, .order_item_privilege_name"
    ):
        return None

    link = item.select_one(
        ".order_item_info a[href*='/pd/'], a[href*='/pd/']"
    )
    href = str(link.get("href") or "") if link else ""
    name = _text(link)
    if not name:
        heading = item.select_one("h3, .order_item_info h3")
        name = _text(heading)
    if not name:
        return None

    qty = 1
    line_amount: Optional[float] = None
    for price_el in item.select(".order_item_price"):
        raw = _text(price_el)
        if "点" in raw:
            qty = _parse_qty(raw)
        elif "円" in raw:
            line_amount = _parse_yen(raw)

    if line_amount is None:
        # Fallback: any yen text in the item block.
        line_amount = _parse_yen(_text(item))

    unit_cost: Optional[float] = None
    if line_amount is not None and qty > 0:
        unit_cost = round(line_amount / qty, 2)

    img = item.select_one("img[src], img[data-src]")
    image_src = ""
    if img:
        image_src = str(img.get("src") or img.get("data-src") or "")
    image_url = _abs_url(image_src)
    product_id = _product_id_from_href(href)
    source_url = _abs_url(href) if href else ""
    if product_id and not source_url:
        source_url = f"{BASE}/pd/{product_id}/"

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


def parse_animate_order_history_lines(html: str) -> list[dict[str, Any]]:
    """Parse raw order lines from Animate 注文履歴 HTML (before merge)."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    lines: list[dict[str, Any]] = []
    items = soup.select(".order_item")
    if not items:
        # Some fragments wrap items without the shared class on the outer node.
        items = soup.select(".order_inner > div")
    for item in items:
        line = _line_from_order_item(item)
        if line:
            lines.append(line)
    return lines


def merge_animate_products(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def parse_animate_order_history_html(html: str) -> dict[str, Any]:
    """Parse Animate order-history HTML → products + order meta."""
    if not is_animate_order_history_html(html):
        return {
            "products": [],
            "order_ref": "",
            "shipping_fee": None,
            "order_total": None,
            "raw_line_count": 0,
        }
    lines = parse_animate_order_history_lines(html)
    products = merge_animate_products(lines)
    return {
        "products": products,
        "order_ref": extract_animate_order_ref(html),
        "shipping_fee": extract_animate_shipping_fee(html),
        "order_total": extract_animate_order_total(html),
        "raw_line_count": len(lines),
    }
