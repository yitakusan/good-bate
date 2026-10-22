"""FutureShop product pages: KADOKAWA store and JUMP CS.

Cart add stays in retailer_cart (GET /shop/cart/cart.aspx?goods=&qty=).
This module only parses the product page for scrape import and cart preview.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.scrapers.jan import canonicalize_jan, extract_jan_from_html
from app.scrapers.preview import (
    _clean_product_name,
    _json_ld_products,
    _meta,
    _normalize_image_url,
    _product_dict,
)

SHOP_HOSTS = ("store.kadokawa.co.jp", "jumpcs.shueisha.co.jp")
_GOODS_RE = re.compile(r"/shop/g/g([^/?#]+)", re.I)
_PRICE_RE = re.compile(r"(\d[\d,]*)")


def _host(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def is_futureshop_product_url(url: str) -> bool:
    host = _host(url)
    if not any(host == allowed or host.endswith("." + allowed) for allowed in SHOP_HOSTS):
        return False
    return bool(_GOODS_RE.search(urlparse(url).path or ""))


def goods_code_from_url(url: str) -> str:
    match = _GOODS_RE.search(urlparse(url or "").path or "")
    return match.group(1) if match else ""


def _goods_from_html(soup: BeautifulSoup, page_url: str) -> str:
    tag = soup.find("input", attrs={"name": "goods"})
    if tag and tag.get("value"):
        return str(tag["value"]).strip()
    return goods_code_from_url(page_url)


def _name_from_page(soup: BeautifulSoup) -> str:
    products = _json_ld_products(soup)
    if products:
        name = _clean_product_name(str(products[0].get("name") or ""))
        if name:
            return name
    h1 = soup.find("h1")
    if h1:
        name = _clean_product_name(h1.get_text(" ", strip=True))
        if name:
            return name
    title = _clean_product_name(_meta(soup, "og:title"))
    if " | " in title:
        title = title.split(" | ", 1)[0].strip()
    if ": " in title:
        head, tail = title.rsplit(": ", 1)
        if len(tail) <= 24:
            title = head.strip()
    return title


def _price_from_page(soup: BeautifulSoup, products: list[dict[str, Any]]) -> Optional[float]:
    raw = _meta(soup, "product:price:amount")
    if raw:
        match = _PRICE_RE.search(raw.replace(",", ""))
        if match:
            return float(match.group(1))
    if products:
        offers = products[0].get("offers")
        if isinstance(offers, list) and offers:
            offers = offers[0]
        if isinstance(offers, dict) and offers.get("price") is not None:
            try:
                return float(str(offers["price"]).replace(",", ""))
            except ValueError:
                return None
    return None


def _image_from_page(soup: BeautifulSoup, page_url: str, goods: str) -> str:
    image = _normalize_image_url(_meta(soup, "og:image"), page_url)
    host = _host(page_url)
    if goods and host:
        large = f"https://{host}/img/goods/L/{goods}.jpg"
        if not image or "/img/goods/S/" in image or "/img/goods/" not in image:
            return large
    return image


def parse_futureshop_product_html(html: str, page_url: str = "") -> Optional[dict[str, Any]]:
    if not (html or "").strip():
        return None
    soup = BeautifulSoup(html, "html.parser")
    goods = _goods_from_html(soup, page_url)
    name = _name_from_page(soup)
    if not name and not goods:
        return None
    products = _json_ld_products(soup)
    price = _price_from_page(soup, products)
    image = _image_from_page(soup, page_url, goods)
    barcode = ""
    if goods:
        barcode = canonicalize_jan(goods, require_jp_prefix=True) or ""
    if not barcode:
        barcode = extract_jan_from_html(html, soup) or ""
    return _product_dict(
        name=name or goods,
        source_url=page_url,
        shop=_host(page_url),
        unit_cost=price,
        image_url=image,
        barcode=barcode,
        search_text=name,
    )
