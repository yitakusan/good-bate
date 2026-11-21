"""gamers.co.jp（ゲーマーズ）注文履歴 HTML.

Paste one 注文 card. Line yen next to N点 is the line total; unit = total / qty.
Prices are tax-inclusive. 配送料・手数料 is shipping. Do not read お届け先 or 配送伝票番号.
The order image filename is not a JAN. JAN is 店舗予約用バーコード on the product page.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag  # type: ignore[import-untyped]

from app.scrapers.jan import canonicalize_jan, extract_jan_from_html

SHOP = "gamers.co.jp"
BASE = "https://www.gamers.co.jp"

_YEN_RE = re.compile(r"([\d,]+)\s*円")
_QTY_RE = re.compile(r"([\d,]+)\s*点")
_PD_RE = re.compile(r"/pd/(\d+)/?", re.I)
_ORDER_NO_RE = re.compile(r"注文番号\s*[:：]?\s*(\d{6,})")
_BARCODE_RE = re.compile(
    r"(?:店舗予約用)?バーコード\s*[:：]\s*(\d{8}|\d{13})"
)


def is_gamers_order_history_html(html: str) -> bool:
    text = html or ""
    if not text:
        return False
    lower = text.lower()
    if not (
        "tc-gamers" in lower
        or "gamers.co.jp" in lower
        or "ゲーマーズ" in text
    ):
        return False
    if "order_item" not in lower:
        return False
    return "注文番号" in text or "点" in text


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


def jan_from_gamers_product_html(html: str) -> str:
    """JAN from 店舗予約用バーコード. Image filenames are not barcodes."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select("#opener, #opener_sp, a.relation_keyword"):
        match = _BARCODE_RE.search(_text(node))
        if not match:
            continue
        jan = canonicalize_jan(match.group(1))
        if jan:
            return jan
    return extract_jan_from_html(html, soup) or ""


def _order_refs(html: str) -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    refs: list[str] = []
    blocks = soup.select(".order") or [soup]
    for block in blocks:
        match = _ORDER_NO_RE.search(_text(block))
        if match and match.group(1) not in refs:
            refs.append(match.group(1))
    if refs:
        return refs
    return [m.group(1) for m in _ORDER_NO_RE.finditer(html or "")][:1]


def _bill_amount(soup: BeautifulSoup, labels: tuple[str, ...]) -> Optional[float]:
    for tr in soup.select(".order_bill tr, table tr"):
        cells = tr.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        label = _text(cells[0])
        if label in labels:
            value = _parse_yen(_text(cells[1]))
            if value is not None:
                return value
    return None


def _line_from_order_item(item: Tag) -> Optional[dict[str, Any]]:
    classes = " ".join(item.get("class") or []).lower()
    if "privilege" in classes or "footer" in classes:
        return None
    link = item.select_one(".order_item_info a[href*='/pd/'], a[href*='/pd/']")
    href = str(link.get("href") or "") if link else ""
    name = _text(link)
    if not name:
        name = _text(item.select_one("h3"))
    if not name:
        return None
    qty = _parse_qty(_text(item.select_one(".num, .order_item_num")))
    line_amount = _parse_yen(_text(item.select_one(".price, .order_item_price")))
    if line_amount is None:
        line_amount = _parse_yen(_text(item.select_one(".order_item_info")))
    unit_cost = None
    if line_amount is not None and qty > 0:
        unit_cost = round(line_amount / qty, 2)
    img = item.select_one("img[src]")
    image_url = _abs_url(str(img.get("src") or "")) if img else ""
    product_id = ""
    match = _PD_RE.search(href)
    if match:
        product_id = match.group(1)
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


def parse_gamers_order_history_html(html: str) -> dict[str, Any]:
    empty = {
        "products": [],
        "order_ref": "",
        "shipping_fee": None,
        "order_total": None,
        "raw_line_count": 0,
    }
    if not is_gamers_order_history_html(html):
        return empty
    soup = BeautifulSoup(html, "html.parser")
    lines: list[dict[str, Any]] = []
    for item in soup.select(".order_item"):
        line = _line_from_order_item(item)
        if line:
            lines.append(line)
    refs = _order_refs(html)
    order_ref = refs[0] if len(refs) == 1 else ""
    return {
        "products": lines,
        "order_ref": order_ref,
        "shipping_fee": _bill_amount(soup, ("配送料・手数料", "配送料", "送料")),
        "order_total": _bill_amount(soup, ("注文合計金額", "ご請求金額")),
        "raw_line_count": len(lines),
    }


async def fill_gamers_barcodes(
    products: list[dict[str, Any]],
    fetch_html: Callable[[str], Awaitable[str]],
) -> int:
    """Load each product page and copy 店舗予約用バーコード when it is a valid JAN."""
    pending = [
        product
        for product in products
        if not (product.get("barcode") or "").strip()
        and (product.get("source_url") or "").strip()
    ]
    if not pending:
        return 0

    async def one(product: dict[str, Any]) -> str:
        url = str(product.get("source_url") or "")
        try:
            html = await fetch_html(url)
        except Exception:
            return ""
        return jan_from_gamers_product_html(html or "")

    codes = await asyncio.gather(*(one(product) for product in pending))
    filled = 0
    for product, code in zip(pending, codes):
        if code:
            product["barcode"] = code
            filled += 1
    return filled
