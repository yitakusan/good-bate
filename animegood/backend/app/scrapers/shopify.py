from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from app.scrapers.base import RawProduct, Scraper
from app.source_config import SourceConfig

DETAIL_FETCH_CONCURRENCY = 6


class ShopifyScraper(Scraper):
    source_platform = "shopify"

    def __init__(self, timeout_seconds: float = 20):
        self.timeout_seconds = timeout_seconds

    async def scrape(self, source: SourceConfig, limit: int | None = None) -> list[RawProduct]:
        collections = source.collections or [""]
        products: list[RawProduct] = []

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
                "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            },
        ) as client:
            pending_details: list[tuple[RawProduct, dict]] = []
            for collection in collections:
                page = 1
                while True:
                    payload = await self._fetch_collection(
                        client,
                        str(source.base_url),
                        collection,
                        page,
                    )
                    page_products = payload.get("products", [])
                    if not page_products:
                        break
                    for item in page_products:
                        product = self._parse_product(source, item)
                        if product.release_date is None and limit is None:
                            pending_details.append((product, item))
                        products.append(product)
                        if limit is not None and len(products) >= limit:
                            if pending_details:
                                await self._enrich_release_dates(client, pending_details)
                            return products
                    if pending_details:
                        await self._enrich_release_dates(client, pending_details)
                        pending_details.clear()
                    if len(page_products) < 250:
                        break
                    page += 1

        return products

    async def _enrich_release_dates(
        self,
        client: httpx.AsyncClient,
        pending: list[tuple[RawProduct, dict]],
    ) -> None:
        semaphore = asyncio.Semaphore(DETAIL_FETCH_CONCURRENCY)

        async def enrich_one(product: RawProduct, item: dict) -> None:
            async with semaphore:
                detail_html = await self._fetch_product_detail(client, product.source_url)
                fallback_year = self._extract_year(item.get("published_at") or item.get("created_at"))
                product.release_date = self._extract_release_date(detail_html, fallback_year)

        await asyncio.gather(*(enrich_one(product, item) for product, item in pending))

    async def _fetch_collection(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        collection: str,
        page: int,
    ) -> dict:
        collection = collection.strip("/")
        if collection:
            url = urljoin(base_url.rstrip("/") + "/", f"collections/{collection}/products.json")
        else:
            url = urljoin(base_url.rstrip("/") + "/", "products.json")
        last_error = ""
        for attempt in range(4):
            try:
                if attempt:
                    await asyncio.sleep(1.5 * attempt)
                response = await client.get(
                    url,
                    params={"limit": 250, "page": page},
                    headers={"Accept": "application/json"},
                )
                if response.status_code in {429, 503}:
                    last_error = f"{response.status_code} {response.reason_phrase}"
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as exc:
                last_error = str(exc)
        raise RuntimeError(f"获取 Shopify 商品 JSON 失败：{last_error}")

    async def _fetch_product_detail(self, client: httpx.AsyncClient, url: str) -> str:
        request_url = url.replace("https://cocollabo.net/", "https://www.cocollabo.net/")
        fallback_html = ""
        last_error = ""
        for attempt in range(3):
            try:
                await asyncio.sleep(1.2 + attempt)
                response = await client.get(request_url)
                if response.status_code == 429:
                    last_error = "429 请求过于频繁"
                    continue
                response.raise_for_status()
                fallback_html = response.text
                if self._extract_release_date(
                    fallback_html,
                    self._extract_year_from_text(fallback_html),
                ):
                    return fallback_html
            except httpx.HTTPError as exc:
                last_error = str(exc)

        if "cocollabo.net" in request_url:
            playwright_html = await self._fetch_product_detail_with_playwright(request_url)
            if playwright_html:
                return playwright_html
            if fallback_html:
                return fallback_html
            return ""
        if fallback_html:
            return fallback_html
        return ""

    async def _fetch_product_detail_with_playwright(self, url: str) -> str:
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page(locale="ja-JP")
                await page.goto(url, wait_until="networkidle", timeout=30000)
                html = await page.content()
                await browser.close()
                return html
        except Exception:
            return ""

    def _parse_product(self, source: SourceConfig, item: dict) -> RawProduct:
        title = item.get("title") or item.get("handle") or "名称未取得"
        handle = item.get("handle")
        source_url = urljoin(str(source.base_url), f"/products/{handle}") if handle else str(source.base_url)
        images = item.get("images") or []
        variants = item.get("variants") or []
        first_variant = variants[0] if variants else {}
        body_html = item.get("body_html") or ""
        fallback_year = self._extract_year(item.get("published_at") or item.get("created_at"))

        return RawProduct(
            product_name=title,
            shop=source.shop,
            source_url=source_url,
            source_platform=source.source_platform,
            search_text=self._build_search_text(item),
            price=self._parse_price(first_variant.get("price")),
            stock_status=self._parse_stock_status(variants, body_html, fallback_year),
            release_date=(
                self._extract_release_date(body_html, fallback_year)
                or self._extract_source_specific_release_date(source, item)
            ),
            preorder_date=self._extract_preorder_date(body_html, fallback_year),
            image_url=images[0].get("src") if images else None,
        )

    def _parse_price(self, value: object) -> int | None:
        if value is None:
            return None
        try:
            return int(float(str(value)))
        except ValueError:
            return None

    def _build_search_text(self, item: dict) -> str:
        tags = item.get("tags") or []
        if isinstance(tags, str):
            tags_text = tags
        else:
            tags_text = " ".join(str(tag) for tag in tags)

        parts = [
            item.get("vendor") or "",
            item.get("product_type") or "",
            tags_text,
            self._html_to_text(item.get("body_html") or ""),
        ]
        return " ".join(part for part in parts if part)

    def _extract_source_specific_release_date(
        self,
        source: SourceConfig,
        item: dict,
    ) -> str | None:
        text = f"{item.get('title') or ''} {self._build_search_text(item)}"
        if "cocollabo.net" in str(source.base_url) and "秋葉原フェスティバル2026" in text:
            return "2026-10-下旬"
        return None

    def _parse_stock_status(
        self,
        variants: list[dict],
        body_html: str,
        fallback_year: int | None,
    ) -> str:
        preorder_window = self._extract_preorder_window(body_html, fallback_year)
        if preorder_window:
            now = datetime.now(timezone(timedelta(hours=9))).date()
            start_date, end_date = preorder_window
            if now < start_date:
                return "未开售"
            if now > end_date:
                return "已结束"

        if not variants:
            return "未知"
        if any(variant.get("available") is True for variant in variants):
            return "可购买"
        return "缺货"

    def _extract_release_date(self, html: str, fallback_year: int | None) -> str | None:
        soup = BeautifulSoup(html, "html.parser")
        hidden_date = self._extract_hidden_release_date(soup, fallback_year)
        if hidden_date:
            return hidden_date

        text = soup.get_text(" ", strip=True)
        match = re.search(
            r"(?:商品のお届け|お届け時期|お届け予定日|配送時期|配送予定|発売予定日|発売日|発送予定|出荷予定)"
            r"[^。．\n\r]*?(?:(\d{4})年)?\s*(\d{1,2})月\s*(上旬|中旬|下旬|\d{1,2}日)?",
            text,
        )
        if not match:
            match = re.search(
                r"(?:(\d{4})年)?\s*(\d{1,2})月\s*(上旬|中旬|下旬|\d{1,2}日)?"
                r"[^。．\n\r]*?(?:配送予定|発送予定|出荷予定|お届け予定|お届け時期|発売予定)",
                text,
            )
        if not match:
            return None

        year_text, month_text, day_or_period = match.groups()
        return self._format_japanese_date(year_text, month_text, day_or_period, fallback_year)

    def _extract_hidden_release_date(
        self,
        soup: BeautifulSoup,
        fallback_year: int | None,
    ) -> str | None:
        for input_el in soup.find_all("input"):
            name = str(input_el.get("name") or "")
            marker = input_el.has_attr("data-reservation-shipping-date")
            if "発送予定日" not in name and not marker:
                continue
            value = str(input_el.get("value") or "")
            match = re.search(
                r"(\d{4}年)?\s*(\d{1,2})月\s*(上旬|中旬|下旬|\d{1,2}日)?",
                value,
            )
            if match:
                return self._format_japanese_date(*match.groups(), fallback_year)
        return None

    def _format_japanese_date(
        self,
        year_text: str | None,
        month_text: str,
        day_or_period: str | None,
        fallback_year: int | None,
    ) -> str | None:
        year = int(year_text[:4]) if year_text else fallback_year
        if year is None:
            return None

        month = int(month_text)
        if not day_or_period:
            return f"{year:04d}-{month:02d}"
        if day_or_period.endswith("日"):
            return f"{year:04d}-{month:02d}-{int(day_or_period[:-1]):02d}"
        return f"{year:04d}-{month:02d}-{day_or_period}"

    def _extract_preorder_date(self, html: str, fallback_year: int | None) -> str | None:
        window = self._extract_preorder_window(html, fallback_year)
        if not window:
            return None
        return window[0].isoformat()

    def _extract_preorder_window(
        self,
        html: str,
        fallback_year: int | None,
    ) -> tuple[datetime.date, datetime.date] | None:
        if fallback_year is None:
            return None

        text = self._html_to_text(html)
        match = re.search(
            r"予約期間[:：]\s*(?:(\d{4})年)?\s*(\d{1,2})/(\d{1,2})"
            r".*?~\s*(?:(\d{4})年)?\s*(\d{1,2})/(\d{1,2})",
            text,
        )
        if not match:
            return None

        start_year = int(match.group(1)) if match.group(1) else fallback_year
        end_year = int(match.group(4)) if match.group(4) else start_year
        start_date = datetime(start_year, int(match.group(2)), int(match.group(3))).date()
        end_date = datetime(end_year, int(match.group(5)), int(match.group(6))).date()
        return start_date, end_date

    def _extract_year(self, value: object) -> int | None:
        if not value:
            return None
        match = re.match(r"(\d{4})", str(value))
        return int(match.group(1)) if match else None

    def _extract_year_from_text(self, value: str) -> int | None:
        match = re.search(r"(\d{4})年", value)
        return int(match.group(1)) if match else None

    def _html_to_text(self, html: str) -> str:
        return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
