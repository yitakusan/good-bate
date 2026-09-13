"""a.sofmap.com / sofmap.com product-detail scraper.

Template notes: templates/sofmap.md

PDP example:
  https://a.sofmap.com/product_detail.aspx?sku=102018397

Page is Shift_JIS; httpx usually decodes via Content-Type charset.
Prefer JSON-LD + 仕様詳細 table (JANコード) over generic og:image (site OGP).
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from app.scrapers.jan import canonicalize_jan, extract_jan_from_html
from app.scrapers.preview import (
    _clean_product_name,
    _extract_release_from_text,
    _meta,
    _normalize_image_url,
    _parse_price_text,
    _product_dict,
    _shop_from_url,
)

SHOP_HINT = "sofmap.com"
_PRODUCT_PATH_RE = re.compile(r"product_detail(?:_sp)?\.aspx", re.I)
_SKU_RE = re.compile(r"[?&]sku=(\d+)", re.I)
_JAN_IN_IMG_RE = re.compile(
    r"/(\d{8}|\d{13})\.(?:jpe?g|png|webp)(?:\?|$)", re.I
)
_YEN_RE = re.compile(r"[¥￥]\s*([\d,]+)|(?:&yen;|&#165;)\s*([\d,]+)", re.I)


def is_sofmap_url(url: str) -> bool:
    host = urlparse(url or "").netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host == "sofmap.com" or host.endswith(".sofmap.com")


def is_sofmap_product_url(url: str) -> bool:
    if not is_sofmap_url(url):
        return False
    path = urlparse(url).path.lower()
    return bool(_PRODUCT_PATH_RE.search(path))


def is_sofmap_order_detail_html(html: str) -> bool:
    """Detect お取引の詳細 / order status detail page.

    Softmap order pages have a very large global header; product links often
    appear well after the first 20KB, so product markers must be searched in
    the full document (not only a head slice).
    """
    text = html or ""
    if not text:
        return False
    lower = text.lower()
    head = text[:20000]
    if (
        "sofmap" not in head.lower()
        and "ソフマップ" not in head
        and "sofmap" not in lower
        and "ソフマップ" not in text
    ):
        return False
    markers = (
        "お取引の詳細",
        "お取引の詳細",
        "orderlist_product",
        "ご注文番号",
        "order_status",
        "orderlist_wrp",
    )
    if not any(m in text for m in markers):
        return False
    has_product_link = "product_detail.aspx" in lower
    has_product_ui = (
        "販売価格" in text
        or "販売価格" in text
        or "product_box" in lower
        or "ご注文情報" in text
        or "orderlist_product" in lower
    )
    return has_product_link and has_product_ui


def looks_like_sofmap_html(html: str) -> bool:
    if is_sofmap_order_detail_html(html):
        return True
    head = (html or "")[:12000].lower()
    body = html or ""
    if "sofmap" not in head and "ソフマップ" not in body[:12000]:
        return False
    return (
        "product_detail" in head
        or "janコード" in body[:20000].lower()
        or "ソフマップ特価" in body
        or "image.sofmap.com" in head
    )


def canonicalize_sofmap_product_url(url: str) -> str:
    """Keep host + product_detail path + sku query only."""
    raw = (url or "").strip()
    if not raw:
        return raw
    try:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        qs = parse_qs(parsed.query)
        sku = (qs.get("sku") or [None])[0]
        query = urlencode({"sku": sku}) if sku else ""
        path = parsed.path or "/product_detail.aspx"
        return urlunparse(
            (parsed.scheme or "https", parsed.netloc, path, "", query, "")
        )
    except Exception:
        return raw.split("#")[0]


def _table_map(soup: BeautifulSoup) -> dict[str, str]:
    out: dict[str, str] = {}
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        key = cells[0].get_text(" ", strip=True)
        val = cells[1].get_text(" ", strip=True)
        if key and val and key not in out:
            out[key] = val
    return out


def _parse_ld_product(soup: BeautifulSoup) -> dict[str, Any]:
    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            types = node.get("@type")
            if types == "Product" or (isinstance(types, list) and "Product" in types):
                return node
            graph = node.get("@graph")
            if isinstance(graph, list):
                for item in graph:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        return item
    return {}


def _ld_image(ld: dict[str, Any], page_url: str) -> str:
    image = ld.get("image")
    candidates: list[str] = []
    if isinstance(image, str):
        candidates.append(image)
    elif isinstance(image, list):
        for item in image:
            if isinstance(item, str):
                candidates.append(item)
            elif isinstance(item, dict) and item.get("url"):
                candidates.append(str(item["url"]))
    for src in candidates:
        lower = src.lower()
        if any(x in lower for x in ("ogp_", "ogp.", "logo", "icon")):
            continue
        return _normalize_image_url(src, page_url)
    return ""


def _ld_price(ld: dict[str, Any]) -> Optional[float]:
    offers = ld.get("offers")
    if isinstance(offers, list) and offers:
        offers = offers[0]
    if isinstance(offers, dict) and offers.get("price") is not None:
        try:
            return float(str(offers["price"]).replace(",", ""))
        except ValueError:
            return None
    return None


def _price_from_page(soup: BeautifulSoup, specs: dict[str, str]) -> Optional[float]:
    for key in ("ソフマップ特価", "販売価格", "価格"):
        if key in specs:
            value = _parse_price_text(specs[key])
            if value is not None:
                return value
    for sel in ("span.price", "p.price", ".price"):
        for node in soup.select(sel):
            text = node.get_text(" ", strip=True)
            if not text or "ポイント" in text:
                continue
            value = _parse_price_text(text)
            if value is not None:
                return value
    return None


def _jan_from_specs(specs: dict[str, str]) -> str:
    for key, val in specs.items():
        if "JAN" in key.upper():
            jan = canonicalize_jan(val)
            if jan:
                return jan
    return ""


def _release_from_specs(specs: dict[str, str]) -> Optional[str]:
    for key in ("発売日", "メーカー発売日"):
        if key in specs:
            # Cell is often "2026年9月上旬発売" without the label keyword.
            release = _extract_release_from_text(f"{key} {specs[key]}")
            if release:
                return release
    return None


def _name_from_page(soup: BeautifulSoup, ld: dict[str, Any], specs: dict[str, str]) -> str:
    name = _clean_product_name(str(ld.get("name") or ""))
    if name:
        return name
    if "商品名" in specs:
        name = _clean_product_name(specs["商品名"])
        if name:
            return name
    name = _clean_product_name(_meta(soup, "og:title"))
    if name:
        return name
    title = soup.title.string if soup.title else ""
    return _clean_product_name(title or "")


def _image_from_page(soup: BeautifulSoup, ld: dict[str, Any], page_url: str) -> str:
    image = _ld_image(ld, page_url)
    if image:
        return image
    for img in soup.find_all("img"):
        src = str(img.get("src") or img.get("data-src") or "").strip()
        if not src:
            continue
        lower = src.lower()
        if "image.sofmap.com" in lower and (
            "/product/" in lower or "/pim/" in lower
        ):
            return _normalize_image_url(src, page_url)
        if "pim/" in lower and any(
            lower.endswith(ext) or f"{ext}?" in lower
            for ext in (".jpg", ".jpeg", ".png", ".webp")
        ):
            return _normalize_image_url(src, page_url)
    # Never prefer site-wide OGP logos for sofmap.
    return ""


def parse_sofmap_product_html(html: str, page_url: str = "") -> Optional[dict[str, Any]]:
    if not (html or "").strip():
        return None
    soup = BeautifulSoup(html, "html.parser")
    ld = _parse_ld_product(soup)
    specs = _table_map(soup)

    name = _name_from_page(soup, ld, specs)
    if not name:
        return None

    source_url = canonicalize_sofmap_product_url(page_url) if page_url else page_url
    if not source_url:
        canonical = soup.find("link", attrs={"rel": "canonical"})
        if canonical and canonical.get("href"):
            source_url = canonicalize_sofmap_product_url(str(canonical["href"]))

    unit_cost = _ld_price(ld)
    if unit_cost is None:
        unit_cost = _price_from_page(soup, specs)

    barcode = _jan_from_specs(specs) or extract_jan_from_html(html, soup) or ""
    image_url = _image_from_page(soup, ld, source_url or page_url)
    release = _release_from_specs(specs) or _extract_release_from_text(html)

    shop = _shop_from_url(source_url or page_url) or SHOP_HINT
    if shop.endswith(".sofmap.com") or shop == "sofmap.com":
        shop = "sofmap.com"

    return _product_dict(
        name=name,
        source_url=source_url or page_url,
        shop=shop,
        unit_cost=unit_cost,
        image_url=image_url,
        barcode=barcode,
        search_text=f"{name} {specs.get('メーカー', '')} {specs.get('商品番号', '')}",
        release_date=release,
    )


def _sku_from_href_or_box(href: str, box: Any) -> str:
    m = _SKU_RE.search(href or "")
    if m:
        return m.group(1)
    if box is not None:
        for attr in ("rel", "r", "sku"):
            raw = str(box.get(attr) or "").strip()
            if raw.isdigit():
                return raw
    return ""


def _jan_from_image_url(url: str) -> str:
    m = _JAN_IN_IMG_RE.search(url or "")
    if not m:
        return ""
    return canonicalize_jan(m.group(1)) or ""


def _parse_yen_amount(text: str) -> Optional[float]:
    cleaned = (
        (text or "")
        .replace("\xa0", " ")
        .replace("&yen;", "¥")
        .replace("&#165;", "¥")
    )
    value = _parse_price_text(cleaned)
    if value is not None:
        return value
    m = _YEN_RE.search(cleaned)
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _dl_map(root: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for dl in root.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            key = dt.get_text(" ", strip=True)
            val = dd.get_text(" ", strip=True)
            if key and val and key not in out:
                out[key] = val
    return out


def extract_sofmap_order_ref(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for dt in soup.find_all("dt"):
        if "注文番号" in dt.get_text(" ", strip=True):
            dd = dt.find_next_sibling("dd")
            if dd:
                digits = re.sub(r"\D", "", dd.get_text(" ", strip=True))
                if len(digits) >= 6:
                    return digits
    m = re.search(r"ご?注文番号\s*[:：]?\s*([0-9]{6,})", html or "")
    return m.group(1) if m else ""


def extract_sofmap_shipping_fee(html: str) -> Optional[float]:
    soup = BeautifulSoup(html or "", "html.parser")
    for th in soup.find_all("th"):
        label = th.get_text(" ", strip=True)
        if "送料" in label:
            td = th.find_next_sibling("td")
            if td:
                return _parse_yen_amount(td.get_text(" ", strip=True))
    m = re.search(r"送料合計[^¥￥]*[¥￥]\s*([\d,]+)", html or "")
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def extract_sofmap_order_total(html: str) -> Optional[float]:
    soup = BeautifulSoup(html or "", "html.parser")
    for sel in ("#receiptPaymentPriceVal",):
        node = soup.select_one(sel)
        if node:
            value = _parse_yen_amount(node.get_text(" ", strip=True))
            if value is not None:
                return value
    for th in soup.find_all("th"):
        label = th.get_text(" ", strip=True)
        if any(k in label for k in ("お支払い総額", "ご注文合計", "ご注文金額")):
            td = th.find_next_sibling("td")
            if td:
                value = _parse_yen_amount(td.get_text(" ", strip=True))
                if value is not None:
                    return value
    m = re.search(
        r"(?:お支払い総額|ご注文合計|ご注文金額)[^¥￥]*[¥￥]\s*([\d,]+)",
        html or "",
    )
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def parse_sofmap_order_detail_lines(html: str) -> list[dict[str, Any]]:
    """Parse product lines from お取引の詳細 HTML (before merge)."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    lines: list[dict[str, Any]] = []
    for box in soup.select(".product_box, div.product_box"):
        name_a = box.select_one("a.product_name[href], a.product_name")
        if not name_a:
            name_a = box.select_one('a[href*="product_detail.aspx"]')
        name = _clean_product_name(
            name_a.get_text(" ", strip=True) if name_a else ""
        )
        if not name:
            continue
        href = str(name_a.get("href") or "") if name_a else ""
        sku = _sku_from_href_or_box(href, box)
        if href:
            source_url = canonicalize_sofmap_product_url(href)
        elif sku:
            source_url = f"https://a.sofmap.com/product_detail.aspx?sku={sku}"
        else:
            source_url = ""
        if source_url and "sofmap.com" not in source_url and sku:
            source_url = f"https://a.sofmap.com/product_detail.aspx?sku={sku}"

        fields = _dl_map(box)
        unit_cost = _parse_yen_amount(
            fields.get("販売価格")
            or fields.get("販売価格")
            or fields.get("価格")
            or ""
        )
        qty = 1
        qty_raw = (
            fields.get("数量") or fields.get("注文数量") or ""
        ).strip()
        if qty_raw.isdigit():
            qty = max(1, int(qty_raw))

        image_url = ""
        img = box.select_one("img[src], img[data-src]")
        if img:
            image_url = _normalize_image_url(
                str(img.get("src") or img.get("data-src") or ""),
                source_url or "https://a.sofmap.com/",
            )
        barcode = _jan_from_image_url(image_url)

        lines.append(
            {
                "name": name,
                "shop": SHOP_HINT,
                "unit_cost": unit_cost,
                "image_url": image_url,
                "source_url": source_url,
                "ip": "",
                "barcode": barcode,
                "expected_ship_at": None,
                "expected_ship_period": None,
                "release_date": None,
                "qty": qty,
                "product_id": sku,
            }
        )
    return lines


def merge_sofmap_order_products(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
                "shop": line.get("shop") or SHOP_HINT,
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
        if not cur.get("barcode") and line.get("barcode"):
            cur["barcode"] = line["barcode"]
    return [merged[k] for k in order]


def parse_sofmap_order_detail_html(html: str) -> dict[str, Any]:
    """Parse sofmap お取引の詳細 HTML → products + order meta."""
    if not is_sofmap_order_detail_html(html):
        return {
            "products": [],
            "order_ref": "",
            "shipping_fee": None,
            "order_total": None,
            "raw_line_count": 0,
        }
    lines = parse_sofmap_order_detail_lines(html)
    products = merge_sofmap_order_products(lines)
    return {
        "products": products,
        "order_ref": extract_sofmap_order_ref(html),
        "shipping_fee": extract_sofmap_shipping_fee(html),
        "order_total": extract_sofmap_order_total(html),
        "raw_line_count": len(lines),
    }
