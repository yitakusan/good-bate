"""BASE dynamic receipt page (c.thebase.in/dynamic_receipts).

Japanese and English labels share the same DOM: table.itemList,
span.itemList__titleClamp, p.itemList__additionalInfo, ul.chargeBreakdown.
The price column is the tax-inclusive unit price. Quantity is "N点" or "Nqty".
Variation text is appended to the name so two options of one /items/{id}
stay separate. Buyer name, address, phone, email, and tracking numbers
are not read.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag  # type: ignore[import-untyped]

_YEN_RE = re.compile(r"[¥￥]\s*([\d,]+)")
_QTY_RE = re.compile(r"(\d[\d,]*)\s*(?:点|qty)(?!\w)", re.I)
_HOST_SKIP = (
    "thebase.in",
    "thebase.com",
    "akamaized.net",
    "google.com",
    "googleapis.com",
    "gstatic.com",
    "doubleclick.net",
    "facebook.net",
    "twitter.com",
    "tiktok.com",
    "yahoo.co.jp",
    "amazon-adsystem.com",
)

_TOTAL_LABELS = {"合計金額", "total", "合計"}
_SHIP_LABELS = {"送料", "shipping fee", "配送料"}
_ORDER_LABELS = {"注文id", "order id"}
_NOTE_MARKERS = ("発送予定", "出荷予定", "expected shipping", "お届け予定")


def is_thebase_receipt_html(html: str) -> bool:
    text = html or ""
    if not text:
        return False
    lower = text.lower()
    if "dynamicreceipts" in lower or "dynamic_receipts" in lower:
        return True
    if "itemlist__titleclamp" not in lower and "itemlist__title" not in lower:
        return False
    return "x_uniquekey" in lower or "thebase" in lower or "点" in text or "qty" in lower


def _text(node: Optional[Tag]) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())


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
        return 0
    try:
        return max(1, int(match.group(1).replace(",", "")))
    except ValueError:
        return 0


def _host(url: str) -> str:
    raw = (url or "").strip()
    if not raw or raw.startswith("javascript:"):
        return ""
    if raw.startswith("//"):
        raw = "https:" + raw
    try:
        host = urlparse(raw).hostname or ""
    except ValueError:
        return ""
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        return ""
    if any(host == skip or host.endswith("." + skip) for skip in _HOST_SKIP):
        return ""
    return host


def _shop(soup: BeautifulSoup) -> str:
    for link in soup.select("table.itemList a.itemList__title, table.itemList a.itemList__imgContainer"):
        host = _host(str(link.get("href") or ""))
        if host:
            return host
    for link in soup.select(".drFooter a[href], footer a[href]"):
        host = _host(str(link.get("href") or ""))
        if host:
            return host
    shop_id = soup.select_one("#x_shop_id")
    if isinstance(shop_id, Tag):
        value = str(shop_id.get("value") or "").strip()
        if value:
            return value
    return ""


def _order_ref(soup: BeautifulSoup) -> str:
    key = soup.select_one("#x_uniqueKey")
    if isinstance(key, Tag):
        value = str(key.get("value") or "").strip()
        if value:
            return value
    for row in soup.select("table.orderInfoTable tr"):
        header = row.find("th")
        cell = row.find("td")
        if not isinstance(header, Tag) or not isinstance(cell, Tag):
            continue
        label = _text(header).lower()
        if label in _ORDER_LABELS:
            return _text(cell)
    return ""


def _labeled_amount(soup: BeautifulSoup, labels: set[str]) -> Optional[float]:
    for item in soup.select("ul.chargeBreakdown li.chargeBreakdown__item"):
        name_el = item.select_one(".chargeBreakdown__name")
        label = _text(name_el).lower()
        if label not in labels:
            continue
        amount = _parse_yen(item.get_text(" ", strip=True))
        if amount is not None:
            return amount
    for row in soup.select("table.orderInfoTable tr"):
        header = row.find("th")
        cell = row.find("td")
        if not isinstance(header, Tag) or not isinstance(cell, Tag):
            continue
        if _text(header).lower() not in labels:
            continue
        amount = _parse_yen(_text(cell))
        if amount is not None:
            return amount
    return None


def _variation(extra: str) -> str:
    text = (extra or "").strip().strip("()（）").strip()
    if not text:
        return ""
    folded = text.lower()
    if any(marker in folded or marker in text for marker in _NOTE_MARKERS):
        return ""
    return text


def _line_from_row(row: Tag, shop: str) -> Optional[dict[str, Any]]:
    item = row.select_one("td.itemList__item")
    if not isinstance(item, Tag):
        return None
    name = _text(item.select_one(".itemList__titleClamp"))
    extra = _variation(_text(item.select_one(".itemList__additionalInfo")))
    if extra and extra not in name:
        name = f"{name} ({extra})"
    if not name:
        return None
    link = item.select_one("a.itemList__title") or item.select_one("a.itemList__imgContainer")
    source_url = str(link.get("href") or "").strip() if isinstance(link, Tag) else ""
    img = item.select_one("img.itemList__img")
    image_url = str(img.get("src") or "").strip() if isinstance(img, Tag) else ""
    unit_cost: Optional[float] = None
    qty = 1
    for cell in row.find_all("td", recursive=False):
        classes = cell.get("class") or []
        if "itemList__item" in classes:
            continue
        text = _text(cell)
        if unit_cost is None:
            unit_cost = _parse_yen(text)
        parsed_qty = _parse_qty(text)
        if parsed_qty:
            qty = parsed_qty
    return {
        "name": name,
        "shop": _host(source_url) or shop,
        "unit_cost": unit_cost,
        "image_url": image_url,
        "source_url": source_url,
        "qty": qty,
        "ip": "",
        "barcode": "",
        "expected_ship_at": None,
        "expected_ship_period": None,
    }


def parse_thebase_receipt_html(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html or "", "html.parser")
    shop = _shop(soup)
    lines: list[dict[str, Any]] = []
    for row in soup.select("table.itemList tbody tr"):
        if not isinstance(row, Tag):
            continue
        line = _line_from_row(row, shop)
        if line:
            lines.append(line)
    if not shop:
        for line in lines:
            host = _host(str(line.get("source_url") or ""))
            if host:
                shop = host
                break
    return {
        "products": lines,
        "raw_line_count": len(lines),
        "order_ref": _order_ref(soup),
        "shipping_fee": _labeled_amount(soup, _SHIP_LABELS),
        "order_total": _labeled_amount(soup, _TOTAL_LABELS),
        "shop": shop,
    }
