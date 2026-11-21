"""MakeShop / store-gk.com 注文履歴 HTML parser.

Page template: templates/store-gk.com.order-history.md
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.release_date import map_release_to_expected_ship

SHOP = "store-gk.com"
BASE = "https://www.store-gk.com/"

# CDN shop id or host text -> public shop. Order pages often omit the domain.
_MAKESHOP_SHOPS: tuple[dict[str, str], ...] = (
    {
        "shop": "shop.twincre.com",
        "base": "https://shop.twincre.com/",
        "label": "ツインクル",
        "markers": "twincre",
    },
    {
        "shop": "the-chara.com",
        "base": "https://www.the-chara.com/",
        "label": "THEキャラ",
        "markers": "thechara55,the-chara.com",
    },
    {
        "shop": "store-gk.com",
        "base": "https://www.store-gk.com/",
        "label": "store-gk",
        "markers": "store-gk.com,gokurakuyu,gk store",
    },
)


def load_html_bytes(raw: bytes) -> str:
    """Decode browser-saved MakeShop HTML.

    These pages declare EUC-JP but often contain a few illegal bytes, so a
    strict decode fails. Scoring replacement-decoded candidates avoids writing
    mojibake product names into the DB.
    """
    candidates: list[tuple[int, str]] = []
    for enc in ("euc_jp", "cp932", "shift_jis", "utf-8", "utf-8-sig"):
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            text = raw.decode(enc, errors="replace")
        score = 0
        for marker in ("注文番号", "送料", "合計", "消費税", "発送", "円"):
            score += text.count(marker) * 10
        score -= text.count("\ufffd") * 3
        candidates.append((score, text))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def load_html_path(path: str | Path) -> str:
    return load_html_bytes(Path(path).read_bytes())


def _parse_int_amount(text: str) -> Optional[float]:
    cleaned = (text or "").replace("\xa0", " ").replace(",", "").strip()
    m = re.search(r"(\d+(?:\.\d+)?)", cleaned)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _brand_id_from_href(href: str) -> str:
    m = re.search(r"shopdetail/(\d+)/?", href or "")
    return m.group(1) if m else ""


def _guess_ship_from_name(name: str, ordered_year: Optional[int]) -> tuple[Optional[str], Optional[str]]:
    # e.g. 「2026年10月発送」「2026年10月中旬…発送」
    dated = re.search(
        r"(\d{4})年\s*(\d{1,2})月\s*(上旬|中旬|下旬)?.{0,16}発送",
        name or "",
    )
    if dated:
        period = {"上旬": "early", "中旬": "mid", "下旬": "late"}.get(dated.group(3) or "")
        return f"{int(dated.group(1)):04d}-{int(dated.group(2)):02d}", period
    # e.g. 「7月中旬頃以降発送」
    m = re.search(r"(\d{1,2})月\s*(上旬|中旬|下旬)", name)
    if not m:
        return None, None
    year = ordered_year or 2026
    month = int(m.group(1))
    period = {"上旬": "early", "中旬": "mid", "下旬": "late"}[m.group(2)]
    return f"{year:04d}-{month:02d}", period


def _ordered_year(text: str) -> Optional[int]:
    m = re.search(r"(\d{4})年", text or "")
    return int(m.group(1)) if m else None


def detect_makeshop_order_shop(html: str) -> Optional[dict[str, str]]:
    text = html or ""
    if "orderBlock" not in text or "注文番号" not in text or "orderList" not in text:
        return None
    lower = text.lower()
    for shop in _MAKESHOP_SHOPS:
        if any(marker in lower for marker in shop["markers"].split(",")):
            return shop
    return None


def _line_from_row(row: Tag, base: str = BASE) -> Optional[dict[str, Any]]:
    item = row.select_one("dl.orderItem")
    if not item:
        return None
    cells = row.find_all("td", recursive=False)
    if len(cells) < 6:
        return None

    name = ""
    source_url = ""
    brand_id = ""
    # Prefer dd product link; skip 再購入 / empty image anchors.
    candidates: list[str] = []
    for a in item.select("dd a, a"):
        text = a.get_text(" ", strip=True)
        href = str(a.get("href") or "")
        bid = _brand_id_from_href(href)
        if bid:
            brand_id = bid
            source_url = urljoin(base, f"shopdetail/{bid}/")
        if not text:
            continue
        if text in ("再購入", "再購入不可", "詳細") or text.startswith("再購入"):
            continue
        if "sendReorder" in href:
            continue
        candidates.append(text)
    if candidates:
        # MakeShop sometimes duplicates "short - long【brand】"; keep shorter head.
        name = candidates[-1]
        if " - " in name:
            head, tail = name.split(" - ", 1)
            if len(head) >= 8 and ("グッズ" in head or "発送" in head):
                name = head.strip()
    if not name:
        return None

    unit_raw = _parse_int_amount(cells[2].get_text(" ", strip=True))
    qty_raw = _parse_int_amount(cells[3].get_text(" ", strip=True))
    qty = max(1, int(qty_raw or 1))
    sub_text = cells[5].get_text(" ", strip=True)
    subtotal_raw = _parse_int_amount(sub_text)
    # store-gk / THEキャラ の単価は税抜。ツインクルは小計に（税込）と書いてある。
    tax_included = "税込" in sub_text

    unit_cost: Optional[float] = None
    if unit_raw is not None:
        unit_cost = float(unit_raw) if tax_included else round(unit_raw * 1.1, 2)
    elif subtotal_raw is not None:
        unit_cost = (
            round(subtotal_raw / qty, 2)
            if tax_included
            else round(subtotal_raw * 1.1 / qty, 2)
        )

    image_url = ""
    for img in item.select("img[src]"):
        src = str(img.get("src") or "").strip()
        if not src or "none_image" in src:
            continue
        if src.startswith("http://") or src.startswith("https://"):
            image_url = src
            break
    return {
        "name": name,
        "qty": qty,
        "unit_cost": unit_cost,
        "image_url": image_url,
        "source_url": source_url,
        "brand_id": brand_id,
        "tax_included": tax_included,
    }


def is_storegk_order_history_html(html: str) -> bool:
    """MakeShop 注文履歴 for known shops (store-gk, THEキャラ)."""
    return detect_makeshop_order_shop(html) is not None


def parse_order_history_html(
    html: str,
    *,
    order_ref: Optional[str] = None,
) -> list[dict[str, Any]]:
    shop_info = detect_makeshop_order_shop(html)
    if shop_info is None:
        return []
    shop = shop_info["shop"]
    base = shop_info["base"]
    label = shop_info["label"]
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, Any]] = []

    for block in soup.select("div.orderBlock"):
        num_dd = block.select_one("dl.orderNum dd")
        if not num_dd:
            continue
        ref = num_dd.get_text(" ", strip=True)
        if order_ref and ref != order_ref:
            continue

        status_text = ""
        st = block.select_one("p.orderStatus")
        if st:
            status_text = st.get_text(" ", strip=True)

        ordered_at = ""
        day = block.select_one("dl.orderDaytime dd")
        if day:
            ordered_at = day.get_text(" ", strip=True)
        year = _ordered_year(ordered_at)

        lines: list[dict[str, Any]] = []
        for row in block.select("table.orderList tbody tr"):
            classes = row.get("class") or []
            if "orderCharge" in classes or "orderTotal" in classes:
                continue
            line = _line_from_row(row, base)
            if line:
                lines.append(line)

        shipping_fee = None
        order_total = None
        for row in block.select("tr.orderCharge, tr.orderTotal"):
            row_label = row.get_text(" ", strip=True)
            amount = _parse_int_amount(row_label)
            if amount is None:
                continue
            if "送料" in row_label:
                shipping_fee = amount
            if "合計" in row_label:
                order_total = amount

        ship_at = None
        ship_period = None
        for line in lines:
            ship_at, ship_period = _guess_ship_from_name(line["name"], year)
            if ship_at:
                break
            ship_at, ship_period = map_release_to_expected_ship(None)

        results.append(
            {
                "order_ref": ref,
                "shop": shop,
                "shop_label": label,
                "status_text": status_text,
                "ordered_at": ordered_at,
                "shipping_fee": shipping_fee,
                "order_total": order_total,
                "expected_ship_at": ship_at,
                "expected_ship_period": ship_period,
                "unit_tax_included": bool(lines) and all(
                    line.get("tax_included") for line in lines
                ),
                "lines": [
                    {
                        "name": line["name"],
                        "qty": line["qty"],
                        "unit_cost": line["unit_cost"],
                        "image_url": line["image_url"],
                        "source_url": line["source_url"],
                        "ip": "",
                        "expected_ship_at": ship_at,
                        "expected_ship_period": ship_period,
                    }
                    for line in lines
                ],
            }
        )
        if order_ref:
            break

    return results
