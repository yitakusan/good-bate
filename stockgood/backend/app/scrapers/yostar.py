"""shop.yostar.co.jp（Yostar OFFICIAL SHOP）商品 / 注文解析。

站点为 SPA（#app 空壳 + ecshop-api）。商品页通过
POST /ecshop-api/api/v1/product/detail {"product_id": int} 拉取。
Ctrl+U 空壳不可用。已渲染的「ご注文履歴」详情可直接解析；
也可粘贴 Network 中 /api/v1/order/detail 的 JSON 响应。
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.scrapers.preview import (
    HEADERS,
    _clean_product_name,
    _extract_release_from_text,
    _product_dict,
)

SHOP = "shop.yostar.co.jp"
BASE = "https://shop.yostar.co.jp"
API_PRODUCT_DETAIL = f"{BASE}/ecshop-api/api/v1/product/detail"

_PRODUCT_ID_RE = re.compile(r"/products/detail/(\d+)", re.I)


def is_yostar_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host == "shop.yostar.co.jp" or host.endswith(".yostar.co.jp")


def product_id_from_url(url: str) -> Optional[int]:
    m = _PRODUCT_ID_RE.search(urlparse(url).path or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def product_page_url(product_id: Any) -> str:
    try:
        pid = int(product_id)
    except (TypeError, ValueError):
        return BASE
    return f"{BASE}/products/detail/{pid}"


def is_yostar_spa_shell_html(html: str) -> bool:
    """Detect Ctrl+U SPA empty shell (no order/product DOM)."""
    if not html:
        return False
    lower = html[:8000].lower()
    markers = (
        "yostar official shop",
        "shop.yostar.co.jp",
        "webusstatic.yo-star.com/ecshop",
        "yo-star.com/ecshop",
    )
    if not any(m in lower for m in markers):
        return False
    if 'id="app"' not in lower and "id='app'" not in lower:
        return False
    textish = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    textish = re.sub(r"<style[\s\S]*?</style>", " ", textish, flags=re.I)
    textish = re.sub(r"<[^>]+>", " ", textish)
    textish = re.sub(r"\s+", " ", textish).strip().lower()
    if len(textish) < 120:
        return True
    return "注文" not in textish and "商品" not in textish


def _unwrap_api_data(raw: Any) -> Any:
    if isinstance(raw, dict) and "data" in raw and ("code" in raw or "msg" in raw):
        return raw.get("data")
    return raw


def looks_like_yostar_product_json(text: str) -> bool:
    raw = (text or "").strip()
    if not raw.startswith("{"):
        return False
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return False
    payload = _unwrap_api_data(data)
    if not isinstance(payload, dict):
        return False
    if isinstance(payload.get("list"), list) and (
        payload.get("order_no") or payload.get("order_id") is not None
    ):
        return False
    if not (payload.get("id") or payload.get("product_id")):
        return False
    return bool(payload.get("name") or payload.get("sku") or payload.get("head_image"))


def looks_like_yostar_order_json(text: str) -> bool:
    raw = (text or "").strip()
    if not raw.startswith("{"):
        return False
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return False
    payload = _unwrap_api_data(data)
    if not isinstance(payload, dict):
        return False
    items = payload.get("list")
    if not isinstance(items, list) or not items:
        return False
    sample = items[0] if isinstance(items[0], dict) else {}
    has_line = bool(
        sample.get("product_id") is not None
        or sample.get("name")
        or sample.get("head_image")
    )
    has_meta = bool(
        payload.get("order_no")
        or payload.get("order_id") is not None
        or payload.get("freight_price") is not None
        or payload.get("total_price") is not None
        or payload.get("payment_price") is not None
    )
    return has_line and has_meta


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _category_search_text(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for cat in data.get("category_list") or []:
        if not isinstance(cat, dict):
            continue
        name = (cat.get("name") or "").strip()
        if name:
            parts.append(name)
        children = cat.get("children") or cat.get("child") or []
        if not isinstance(children, list):
            continue
        for child in children:
            if isinstance(child, dict) and (child.get("name") or "").strip():
                parts.append(str(child["name"]).strip())
    detail = data.get("detail") if isinstance(data.get("detail"), dict) else {}
    for key in ("ip_maker", "ip_designer", "hint"):
        val = str(detail.get(key) or "").strip()
        if val:
            parts.append(val)
    return " ".join(parts)


def _sku_label(sku: dict[str, Any]) -> str:
    name = str(sku.get("sku_name") or "").strip()
    if name and name not in ("-",):
        return name
    bits: list[str] = []
    for attr in sku.get("attr") or []:
        if not isinstance(attr, dict):
            continue
        key = str(attr.get("key") or "").strip()
        val = str(attr.get("value") or "").strip()
        if key in ("", "-") and not val:
            continue
        if key in ("", "-"):
            bits.append(val)
        elif val:
            bits.append(f"{key}:{val}")
        else:
            bits.append(key)
    return " / ".join(bits)


def _price_from_skus(data: dict[str, Any]) -> Optional[float]:
    for sku in data.get("sku") or []:
        if not isinstance(sku, dict):
            continue
        price = _to_float(sku.get("price"))
        if price is not None and price > 0:
            return price
    price = _to_float(data.get("price"))
    if price is not None and price > 0:
        return price
    return None


def product_from_api_data(
    data: dict[str, Any], *, page_url: str = ""
) -> list[dict[str, Any]]:
    """Map product/detail API `data` to scrape product dict(s)."""
    if not isinstance(data, dict):
        return []
    pid = data.get("id") or data.get("product_id")
    name = _clean_product_name(str(data.get("name") or ""))
    if not name:
        return []
    source_url = (page_url or "").strip() or product_page_url(pid)
    image_url = str(data.get("head_image") or "").strip()
    detail = data.get("detail") if isinstance(data.get("detail"), dict) else {}
    images = detail.get("imageList") if isinstance(detail.get("imageList"), list) else []
    if not image_url and images:
        image_url = str(images[0] or "").strip()
    content = str(detail.get("content") or data.get("description") or "")
    release = _extract_release_from_text(content)
    search_text = _category_search_text(data)

    skus = [s for s in (data.get("sku") or []) if isinstance(s, dict)]
    multi = len(skus) > 1 and int(data.get("have_spec") or 0) == 1

    out: list[dict[str, Any]] = []
    if multi:
        for sku in skus:
            label = _sku_label(sku)
            full_name = f"{name} {label}".strip() if label else name
            unit_cost = _to_float(sku.get("price"))
            if unit_cost is not None and unit_cost <= 0:
                unit_cost = None
            sku_img = str(sku.get("sku_img") or "").strip() or image_url
            sku_id = sku.get("sku_id")
            url = (
                f"{source_url}?sku_id={sku_id}"
                if sku_id is not None
                else source_url
            )
            item = _product_dict(
                name=full_name,
                source_url=url,
                shop=SHOP,
                unit_cost=unit_cost,
                image_url=sku_img,
                search_text=search_text,
                release_date=release,
            )
            item["product_id"] = str(pid) if pid is not None else ""
            item["qty"] = 1
            out.append(item)
        return out

    item = _product_dict(
        name=name,
        source_url=source_url,
        shop=SHOP,
        unit_cost=_price_from_skus(data),
        image_url=image_url,
        search_text=search_text,
        release_date=release,
    )
    item["product_id"] = str(pid) if pid is not None else ""
    item["qty"] = 1
    return [item]


def parse_yostar_product_json(text: str, *, page_url: str = "") -> list[dict[str, Any]]:
    payload = _unwrap_api_data(json.loads(text.strip()))
    if not isinstance(payload, dict):
        return []
    return product_from_api_data(payload, page_url=page_url)


def merge_yostar_products(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


_YEN_RE = re.compile(r"[¥￥]\s*([\d,]+)")
_QTY_RE = re.compile(r"[x×]\s*(\d+)", re.I)


def is_yostar_order_detail_html(html: str) -> bool:
    """Rendered ご注文履歴 detail (Elements copy), not the empty #app shell."""
    if not html or "delivery-item" not in html:
        return False
    lower = html[:12000].lower()
    return (
        "shop.yostar.co.jp" in lower
        or "yo-star.com/ecshop" in lower
        or "yostar official shop" in lower
    )


def _yen_amount(text: str) -> Optional[float]:
    match = _YEN_RE.search(text or "")
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    return value


def parse_yostar_order_html(html: str) -> dict[str, Any]:
    """Unit price is .price-single. .price-total 小計 is the line total."""
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".order-detail-container") or soup
    refs: list[str] = []
    for block in root.select(".info-base-item"):
        label = block.find("label")
        value = block.find("span")
        if not label or not value:
            continue
        if "ご注文番号" not in label.get_text(" ", strip=True):
            continue
        ref = value.get_text(" ", strip=True)
        if ref and ref not in refs:
            refs.append(ref)

    lines: list[dict[str, Any]] = []
    for block in root.select(".delivery-item"):
        link = block.select_one("a[href*='/products/detail/']")
        if link is None:
            continue
        name = _clean_product_name(link.get_text(" ", strip=True))
        if not name:
            continue
        href = str(link.get("href") or "").strip()
        source_url = urljoin(BASE + "/", href) if href else BASE
        pid = product_id_from_url(source_url)
        image = block.select_one("img.delivery-item-img") or block.find("img")
        image_url = str(image.get("src") or "").strip() if image else ""
        single = block.select_one(".price-single")
        single_text = single.get_text(" ", strip=True) if single else ""
        unit_cost = _yen_amount(single_text)
        qty_match = _QTY_RE.search(single_text)
        try:
            qty = max(1, int(qty_match.group(1))) if qty_match else 1
        except (TypeError, ValueError):
            qty = 1
        if unit_cost is None or unit_cost <= 0:
            total_el = block.select_one(".price-total")
            line_total = _yen_amount(total_el.get_text(" ", strip=True) if total_el else "")
            if line_total is not None and qty > 0:
                unit_cost = round(line_total / qty, 2)
        if unit_cost is not None and unit_cost <= 0:
            unit_cost = None
        hint = block.select_one(".dilivery-hint, .delivery-hint")
        release = _extract_release_from_text(
            hint.get_text(" ", strip=True) if hint else ""
        )
        item = _product_dict(
            name=name,
            source_url=source_url,
            shop=SHOP,
            unit_cost=unit_cost,
            image_url=image_url,
            release_date=release,
        )
        item["product_id"] = str(pid) if pid is not None else ""
        item["qty"] = qty
        lines.append(item)

    shipping_fee = None
    order_total = None
    summary = soup.select_one(".order-summary")
    if summary is not None:
        for row in summary.select(".summary-item"):
            cells = row.find_all("span")
            if len(cells) < 2:
                continue
            label = cells[0].get_text(" ", strip=True)
            if label != "送料":
                continue
            shipping_fee = _yen_amount(cells[1].get_text(" ", strip=True))
        for row in summary.select(".summary-total"):
            text = row.get_text(" ", strip=True)
            if "合計" not in text or "小計" in text:
                continue
            amount = _yen_amount(text)
            if amount is not None:
                order_total = amount
    return {
        "products": merge_yostar_products(lines),
        "order_ref": refs[0] if len(refs) == 1 else "",
        "shipping_fee": shipping_fee,
        "order_total": order_total,
        "raw_line_count": len(lines),
    }


def parse_yostar_order_json(text: str) -> dict[str, Any]:
    payload = _unwrap_api_data(json.loads(text.strip()))
    if not isinstance(payload, dict):
        return {
            "products": [],
            "order_ref": "",
            "shipping_fee": None,
            "order_total": None,
            "raw_line_count": 0,
        }
    lines: list[dict[str, Any]] = []
    for row in payload.get("list") or []:
        if not isinstance(row, dict):
            continue
        name = _clean_product_name(str(row.get("name") or ""))
        sku_label = _clean_product_name(str(row.get("sku_name") or ""))
        if sku_label and sku_label not in ("-",) and sku_label not in name:
            name = f"{name} {sku_label}".strip()
        if not name:
            continue
        pid = row.get("product_id")
        try:
            qty = max(1, int(row.get("quantity")))
        except (TypeError, ValueError):
            qty = 1
        unit_cost = _to_float(row.get("price"))
        if unit_cost is not None and unit_cost <= 0:
            unit_cost = None
        item = _product_dict(
            name=name,
            source_url=product_page_url(pid) if pid is not None else BASE,
            shop=SHOP,
            unit_cost=unit_cost,
            image_url=str(row.get("head_image") or "").strip(),
        )
        item["product_id"] = str(pid) if pid is not None else ""
        item["qty"] = qty
        lines.append(item)

    shipping_fee = _to_float(payload.get("freight_price"))
    order_total = _to_float(payload.get("payment_price"))
    if order_total is None:
        order_total = _to_float(payload.get("total_price"))
    return {
        "products": merge_yostar_products(lines),
        "order_ref": str(payload.get("order_no") or "").strip(),
        "shipping_fee": shipping_fee,
        "order_total": order_total,
        "raw_line_count": len(lines),
    }


async def scrape_yostar_product(url: str) -> Optional[dict[str, Any]]:
    """Fetch product via ecshop-api; return scrape list payload or None."""
    pid = product_id_from_url(url)
    if pid is None:
        return None
    page_url = product_page_url(pid)
    headers = {
        **HEADERS,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": BASE,
        "Referer": page_url,
    }
    async with httpx.AsyncClient(
        headers=headers, follow_redirects=True, timeout=30.0
    ) as client:
        resp = await client.post(API_PRODUCT_DETAIL, json={"product_id": pid})
    if resp.status_code != 200:
        return None
    try:
        body = resp.json()
    except ValueError:
        return None
    if not isinstance(body, dict) or body.get("code") != 200:
        return None
    data = body.get("data")
    if not isinstance(data, dict) or not data:
        return None
    products = product_from_api_data(data, page_url=page_url)
    if not products:
        return None
    return {
        "kind": "list",
        "products": products,
        "message": (
            f"已从 Yostar OFFICIAL SHOP 商品 API 抓取 {len(products)} 件"
            f"（product_id={pid}），请核对后导入"
        ),
    }
