"""shop.asobistore.jp product / order-history parsers.

Template notes: templates/asobistore.jp.md
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.scrapers.jan import (
    canonicalize_jan,
    extract_jan_from_html,
    extract_jan_near_product_name,
)
from app.scrapers.preview import (
    _clean_product_name,
    _extract_release_from_text,
    _meta,
    _normalize_image_url,
    _parse_price_text,
    _product_dict,
    _shop_from_url,
)

SHOP_HOSTS = ("shop.asobistore.jp", "asobistore.jp")


def is_asobi_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host in SHOP_HOSTS or host.endswith(".asobistore.jp")


def _main_selling_price(soup: BeautifulSoup) -> Optional[float]:
    """Main PDP price lives in #selling_price — NOT related-item .selling_price."""
    node = soup.select_one("#selling_price")
    if node:
        value = _parse_price_text(node.get_text(" ", strip=True))
        if value is not None:
            return value
        # Markup sometimes splits number / 円 into spans: "1,500" + "円"
        value = _parse_price_text(node.get_text("", strip=True) + "円")
        if value is not None:
            return value
        digits = re.sub(r"[^\d.]", "", node.get_text("", strip=True).replace(",", ""))
        if digits:
            try:
                return float(digits)
            except ValueError:
                pass

    wrap = soup.select_one("#selling_price_wrap")
    if wrap:
        value = _parse_price_text(wrap.get_text(" ", strip=True))
        if value is not None:
            return value

    # Last resort: first .price outside related-product carousels
    for tag in soup.select("p.price, span.selling_price"):
        if tag.find_parent(class_=re.compile(r"area_rel_product|shopbox_wrap|ulseq")):
            continue
        value = _parse_price_text(tag.get_text(" ", strip=True))
        if value is not None:
            return value
    return None


def _main_product_name(soup: BeautifulSoup) -> str:
    # Header also has an h1; prefer item title near price wrap.
    wrap = soup.select_one("#selling_price_wrap")
    if wrap:
        box = wrap.find_parent("div", class_=True) or wrap.parent
        for _ in range(6):
            if not box:
                break
            for sel in ("h1", "h2", ".item_name", ".goods_name", ".product_name"):
                tag = box.select_one(sel) if hasattr(box, "select_one") else None
                if tag:
                    name = _clean_product_name(tag.get_text(" ", strip=True))
                    if name and "マイページ" not in name:
                        return name
            box = box.parent
    for key in ("og:title",):
        name = _clean_product_name(_meta(soup, key))
        if name:
            return name
    for h1 in soup.find_all("h1"):
        name = _clean_product_name(h1.get_text(" ", strip=True))
        if name and name not in ("マイページ",) and "asobi" not in name.lower():
            return name
    return ""


def _main_image(soup: BeautifulSoup, page_url: str) -> str:
    for key in ("og:image", "twitter:image"):
        value = _meta(soup, key)
        if value:
            return _normalize_image_url(value, page_url)
    for sel in (
        "#main_image img",
        ".main_image img",
        "img#main_image",
        ".item_img img",
        ".detail_img img",
    ):
        tag = soup.select_one(sel)
        if tag and (tag.get("src") or tag.get("data-src")):
            return _normalize_image_url(
                str(tag.get("src") or tag.get("data-src")),
                page_url,
            )
    return ""


def parse_asobi_product_html(html: str, page_url: str) -> Optional[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    name = _main_product_name(soup)
    if not name:
        return None
    unit_cost = _main_selling_price(soup)
    image_url = _main_image(soup, page_url)
    release = _extract_release_from_text(html)
    # Names often contain 【 MM/DD 発送予定】
    if not release:
        m = re.search(r"【\s*(\d{1,2})/(\d{1,2})\s*発送予定\s*】", name)
        if m:
            # year unknown on PDP; leave null — order history is better source
            pass
    barcode = extract_jan_from_html(html, soup) or ""
    return _product_dict(
        name=name,
        source_url=page_url.split("?")[0],
        shop=_shop_from_url(page_url) or "shop.asobistore.jp",
        unit_cost=unit_cost,
        image_url=image_url,
        barcode=barcode,
        search_text=f"{name} {_meta(soup, 'og:description')}",
        release_date=release,
    )


def parse_asobi_order_history_html(
    html: str,
    *,
    order_ref: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Parse saved 購入履歴詳細 pages (mypage/history)."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    # Split loosely by 注文番号 blocks if multiple; single-detail pages have one.
    refs = re.findall(r"(A\d{10,})", text)
    if order_ref:
        refs = [order_ref] if order_ref in text else []
    elif not refs:
        return []

    results: list[dict[str, Any]] = []
    for ref in dict.fromkeys(refs):  # unique, keep order
        # Window around this order number until next order-ish marker
        idx = text.find(ref)
        if idx < 0:
            continue
        window = text[idx : idx + 4000]
        next_ref = re.search(r"\nA\d{10,}\n", window[len(ref) :])
        if next_ref:
            window = window[: len(ref) + next_ref.start()]

        shipping_fee = None
        m_ship = re.search(r"送料\(税込\)\s*([\d,]+)\s*円", window)
        if m_ship:
            shipping_fee = float(m_ship.group(1).replace(",", ""))
        order_total = None
        m_pay = re.search(r"お支払金額\(税込\)\s*([\d,]+)\s*円", window)
        if m_pay:
            order_total = float(m_pay.group(1).replace(",", ""))
        goods_total = None
        m_goods = re.search(r"商品金額合計\(税込\)\s*([\d,]+)\s*円", window)
        if m_goods:
            goods_total = float(m_goods.group(1).replace(",", ""))

        lines: list[dict[str, Any]] = []
        # Pattern: name \n sku \n qty \n price円
        for m in re.finditer(
            r"(?P<name>[^\n]{8,120}?)\n"
            r"(?P<sku>\d{5,}-\d{2}-\d{2}-\d{2})\n"
            r"(?P<qty>\d+)\n"
            r"(?P<price>[\d,]+)\s*円",
            window,
        ):
            name = m.group("name").strip()
            if name in ("商品名", "品番"):
                continue
            sku = m.group("sku")
            qty = max(1, int(m.group("qty")))
            unit = float(m.group("price").replace(",", ""))
            # History lines often show "Name (JAN)" — only accept check-digit-valid JAN.
            barcode = extract_jan_near_product_name(window, name) or ""
            if not barcode:
                paren = re.search(r"\((\d{8}|\d{13})\)\s*$", name)
                if paren:
                    barcode = canonicalize_jan(paren.group(1)) or ""
            lines.append(
                {
                    "name": name,
                    "qty": qty,
                    "unit_cost": unit,
                    "image_url": "",
                    "source_url": f"https://shop.asobistore.jp/products/detail/{sku}",
                    "ip": "",
                    "sku": sku,
                    "barcode": barcode,
                }
            )

        if not lines:
            continue
        results.append(
            {
                "order_ref": ref,
                "shop": "shop.asobistore.jp",
                "shipping_fee": shipping_fee,
                "order_total": order_total,
                "goods_total": goods_total,
                "lines": lines,
            }
        )
    return results
