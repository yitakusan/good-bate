"""STORES（*.stores.jp）商品页 / マイページ注文解析。

商品页为 SSR（og / JSON-LD / h1.item_name）。httpx 常被 Cloudflare 403；
Windows 下用 curl.exe 拉取通常可过。仍可粘贴浏览器「查看网页源代码」。

注文详情：
1. 已渲染「購入詳細」HTML（含 .order_history_item）可直接粘贴 Elements 外层 HTML；
2. Ctrl+U 常为 SPA 空壳，可改贴 Network GET /web/customers/orders/{id} JSON。

行金额为小计（HTML: order_sales_payment_num / JSON: salesDetail.salesPayment），
单价=小计÷数量。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from typing import Any, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.scrapers.preview import (
    HEADERS,
    _clean_product_name,
    _extract_release_from_text,
    _meta,
    _parse_price_text,
    _product_dict,
)

_ITEM_ID_RE = re.compile(r"/items/([0-9a-f]{20,})", re.I)
_ORDER_ID_RE = re.compile(r"/mypage/orders/([0-9a-f]{20,})", re.I)
_RELEASE_FALLBACK_RE = re.compile(
    r"(?:(\d{4})年)?\s*(\d{1,2})月\s*(上旬|中旬|下旬|\d{1,2}日)?"
    r"[^。．\n\r]{0,40}発送",
)


def is_stores_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host == "stores.jp" or host.endswith(".stores.jp")


def item_id_from_url(url: str) -> Optional[str]:
    m = _ITEM_ID_RE.search(urlparse(url).path or "")
    return m.group(1) if m else None


def _fetch_stores_html_sync(url: str) -> Optional[str]:
    """httpx 常 403；curl 在本机通常可过 Cloudflare。"""
    import subprocess

    curl = "curl.exe" if os.name == "nt" else "curl"
    if not shutil.which(curl):
        return None
    try:
        completed = subprocess.run(
            [
                curl,
                "-sL",
                "--max-time",
                "40",
                "-A",
                HEADERS["User-Agent"],
                "-H",
                "Accept: text/html,application/xhtml+xml",
                "-H",
                f"Accept-Language: {HEADERS['Accept-Language']}",
                url,
            ],
            capture_output=True,
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0 or not completed.stdout:
        return None
    html = completed.stdout.decode("utf-8", errors="replace")
    if is_stores_captcha_html(html):
        return None
    return html


async def fetch_stores_html(url: str) -> Optional[str]:
    return await asyncio.to_thread(_fetch_stores_html_sync, url)


async def scrape_stores_product(url: str) -> Optional[dict[str, Any]]:
    html = await fetch_stores_html(url)
    if not html:
        return None
    return parse_stores_product_html(html, url)


def is_stores_captcha_html(html: str) -> bool:
    if not html:
        return False
    lower = html[:6000].lower()
    return (
        "captcha challenge - stores" in lower
        or "ロボットによる操作ではないことを確認します" in html[:6000]
        or "challenge-platform" in lower and "stores" in lower
    )


def is_stores_order_detail_html(html: str) -> bool:
    """マイページ「購入詳細」已渲染 HTML（含 .order_history_item）。"""
    if not html:
        return False
    if is_stores_captcha_html(html):
        return False
    lower = html.lower()
    if "order_history_item" not in lower and "order_item_name_bold" not in lower:
        return False
    if "購入詳細" in html or "order_history_detail" in lower:
        return True
    if "数量：" in html and "order_sales_payment_num" in lower:
        return True
    return "order_history_item" in lower and (
        "オーダー番号" in html or "order_total_num" in lower
    )


def is_stores_mypage_order_shell_html(html: str) -> bool:
    """Ctrl+U mypage order page: SPA shell without line items."""
    if not html:
        return False
    if is_stores_order_detail_html(html):
        return False
    lower = html[:12000].lower()
    if "stores.jp" not in lower and "storesjp" not in lower and "powered by stores" not in lower:
        # still allow STORE_ID / AUTH_TOKEN shell from user paste
        if "ng-app=\"storesjp\"" not in lower and "ng-app='storesjp'" not in lower:
            return False
    if "/mypage/orders/" not in lower and "購入履歴" not in html[:12000]:
        # user pasted order detail shell
        if "mypage/orders" not in lower and 'id="mypage"' not in lower:
            return False
    # Has router-view / mypage but no order line DOM
    if "router-view" in lower or 'id="mypage"' in lower or "sj-account-menu" in lower:
        if "order_history_item" not in lower and "order_item_name" not in lower:
            if "salesdetail" not in lower and '"deliveries"' not in lower:
                return True
    return False


def is_stores_product_html(html: str) -> bool:
    if not html:
        return False
    lower = html[:12000].lower()
    if "stores.jp" not in lower and "storesjp" not in lower:
        return False
    if is_stores_captcha_html(html):
        return False
    if is_stores_order_detail_html(html):
        return False
    if is_stores_mypage_order_shell_html(html):
        return False
    return (
        'class="item_name"' in html
        or "data-item-id=" in html
        or "/items/" in lower
        and ("og:title" in lower or "application/ld+json" in lower)
    )


def _yen_amount(text: str) -> Optional[float]:
    return _parse_price_text(text or "")


def _unwrap(raw: Any) -> Any:
    if isinstance(raw, dict) and "data" in raw and (
        "code" in raw or "msg" in raw or "status" in raw
    ):
        return raw.get("data")
    return raw


def looks_like_stores_order_json(text: str) -> bool:
    raw = (text or "").strip()
    if not raw.startswith("{"):
        return False
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return False
    payload = _unwrap(data)
    if not isinstance(payload, dict):
        return False
    if not (
        payload.get("number")
        or payload.get("id")
        or payload.get("salesPayment") is not None
    ):
        return False
    if isinstance(payload.get("deliveries"), list) and payload["deliveries"]:
        return True
    if isinstance(payload.get("items"), list) and payload["items"]:
        return True
    return False


def _to_float(value: Any) -> Optional[float]:
    if isinstance(value, dict) and "amount" in value:
        value = value.get("amount")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stores_release(html: str) -> Optional[str]:
    release = _extract_release_from_text(html)
    if release:
        return release
    m = _RELEASE_FALLBACK_RE.search(html)
    if not m:
        return None
    year_text, month_text, day_or_period = m.groups()
    if not month_text:
        return None
    from datetime import datetime, timezone, timedelta

    year = int(year_text) if year_text else datetime.now(
        timezone(timedelta(hours=9))
    ).year
    month = int(month_text)
    if not day_or_period:
        return f"{year:04d}-{month:02d}"
    if day_or_period.endswith("日"):
        return f"{year:04d}-{month:02d}-{int(day_or_period[:-1]):02d}"
    return f"{year:04d}-{month:02d}-{day_or_period}"


def parse_stores_product_html(html: str, page_url: str = "") -> Optional[dict[str, Any]]:
    if not html or is_stores_captcha_html(html):
        return None
    soup = BeautifulSoup(html, "html.parser")
    if not page_url:
        page_url = _meta(soup, "og:url") or ""
        link = soup.find("link", attrs={"rel": "canonical"})
        if not page_url and link and link.get("href"):
            page_url = str(link["href"]).strip()
    page_url = (page_url or "").strip()

    name = ""
    h1 = soup.select_one("h1.item_name") or soup.find("h1")
    if h1:
        name = _clean_product_name(h1.get_text(" ", strip=True))
    if not name:
        name = _clean_product_name(_meta(soup, "og:title"))
    if not name:
        return None

    unit_cost = None
    amount = _meta(soup, "product:price:amount")
    if amount:
        try:
            unit_cost = float(str(amount).replace(",", ""))
        except ValueError:
            unit_cost = None
    if unit_cost is None:
        price_node = soup.select_one("p.item_price")
        if price_node:
            unit_cost = _parse_price_text(price_node.get_text(" ", strip=True))

    image_url = _meta(soup, "og:image") or ""
    if not image_url:
        img = soup.select_one("img.item_thumb_image, .item_images img")
        if img and img.get("src"):
            image_url = str(img["src"]).strip()

    item_id = item_id_from_url(page_url)
    if not item_id:
        section = soup.select_one("[data-item-id]")
        if section and section.get("data-item-id"):
            item_id = str(section["data-item-id"]).strip()
            if not page_url and item_id:
                # best-effort host from canonical
                host = urlparse(_meta(soup, "og:url") or "").netloc
                if host:
                    page_url = f"https://{host}/items/{item_id}"

    shop = ""
    if page_url:
        shop = urlparse(page_url).netloc.lower()
        if shop.startswith("www."):
            shop = shop[4:]
    shop = shop or "stores.jp"
    item = _product_dict(
        name=name,
        source_url=page_url,
        shop=shop,
        unit_cost=unit_cost,
        image_url=image_url,
        search_text=soup.get_text(" ", strip=True)[:2000],
        release_date=_stores_release(html),
    )
    if item_id:
        item["product_id"] = item_id
    item["qty"] = 1
    return item


def merge_stores_products(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
                "shop": line.get("shop") or "stores.jp",
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


def _iter_order_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for delivery in payload.get("deliveries") or []:
        if not isinstance(delivery, dict):
            continue
        for item in delivery.get("items") or []:
            if isinstance(item, dict):
                rows.append(item)
    if rows:
        return rows
    for item in payload.get("items") or []:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def parse_stores_order_detail_html(html: str, *, shop_hint: str = "") -> dict[str, Any]:
    """解析 STORES マイページ「購入詳細」已渲染 HTML。

    行金额 class=order_sales_payment_num 为小计；单价 = 小计 ÷ 数量。
    """
    soup = BeautifulSoup(html or "", "html.parser")
    shop = (shop_hint or "").strip()
    if not shop:
        for a in soup.select("a[href*='/items/']"):
            href = a.get("href") or ""
            host = urlparse(href).netloc.lower()
            if host.endswith(".stores.jp") or host == "stores.jp":
                shop = host[4:] if host.startswith("www.") else host
                break
    if not shop:
        shop = "stores.jp"

    lines: list[dict[str, Any]] = []
    for block in soup.select(".order_history_item"):
        name_el = block.select_one(".order_item_name_bold")
        name = _clean_product_name(name_el.get_text(" ", strip=True) if name_el else "")
        if not name:
            continue
        qty = 1
        qty_el = block.select_one(".order_total_num")
        if qty_el:
            qm = re.search(r"数量[：:]\s*(\d+)", qty_el.get_text(" ", strip=True))
            if qm:
                qty = max(1, int(qm.group(1)))
        line_total = None
        pay_el = block.select_one(".order_sales_payment_num")
        if pay_el:
            line_total = _yen_amount(pay_el.get_text(" ", strip=True))
        unit_cost = None
        if line_total is not None and qty > 0:
            unit_cost = round(line_total / qty, 2)

        source_url = ""
        product_id = ""
        for a in block.select("a[href*='/items/']"):
            href = (a.get("href") or "").strip()
            if "/items/" in href:
                source_url = href.split("?")[0]
                product_id = item_id_from_url(source_url) or ""
                break
        if not source_url and product_id:
            source_url = f"https://{shop}/items/{product_id}"

        image_url = ""
        img = block.select_one("img.order_history_item_img, img[src]")
        if img:
            image_url = (img.get("src") or "").strip()

        item = _product_dict(
            name=name,
            source_url=source_url or f"https://{shop}/",
            shop=shop,
            unit_cost=unit_cost,
            image_url=image_url,
        )
        item["product_id"] = product_id
        item["qty"] = qty
        lines.append(item)

    shipping_fee = None
    ship_el = soup.select_one(".order_price_shipping_num")
    if ship_el:
        shipping_fee = _yen_amount(ship_el.get_text(" ", strip=True))

    order_total = None
    total_el = soup.select_one(".order_price_total_num")
    if total_el:
        order_total = _yen_amount(total_el.get_text(" ", strip=True))

    order_ref = ""
    for dl in soup.select("dl.order_information"):
        dt = dl.find("dt")
        dd = dl.find("dd")
        if not dt or not dd:
            continue
        if "オーダー番号" in dt.get_text():
            order_ref = dd.get_text(strip=True)
            break
    if not order_ref:
        m = re.search(r"オーダー番号[：:]\s*</dt>\s*<dd[^>]*>\s*(\d+)", html or "", re.I)
        if m:
            order_ref = m.group(1)

    return {
        "products": merge_stores_products(lines),
        "order_ref": order_ref,
        "shipping_fee": shipping_fee,
        "order_total": order_total,
        "raw_line_count": len(lines),
    }


def parse_stores_order_json(text: str, *, shop_hint: str = "") -> dict[str, Any]:
    payload = _unwrap(json.loads(text.strip()))
    if not isinstance(payload, dict):
        return {
            "products": [],
            "order_ref": "",
            "shipping_fee": None,
            "order_total": None,
            "raw_line_count": 0,
        }

    shop = (shop_hint or "").strip()
    lines: list[dict[str, Any]] = []
    for row in _iter_order_items(payload):
        name = _clean_product_name(str(row.get("name") or ""))
        variation = _clean_product_name(
            str(row.get("variationName") or row.get("variation") or "")
        )
        if variation and variation not in name:
            name = f"{name} {variation}".strip()
        if not name:
            continue
        try:
            qty = max(1, int(row.get("quantity")))
        except (TypeError, ValueError):
            qty = 1
        sales = row.get("salesDetail") if isinstance(row.get("salesDetail"), dict) else {}
        line_total = _to_float(sales.get("salesPayment"))
        if line_total is None:
            line_total = _to_float(row.get("salesPayment"))
        unit_cost = None
        if line_total is not None and qty > 0:
            unit_cost = round(line_total / qty, 2)

        image_url = ""
        images = row.get("images") or []
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict):
                image_url = str(first.get("url") or "").strip()
            elif isinstance(first, str):
                image_url = first.strip()

        source_url = str(row.get("itemUrl") or "").strip()
        product_id = ""
        if source_url:
            product_id = item_id_from_url(source_url) or ""
            if not shop:
                shop = urlparse(source_url).netloc.lower()
                if shop.startswith("www."):
                    shop = shop[4:]
        if not product_id:
            for key in ("itemId", "id", "item_id"):
                if row.get(key):
                    product_id = str(row[key]).strip()
                    break
        if not source_url and product_id and shop:
            source_url = f"https://{shop}/items/{product_id}"

        item = _product_dict(
            name=name,
            source_url=source_url or (f"https://{shop}/" if shop else ""),
            shop=shop or "stores.jp",
            unit_cost=unit_cost,
            image_url=image_url,
        )
        item["product_id"] = product_id
        item["qty"] = qty
        lines.append(item)

    shipping_fee = None
    for delivery in payload.get("deliveries") or []:
        if not isinstance(delivery, dict):
            continue
        if delivery.get("type") == "shipping":
            fee = delivery.get("shippingFee")
            shipping_fee = _to_float(fee)
            break

    order_total = _to_float(payload.get("salesPayment"))
    order_ref = str(payload.get("number") or payload.get("id") or "").strip()
    return {
        "products": merge_stores_products(lines),
        "order_ref": order_ref,
        "shipping_fee": shipping_fee,
        "order_total": order_total,
        "raw_line_count": len(lines),
    }
