"""三井ショッピングパーク &mall（mitsui-shopping-park.com）注文履歴解析。

支持：
1. 整页「查看网页源代码」（仅含首屏 SSR，通常 10 件；点もっと見る后不会变）
2. 开发者工具 Elements 里复制加载后的列表 outerHTML（点完もっと見る后）
3. Network 里 `shop-order-skus` 接口 JSON 响应（可多页粘贴合并）

相同 mallSkuId / 商品色番 自动合并数量。

模板说明：templates/mitsui-shopping-park.com.order-history.md
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup, Tag

SHOP = "mitsui-shopping-park.com"
BASE = "https://mitsui-shopping-park.com"

_QTY_RE = re.compile(r"数量\s*[：:]\s*(\d+)")
_SHIP_YM_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月")
# CDN path uses …/product/color/{code}_{variant}.jpg (folder name may vary).
_COLOR_CODE_RE = re.compile(r"/product/color/(\d{10,})_", re.I)
_MALL_SKU_RE = re.compile(r"mallSkuId=(\d+)", re.I)
# 「10 件 / 29 件中」or compacted「10件 / 29件中」
_PAGE_COUNT_RE = re.compile(
    r"(\d+)\s*<span[^>]*>\s*件\s*/\s*</span>\s*(\d+)\s*<span[^>]*>\s*件中",
    re.I,
)
_PAGE_COUNT_TEXT_RE = re.compile(r"(\d+)\s*件\s*/\s*(\d+)\s*件中")


def is_andmall_order_history_html(html: str) -> bool:
    """Detect full page or DevTools-copied live DOM fragment."""
    text = html or ""
    if "order-history-product" not in text and "order-history-list" not in text:
        return False
    markers = (
        "mitsui-shopping-park.com",
        "注文履歴",
        "&mall",
        "&amp;mall",
        "andmall",
    )
    if any(m in text for m in markers):
        return True
    # Elements → Copy outerHTML after もっと見る (may lack site chrome).
    return "mallSkuId=" in text or (
        "数量" in text and "order-history-product" in text
    )


def looks_like_andmall_order_json(text: str) -> bool:
    """Detect pasted shop-order-skus API JSON (single page or concatenated)."""
    raw = (text or "").strip()
    if not raw or raw[0] not in "{[":
        return False
    return (
        "mallSkuId" in raw
        or "mall_sku_id" in raw
        or "itemName" in raw
        or "shop-order-skus" in raw
    ) and (
        "quantity" in raw
        or "itemName" in raw
        or "mallProductCodeId" in raw
        or "mall_product_code_id" in raw
    )


def _text(el: Optional[Tag]) -> str:
    if not el:
        return ""
    return el.get_text(" ", strip=True)


def _qty_from_text(text: str) -> int:
    m = _QTY_RE.search(text or "")
    if m:
        return max(1, int(m.group(1)))
    return 1


def _ship_from_name(name: str) -> tuple[Optional[str], Optional[str]]:
    m = _SHIP_YM_RE.search(name or "")
    if not m:
        return None, None
    year, month = int(m.group(1)), int(m.group(2))
    if not (1 <= month <= 12):
        return None, None
    return f"{year:04d}-{month:02d}", None


def _mall_sku_from_href(href: str) -> str:
    qs = parse_qs(urlparse(href or "").query)
    vals = qs.get("mallSkuId") or qs.get("mall_sku_id") or []
    if vals:
        return str(vals[0]).strip()
    m = _MALL_SKU_RE.search(href or "")
    return m.group(1) if m else ""


def _product_code_from_image(src: str) -> str:
    m = _COLOR_CODE_RE.search(src or "")
    return m.group(1) if m else ""


def _product_code_from_sku(mall_sku_id: str) -> str:
    """mallSkuId like 62607000001710001 → color code 6260700000171."""
    sku = (mall_sku_id or "").strip()
    if len(sku) >= 13 and sku.isdigit():
        if len(sku) == 17:
            return sku[:13]
        if len(sku) > 13:
            return sku[:-4]
    return sku


def _abs_image(src: str) -> str:
    src = (src or "").strip()
    if not src:
        return ""
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return BASE + src
    if "mitsui-shopping-park.com" in src and "?" in src:
        return src.split("?", 1)[0]
    return src


def _stable_source_url(*, product_code: str, mall_sku_id: str, href: str = "") -> str:
    if product_code:
        return f"{BASE}/ec/product/{product_code}"
    if mall_sku_id:
        return f"{BASE}/ec/product?mallSkuId={mall_sku_id}"
    return (href or "").split("#", 1)[0]


def _line_from_anchor(a: Tag) -> Optional[dict[str, Any]]:
    detail = a.select_one(".order-history-product-detail") or a
    name = _text(detail.select_one(".name"))
    if not name:
        img = a.select_one("img[alt]")
        name = (img.get("alt") or "").strip() if img else ""
    if not name:
        return None

    shop_label = _text(detail.select_one(".shop")) or "&mall"
    qty = _qty_from_text(
        _text(detail.select_one(".quantity")) or a.get_text(" ", strip=True)
    )
    href = unquote(str(a.get("href") or "").strip())
    mall_sku_id = _mall_sku_from_href(href)

    image_url = ""
    product_code = ""
    for img in a.select("img[src]"):
        src = str(img.get("src") or "")
        if "product/color" in src:
            image_url = _abs_image(src)
            product_code = _product_code_from_image(src)
            break
    if not image_url:
        img = a.select_one("img[src]")
        if img:
            image_url = _abs_image(str(img.get("src") or ""))
            product_code = product_code or _product_code_from_image(image_url)
    if not product_code:
        product_code = _product_code_from_sku(mall_sku_id)

    color = _text(detail.select_one(".color"))
    size = _text(detail.select_one(".size"))
    display_name = name

    ship_at, ship_period = _ship_from_name(name)
    source_url = _stable_source_url(
        product_code=product_code, mall_sku_id=mall_sku_id, href=href
    )

    return {
        "name": display_name,
        "shop": SHOP,
        "shop_label": shop_label,
        "qty": qty,
        "unit_cost": None,
        "image_url": image_url,
        "source_url": source_url,
        "ip": "",
        "barcode": "",
        "expected_ship_at": ship_at,
        "expected_ship_period": ship_period,
        "release_date": ship_at,
        "mall_sku_id": mall_sku_id,
        "product_code": product_code,
        "order_href": href,
        "color": color,
        "size": size,
    }


def _line_from_api_dict(item: dict[str, Any]) -> Optional[dict[str, Any]]:
    name = str(
        item.get("itemName")
        or item.get("item_name")
        or item.get("name")
        or ""
    ).strip()
    if not name:
        return None
    mall_sku_id = str(
        item.get("mallSkuId") or item.get("mall_sku_id") or ""
    ).strip()
    product_code = str(
        item.get("mallProductCodeId")
        or item.get("mall_product_code_id")
        or item.get("productCode")
        or ""
    ).strip()
    if not product_code:
        product_code = _product_code_from_sku(mall_sku_id)
    try:
        qty = max(1, int(item.get("quantity") or item.get("qty") or 1))
    except (TypeError, ValueError):
        qty = 1
    image_url = _abs_image(
        str(item.get("imageUrl") or item.get("image_url") or "")
    )
    if not product_code and image_url:
        product_code = _product_code_from_image(image_url)
    shop_label = str(
        item.get("shopName") or item.get("shop_name") or "&mall"
    ).strip()
    ship_at, ship_period = _ship_from_name(name)
    return {
        "name": name,
        "shop": SHOP,
        "shop_label": shop_label,
        "qty": qty,
        "unit_cost": None,
        "image_url": image_url,
        "source_url": _stable_source_url(
            product_code=product_code, mall_sku_id=mall_sku_id
        ),
        "ip": "",
        "barcode": "",
        "expected_ship_at": ship_at,
        "expected_ship_period": ship_period,
        "release_date": ship_at,
        "mall_sku_id": mall_sku_id,
        "product_code": product_code,
        "color": str(item.get("color") or item.get("colorName") or ""),
        "size": str(item.get("size") or item.get("sizeName") or ""),
    }


def _walk_order_line_dicts(node: Any, out: list[dict[str, Any]]) -> None:
    if isinstance(node, dict):
        name = node.get("itemName") or node.get("item_name")
        sku = node.get("mallSkuId") or node.get("mall_sku_id")
        if name and (sku is not None or node.get("quantity") is not None):
            out.append(node)
        for value in node.values():
            _walk_order_line_dicts(value, out)
    elif isinstance(node, list):
        for value in node:
            _walk_order_line_dicts(value, out)


def _loads_json_blobs(text: str) -> list[Any]:
    """Parse one JSON value, or several JSON values pasted one after another."""
    raw = (text or "").strip()
    if not raw:
        return []
    try:
        return [json.loads(raw)]
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    idx = 0
    blobs: list[Any] = []
    length = len(raw)
    while idx < length:
        while idx < length and raw[idx].isspace():
            idx += 1
        if idx >= length:
            break
        try:
            obj, end = decoder.raw_decode(raw, idx)
        except json.JSONDecodeError:
            break
        blobs.append(obj)
        idx = end
    return blobs


def parse_andmall_order_history_lines(html: str) -> list[dict[str, Any]]:
    """Parse raw order-history rows from HTML (before merge)."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    lines: list[dict[str, Any]] = []
    for a in soup.select("a.order-history-product"):
        line = _line_from_anchor(a)
        if line:
            lines.append(line)
    return lines


def parse_andmall_order_skus_json(text: str) -> list[dict[str, Any]]:
    """Parse shop-order-skus JSON (one or more pages) into raw lines."""
    lines: list[dict[str, Any]] = []
    for blob in _loads_json_blobs(text):
        found: list[dict[str, Any]] = []
        _walk_order_line_dicts(blob, found)
        for item in found:
            line = _line_from_api_dict(item)
            if line:
                lines.append(line)
    return lines


def merge_andmall_products(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge duplicate SKUs: same mall_sku_id / product_code / name → sum qty."""
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for line in lines:
        key = (
            (line.get("mall_sku_id") or "").strip()
            or (line.get("product_code") or "").strip()
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
                "mall_sku_id": line.get("mall_sku_id") or "",
                "product_code": line.get("product_code") or "",
            }
            order.append(key)
            continue
        cur = merged[key]
        cur["qty"] = int(cur.get("qty") or 0) + int(line.get("qty") or 1)
        if not cur.get("image_url") and line.get("image_url"):
            cur["image_url"] = line["image_url"]
        if not cur.get("expected_ship_at") and line.get("expected_ship_at"):
            cur["expected_ship_at"] = line["expected_ship_at"]
            cur["expected_ship_period"] = line.get("expected_ship_period")
            cur["release_date"] = line.get("release_date")
    return [merged[k] for k in order]


def detect_andmall_page_counts(html: str) -> tuple[Optional[int], Optional[int]]:
    """Return (shown, total) from「N件 / M件中」if present."""
    text = html or ""
    m = _PAGE_COUNT_RE.search(text) or _PAGE_COUNT_TEXT_RE.search(text)
    if not m:
        return None, None
    shown, total = int(m.group(1)), int(m.group(2))
    if shown <= 0 or total <= 0:
        return None, None
    return shown, total


def parse_andmall_order_history_html(html: str) -> list[dict[str, Any]]:
    """Parse &mall 注文履歴 HTML into merged scrape products."""
    if not is_andmall_order_history_html(html):
        return []
    return merge_andmall_products(parse_andmall_order_history_lines(html))


def parse_andmall_order_payload(text: str) -> tuple[list[dict[str, Any]], str]:
    """Parse HTML or JSON paste → (merged products, source_kind)."""
    raw = text or ""
    if looks_like_andmall_order_json(raw):
        lines = parse_andmall_order_skus_json(raw)
        return merge_andmall_products(lines), "json"
    if is_andmall_order_history_html(raw):
        lines = parse_andmall_order_history_lines(raw)
        return merge_andmall_products(lines), "html"
    return [], ""
