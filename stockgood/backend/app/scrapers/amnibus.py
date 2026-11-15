"""amnibus.com order card HTML (historyCard).

The price next to the quantity is the tax-inclusive unit price.
A blank price on a 景品 row is stored as 0.
Do not read the address or phone block.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from bs4 import BeautifulSoup, Tag  # type: ignore[import-untyped]

SHOP = "amnibus.com"
_PERIOD = {"上旬": "early", "中旬": "mid", "下旬": "late"}


def is_amnibus_order_html(html: str) -> bool:
    text = html or ""
    if "historyCardItemContainer" not in text:
        return False
    if "historyCard" not in text:
        return False
    lower = text.lower()
    return "amnibus.com" in lower or "注文番号" in text


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


def _order_ref(root: Tag) -> str:
    labeled = _text(root.select_one(".historyCardHeader__orderNumber"))
    match = re.search(r"注文番号[:：]\s*([A-Za-z0-9-]+)", labeled)
    if match:
        return match.group(1)
    match = re.search(r"注文番号[:：]\s*([A-Za-z0-9-]+)", root.get_text(" ", strip=True))
    return match.group(1) if match else ""


def _amounts(root: Tag) -> tuple[Optional[float], Optional[float], Optional[float]]:
    fee = root.select_one(".historyCardInfo__accordionContainer--fee") or root
    text = fee.get_text("\n", strip=True)
    sub = _labeled_amount(text, "小計")
    total = _labeled_amount(text, "合計")
    shipping = _labeled_amount(text, "送料")
    if shipping is None and sub is not None and total is not None and total >= sub:
        shipping = round(total - sub, 2)
    if total is None:
        total = _parse_yen(_text(root.select_one(".historyCardHeader__total--value")))
    return shipping, total, sub


def _labeled_amount(text: str, label: str) -> Optional[float]:
    match = re.search(rf"{label}[:：]\s*¥?\s*([\d,]+)", text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _expected_ship(root: Tag) -> tuple[Optional[str], Optional[str]]:
    block = root.select_one(".historyCardOrderStatus__deliverySchedule")
    if block is None:
        return None, None
    match = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(上旬|中旬|下旬)", _text(block))
    if not match:
        return None, None
    year, month, period = match.groups()
    return f"{int(year):04d}-{int(month):02d}", _PERIOD[period]


def _line_from_item(item: Tag) -> Optional[dict[str, Any]]:
    name = _text(item.select_one(".historyCardItemContainer__productName"))
    if not name:
        return None
    unit_label = _text(item.select_one(".historyCardItemContainer__detail--className"))
    kind = ""
    if "：" in unit_label or ":" in unit_label:
        kind = re.split(r"[:：]", unit_label, maxsplit=1)[-1].strip()
    if kind and kind not in name:
        name = f"{name} ({kind})"
    code_text = _text(item.select_one(".historyCardItemContainer__detail--productNumber"))
    code_match = re.search(r"(?:商品コード|景品コード)[:：]\s*([A-Za-z0-9_-]+)", code_text)
    code = code_match.group(1) if code_match else ""
    link = item.select_one("a[href*='/products/detail/']")
    href = str(link.get("href") or "").split("?")[0] if link else ""
    image = item.select_one("img[src]")
    image_url = str(image.get("src") or "").strip() if image else ""
    price_text = _text(item.select_one(".historyCardItemContainer__priceQuantity--price"))
    unit_cost = _parse_yen(price_text)
    if unit_cost is None:
        unit_cost = 0.0
    qty = _parse_qty(_text(item.select_one(".historyCardItemContainer__priceQuantity--quantity")))
    if qty < 1:
        qty = 1
    return {
        "name": name,
        "shop": SHOP,
        "unit_cost": unit_cost,
        "image_url": image_url,
        "source_url": href,
        "ip": _text(item.select_one(".historyCardItemContainer__detail--artworkTitle")),
        "barcode": "",
        "expected_ship_at": None,
        "expected_ship_period": None,
        "release_date": None,
        "qty": qty,
        "product_id": code,
    }


def _card_roots(soup: BeautifulSoup) -> list[Tag]:
    cards = soup.select("div.historyCard")
    return cards or [soup]


def parse_amnibus_order_html(html: str) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "products": [],
        "order_ref": "",
        "shipping_fee": None,
        "order_total": None,
        "raw_line_count": 0,
        "multi": False,
    }
    if not is_amnibus_order_html(html):
        return empty
    soup = BeautifulSoup(html, "html.parser")
    cards = _card_roots(soup)
    refs = [ref for ref in (_order_ref(card) for card in cards) if ref]
    if len(set(refs)) > 1:
        empty["multi"] = True
        return empty
    root = cards[0]
    lines: list[dict[str, Any]] = []
    for item in root.select(".historyCardItemContainer"):
        line = _line_from_item(item)
        if line:
            lines.append(line)
    ship_at, ship_period = _expected_ship(root)
    if ship_at:
        for line in lines:
            line["expected_ship_at"] = ship_at
            line["expected_ship_period"] = ship_period
    shipping, total, _sub = _amounts(root)
    return {
        "products": lines,
        "order_ref": _order_ref(root),
        "shipping_fee": shipping,
        "order_total": total,
        "raw_line_count": len(lines),
        "multi": False,
    }
