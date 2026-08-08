from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))

ALIPAY_PAGE_URL = "https://www.5waihui.com/alipay/"
RMB_JS_URL = "https://www.5waihui.com/data/rmb.js"
CACHE_TTL_SECONDS = 60 * 60
ALIPAY_MARKUP = 1.002
JPY_BASE_AMOUNT = 100

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": ALIPAY_PAGE_URL,
}

RMB_JPY_PATTERN = re.compile(r'var\s+hq_str_RMBJPY\s*=\s*"([^"]+)"')
RATE_NUMBER_PATTERN = re.compile(r"\d+\.\d+")


@dataclass(frozen=True)
class ExchangeRateData:
    currency_name: str
    cny_per_100_jpy: float
    spot_cny_per_100_jpy: float
    updated_at: str | None
    source_url: str


@dataclass
class _CacheEntry:
    data: ExchangeRateData
    expires_at: float
    fetched_at: str


_cache: _CacheEntry | None = None


def format_fetched_at() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")


def parse_rmb_jpy_line(line: str) -> ExchangeRateData:
    fields = [part.strip() for part in line.split(",")]
    if len(fields) < 6:
        raise ValueError("RMBJPY 数据字段不足")

    spot_rate = float(fields[5])
    alipay_rate = round(spot_rate * ALIPAY_MARKUP, 3)
    updated_at = f"{fields[6]} {fields[7]}" if len(fields) >= 8 else None

    return ExchangeRateData(
        currency_name=fields[0] or "日元",
        cny_per_100_jpy=alipay_rate,
        spot_cny_per_100_jpy=spot_rate,
        updated_at=updated_at,
        source_url=ALIPAY_PAGE_URL,
    )


def parse_tbl_rmbjpy_html(html: str) -> float | None:
    soup = BeautifulSoup(html, "html.parser")
    element = soup.select_one("#tbl_RMBJPY")
    if element is None:
        return None

    text = element.get_text(strip=True)
    if not text:
        return None

    match = RATE_NUMBER_PATTERN.search(text)
    if match is None:
        return None
    return float(match.group())


def parse_rmb_js(text: str) -> ExchangeRateData:
    match = RMB_JPY_PATTERN.search(text)
    if match is None:
        raise ValueError("未在 rmb.js 中找到 RMBJPY 数据")
    return parse_rmb_jpy_line(match.group(1))


async def fetch_exchange_rate(
    *, force_refresh: bool = False
) -> tuple[ExchangeRateData, bool, str]:
    global _cache

    now = time.monotonic()
    if not force_refresh and _cache is not None and _cache.expires_at > now:
        return _cache.data, True, _cache.fetched_at

    async with httpx.AsyncClient(
        timeout=20,
        follow_redirects=True,
        headers=DEFAULT_HEADERS,
    ) as client:
        page_response = await client.get(ALIPAY_PAGE_URL)
        page_response.raise_for_status()

        rendered_rate = parse_tbl_rmbjpy_html(page_response.text)
        if rendered_rate is not None:
            data = ExchangeRateData(
                currency_name="日元",
                cny_per_100_jpy=rendered_rate,
                spot_cny_per_100_jpy=round(rendered_rate / ALIPAY_MARKUP, 3),
                updated_at=None,
                source_url=ALIPAY_PAGE_URL,
            )
        else:
            js_response = await client.get(RMB_JS_URL)
            js_response.raise_for_status()
            js_text = js_response.content.decode("gb2312", errors="replace")
            data = parse_rmb_js(js_text)

    fetched_at = format_fetched_at()
    _cache = _CacheEntry(data=data, expires_at=now + CACHE_TTL_SECONDS, fetched_at=fetched_at)
    return data, False, fetched_at
