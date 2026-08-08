"""HobbySearch (1999.co.jp) product-page scraper.

Page template notes: see templates/1999.co.jp.md
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.scrapers.jan import canonicalize_jan, extract_jan_from_html
from app.scrapers.preview import (
    HEADERS,
    _clean_product_name,
    _extract_release_from_text,
    _meta,
    _normalize_image_url,
    _parse_price_text,
    _product_dict,
    _shop_from_url,
)

_CF_MARKERS = ("just a moment", "cf-browser-verification", "challenge-platform")
_PRODUCT_ID_RE = re.compile(r"(?:/eng)?/(\d{6,})(?:/|$|\?)")


def is_1999_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host == "1999.co.jp" or host.endswith(".1999.co.jp")


def product_id_from_url(url: str) -> Optional[str]:
    m = _PRODUCT_ID_RE.search(urlparse(url).path)
    return m.group(1) if m else None


def _looks_like_cloudflare(html: str) -> bool:
    lower = html[:4000].lower()
    return any(marker in lower for marker in _CF_MARKERS)


def _fetch_1999_html_sync(url: str) -> Optional[str]:
    """
    httpx is often blocked by Cloudflare on this host; curl usually works.

    Use sync subprocess (via to_thread) — Windows uvicorn event loops often
    raise empty NotImplementedError for asyncio.create_subprocess_exec.
    """
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
    if _looks_like_cloudflare(html):
        return None
    return html


async def fetch_1999_html(url: str) -> Optional[str]:
    return await asyncio.to_thread(_fetch_1999_html_sync, url)


def _clean_1999_name(name: str) -> str:
    text = _clean_product_name(name)
    text = re.sub(r"\s*-\s*ホビーサーチ.*$", "", text).strip()
    text = re.sub(r"\s*\|\s*ホビーサーチ.*$", "", text).strip()
    return text


def _spec_value(soup: BeautifulSoup, label: str) -> str:
    for dt in soup.select("dl.c-spec dt, dl.c-spec-itempage dt"):
        if label in dt.get_text(" ", strip=True):
            dd = dt.find_next_sibling("dd")
            if dd:
                return dd.get_text(" ", strip=True)
    return ""


def parse_1999_html(html: str, page_url: str) -> Optional[dict[str, Any]]:
    if not html or _looks_like_cloudflare(html):
        return None

    soup = BeautifulSoup(html, "html.parser")
    name = ""
    for h1 in soup.find_all("h1"):
        candidate = _clean_1999_name(h1.get_text(" ", strip=True))
        if candidate and "ホビーサーチ" not in candidate:
            name = candidate
            break
    if not name:
        name = _clean_1999_name(_meta(soup, "og:title"))
    if not name:
        return None

    unit_cost = None
    price_el = soup.select_one(".c-product-detail__info-price-element")
    if price_el:
        unit_cost = _parse_price_text(price_el.get_text(" ", strip=True))
    if unit_cost is None:
        body = soup.select_one(".c-product-detail__info-price-body")
        if body:
            # Prefer 販売価格 block; ignore メーカー希望小売価格 del line.
            for node in body.find_all(class_="c-product-detail__info-price-element"):
                unit_cost = _parse_price_text(node.get_text(" ", strip=True))
                if unit_cost is not None:
                    break
    if unit_cost is None:
        # English / fallback: "Price: 4,207|JPY|" or "Price: 4,207"
        m = re.search(
            r"Price\s*[:：]\s*([\d,]+)\s*(?:\|?\s*JPY)?",
            soup.get_text(" ", strip=True),
            re.IGNORECASE,
        )
        if m:
            try:
                unit_cost = float(m.group(1).replace(",", ""))
            except ValueError:
                unit_cost = None

    image_url = _normalize_image_url(_meta(soup, "og:image"), page_url)
    if not image_url:
        img = soup.select_one(
            "#masterBody_ulThumnail img[src*='itbig'], "
            ".c-product-detail img[src*='itbig'], "
            "img[src*='/itbig']"
        )
        if img:
            image_url = _normalize_image_url(
                str(img.get("src") or img.get("data-src") or ""),
                page_url,
            )
    if not image_url:
        pid = product_id_from_url(page_url)
        if pid:
            image_url = urljoin(page_url, f"/itbig135/{pid}.jpg")

    release_src = ""
    sales = soup.select_one("#masterBody_salesDate")
    if sales:
        release_src = sales.get_text(" ", strip=True)
    release_date = _extract_release_from_text(release_src) or _extract_release_from_text(
        html
    )

    series = _spec_value(soup, "シリーズタイトル") or _spec_value(soup, "シリーズ")
    search_bits = [
        name,
        series,
        _spec_value(soup, "商品コード"),
        release_src,
    ]
    jan_raw = (
        _spec_value(soup, "JANコード")
        or _spec_value(soup, "ＪＡＮコード")
        or _spec_value(soup, "JAN")
    )
    barcode = canonicalize_jan(jan_raw) or extract_jan_from_html(html, soup) or ""

    return _product_dict(
        name=name,
        source_url=page_url.split("?")[0],
        shop=_shop_from_url(page_url) or "1999.co.jp",
        unit_cost=unit_cost,
        image_url=image_url,
        ip=series,
        barcode=barcode,
        search_text=" ".join(bit for bit in search_bits if bit),
        release_date=release_date,
    )


async def scrape_1999_product(url: str) -> Optional[dict[str, Any]]:
    html = await fetch_1999_html(url)
    if not html:
        return None
    return parse_1999_html(html, url)
