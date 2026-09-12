"""miraithings.com (MakeShop) product-page scraper.

Template notes: templates/miraithings.com.md

Price is NOT reliably available via og tags; use the MakeShop item-price span
confirmed by the user:

  body > div.wrap > div > section.content-wrap.item-name-box
    > p.item-price > span:nth-child(1)
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.scrapers.jan import extract_jan_from_html
from app.scrapers.preview import (
    _clean_product_name,
    _extract_release_from_text,
    _meta,
    _normalize_image_url,
    _parse_price_text,
    _product_dict,
    _shop_from_url,
)

SHOP_HOSTS = ("miraithings.com",)

# User-confirmed Chrome copy selector (+ stable MakeShop data-id).
_PRICE_SELECTORS = (
    "body > div.wrap > div > section.content-wrap.item-name-box > p.item-price > span:nth-of-type(1)",
    "body > div.wrap > div > section.content-wrap.item-name-box > p.item-price > span:nth-child(1)",
    'span[data-id="makeshop-item-price:1"]',
    'span[data-id^="makeshop-item-price"]',
    "section.content-wrap.item-name-box p.item-price > span:nth-of-type(1)",
    "section.item-name-box p.item-price > span:nth-of-type(1)",
    "p.item-price > span:nth-of-type(1)",
)


def is_miraithings_url(url: str) -> bool:
    host = urlparse(url or "").netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host in SHOP_HOSTS or host.endswith(".miraithings.com")


def looks_like_miraithings_html(html: str) -> bool:
    head = (html or "")[:8000]
    return (
        "miraithings" in head.lower()
        or "makeshop-item-price" in head
        or ("item-name-box" in head and "content-wrap" in head)
    )


def _parse_price(soup: BeautifulSoup) -> Optional[float]:
    for sel in _PRICE_SELECTORS:
        try:
            node = soup.select_one(sel)
        except Exception:
            node = None
        if not node:
            continue
        text = node.get_text(" ", strip=True)
        value = _parse_price_text(text)
        if value is not None:
            return value
        # First span is often bare "1,980" without 円.
        digits = re.sub(r"[^\d.]", "", text.replace(",", ""))
        if digits:
            try:
                return float(digits)
            except ValueError:
                pass

    row = soup.select_one(
        "section.content-wrap.item-name-box p.item-price, "
        "section.item-name-box p.item-price, p.item-price"
    )
    if row:
        return _parse_price_text(row.get_text(" ", strip=True))
    return None


def _parse_name(soup: BeautifulSoup) -> str:
    for sel in (
        "section.content-wrap.item-name-box p.item-name",
        "section.item-name-box p.item-name",
        "p.item-name",
    ):
        tag = soup.select_one(sel)
        if tag:
            name = _clean_product_name(tag.get_text(" ", strip=True))
            if name:
                return name
    name = _clean_product_name(_meta(soup, "og:title"))
    if name:
        return name
    title = soup.title.string if soup.title else ""
    return _clean_product_name(title or "")


def _parse_image(soup: BeautifulSoup, page_url: str) -> str:
    for key in ("og:image", "twitter:image"):
        value = _meta(soup, key)
        if value:
            return _normalize_image_url(value, page_url)

    for img in soup.find_all("img"):
        src = str(img.get("src") or img.get("data-src") or "").strip()
        if not src:
            continue
        lower = src.lower()
        if any(x in lower for x in ("logo", "icon", "banner", "btn", "svg", "nav")):
            continue
        if (
            "shopimages" in lower
            or "makeshop-multi-images" in lower
            or "akamaized.net" in lower
        ):
            return _normalize_image_url(src, page_url)
    return ""


def parse_miraithings_product_html(
    html: str, page_url: str
) -> Optional[dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    name = _parse_name(soup)
    if not name:
        return None
    unit_cost = _parse_price(soup)
    image_url = _parse_image(soup, page_url)
    barcode = extract_jan_from_html(html, soup) or ""
    return _product_dict(
        name=name,
        source_url=(page_url or "").split("?")[0] or page_url,
        shop=_shop_from_url(page_url) or "miraithings.com",
        unit_cost=unit_cost,
        image_url=image_url,
        barcode=barcode,
        search_text=f"{name} {_meta(soup, 'og:description')}",
        release_date=_extract_release_from_text(html),
    )
