from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from app.scrapers.base import RawProduct, Scraper
from app.source_config import SourceConfig

BASE_ITEM_ID = re.compile(r"/items/(\d+)")
STORES_ITEM_ID = re.compile(r"/items/([0-9a-f]{24})")
LIST_PATHS = ("", "items", "items/all", "categories/all")
ITEM_PAGE_CONCURRENCY = 6
# 列表翻页上限，避免个别站无限加载
MAX_LIST_PAGES = 30
LOAD_MORE_SELECTORS = (
    'a[rel="next"]',
    'button[rel="next"]',
    'a:has-text("もっと見る")',
    'button:has-text("もっと見る")',
    'a:has-text("次へ")',
    'button:has-text("次へ")',
    'a:has-text("次のページ")',
    '.c-pagination__next a',
    '[class*="pagination"] a[aria-label*="次"]',
    '[class*="Pager"] a[rel="next"]',
)


class BaseStoresScraper(Scraper):
    source_platform = "base-stores"

    def __init__(self, timeout_seconds: float = 20):
        self.timeout_seconds = timeout_seconds

    async def scrape(self, source: SourceConfig, limit: int | None = None) -> list[RawProduct]:
        base_url = str(source.base_url).rstrip("/") + "/"
        platform = self._detect_platform(base_url)
        if platform == "stores":
            return await self._scrape_stores(source, base_url, limit)

        item_urls = await self._discover_item_urls(base_url, platform)
        if not item_urls:
            raise RuntimeError(f"未在 {base_url} 找到商品链接")
        if limit is not None:
            item_urls = item_urls[:limit]

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers=self._default_headers(base_url),
        ) as client:
            return await self._fetch_item_pages(client, source, item_urls, platform)

    async def _fetch_item_pages(
        self,
        client: httpx.AsyncClient,
        source: SourceConfig,
        item_urls: list[str],
        platform: str,
    ) -> list[RawProduct]:
        semaphore = asyncio.Semaphore(ITEM_PAGE_CONCURRENCY)

        async def fetch_one(item_url: str) -> RawProduct:
            async with semaphore:
                html = await self._fetch_html(client, item_url, platform)
                return self._parse_item_page(source, item_url, html, platform)

        results = await asyncio.gather(*(fetch_one(item_url) for item_url in item_urls))
        return list(results)

    async def _scrape_stores(
        self,
        source: SourceConfig,
        base_url: str,
        limit: int | None,
    ) -> list[RawProduct]:
        try:
            products = await asyncio.to_thread(
                self._scrape_stores_paginated_sync,
                source,
                base_url,
                limit,
            )
        except RuntimeError:
            raise
        except Exception as exc:
            raise self._playwright_runtime_error(exc) from exc

        if not products:
            raise RuntimeError(f"未在 {base_url} 找到商品链接")
        if limit is not None:
            return products[:limit]
        return products

    def _scrape_stores_paginated_sync(
        self,
        source: SourceConfig,
        base_url: str,
        limit: int | None,
    ) -> list[RawProduct]:
        """首页渲染后继续：优先点「もっと見る/次へ」，否则尝试 ?page=N。"""
        user_agent = self._default_headers(base_url)["User-Agent"]
        products: list[RawProduct] = []
        seen: set[str] = set()

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(locale="ja-JP", user_agent=user_agent)
                page.goto(base_url, wait_until="networkidle", timeout=90000)
                self._wait_for_item_links_sync(page)

                pages_done = 0
                while pages_done < MAX_LIST_PAGES:
                    batch = self._parse_stores_list_page(source, base_url, page.content())
                    for product in batch:
                        if product.source_url in seen:
                            continue
                        seen.add(product.source_url)
                        products.append(product)
                        if limit is not None and len(products) >= limit:
                            return products

                    pages_done += 1
                    if pages_done >= MAX_LIST_PAGES:
                        break

                    # 1) 同页「加载更多 / 下一页」
                    if self._click_list_next_sync(page):
                        self._wait_for_item_links_sync(page)
                        page.wait_for_timeout(800)
                        continue

                    # 2) URL 翻页
                    next_page = pages_done + 1
                    advanced = False
                    for candidate in (
                        urljoin(base_url, f"?page={next_page}"),
                        urljoin(base_url, f"items?page={next_page}"),
                    ):
                        page.goto(candidate, wait_until="networkidle", timeout=90000)
                        self._wait_for_item_links_sync(page)
                        peek = self._parse_stores_list_page(source, base_url, page.content())
                        if any(item.source_url not in seen for item in peek):
                            advanced = True
                            break
                    if not advanced:
                        break

                return products
            finally:
                browser.close()

    def _click_list_next_sync(self, page) -> bool:
        for selector in LOAD_MORE_SELECTORS:
            try:
                locator = page.locator(selector).first
                if locator.count() == 0:
                    continue
                if not locator.is_visible():
                    continue
                locator.click(timeout=5000)
                return True
            except Exception:
                continue
        return False

    def _parse_stores_list_page(
        self,
        source: SourceConfig,
        base_url: str,
        html: str,
    ) -> list[RawProduct]:
        soup = BeautifulSoup(html, "html.parser")
        host = urlparse(base_url).netloc
        scheme = urlparse(base_url).scheme
        products: list[RawProduct] = []
        seen: set[str] = set()

        for item in soup.select("li.c-itemList__item"):
            item_id = item.get("id", "")
            if not STORES_ITEM_ID.fullmatch(f"/items/{item_id}"):
                continue
            link = item.select_one("a.c-itemList__item-link")
            href = link.get("href") if link else f"/items/{item_id}"
            item_url = urljoin(f"{scheme}://{host}/", href)

            name_tag = item.select_one(".c-itemList__item-name")
            title = name_tag.get_text(strip=True) if name_tag else None
            if not title:
                image_tag = item.select_one("img")
                title = image_tag.get("alt", "").strip() if image_tag else ""
            if not title:
                continue

            price_tag = item.select_one(".c-itemList__item-price-number")
            price = None
            if price_tag and price_tag.get("aria-label"):
                price = self._parse_yen_label(str(price_tag["aria-label"]))
            if price is None and price_tag:
                price = self._parse_price_from_html(price_tag.get_text(" ", strip=True), price_tag.get_text(" ", strip=True))

            image_tag = item.select_one("img")
            image_url = str(image_tag["src"]).strip() if image_tag and image_tag.get("src") else None

            item_text = item.get_text(" ", strip=True)
            stock_status = self._parse_list_stock_status(item_text, str(item))

            if item_url in seen:
                continue
            seen.add(item_url)
            products.append(
                RawProduct(
                    product_name=self._clean_title(title),
                    shop=source.shop,
                    source_url=item_url,
                    source_platform=source.source_platform,
                    search_text=title,
                    price=price,
                    stock_status=stock_status,
                    release_date=None,
                    image_url=image_url,
                )
            )
        return products

    def _parse_yen_label(self, label: str) -> int | None:
        match = re.search(r"([\d,]+)\s*円", label)
        if match:
            return int(match.group(1).replace(",", ""))
        return None

    def _detect_platform(self, base_url: str) -> str:
        host = urlparse(base_url).netloc.lower()
        if host.endswith(".stores.jp"):
            return "stores"
        return "base"

    def _default_headers(self, referer: str) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Referer": referer,
        }

    async def _discover_item_urls(self, base_url: str, platform: str) -> list[str]:
        if platform == "stores":
            # STORES 走 _scrape_stores 分页逻辑；此处仅作兜底
            rendered = await self._fetch_html_playwright(base_url)
            return self._extract_item_urls(base_url, rendered, platform)

        discovered: list[str] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers=self._default_headers(base_url),
        ) as client:
            for path in LIST_PATHS:
                list_url = urljoin(base_url, path)
                stagnant = 0
                for page_num in range(1, MAX_LIST_PAGES + 1):
                    params = {"page": page_num} if page_num > 1 else None
                    try:
                        response = await client.get(list_url, params=params)
                        if response.status_code >= 400:
                            break
                        html = response.text
                    except httpx.HTTPError:
                        break
                    batch = self._extract_item_urls(base_url, html, platform)
                    new_count = 0
                    for item_url in batch:
                        if item_url in seen:
                            continue
                        seen.add(item_url)
                        discovered.append(item_url)
                        new_count += 1
                    if page_num > 1 and new_count == 0:
                        stagnant += 1
                        if stagnant >= 1:
                            break
                    else:
                        stagnant = 0

        if discovered:
            return discovered

        rendered = await self._fetch_html_playwright(base_url)
        return self._extract_item_urls(base_url, rendered, platform)

    def _extract_item_urls(self, base_url: str, html: str, platform: str) -> list[str]:
        pattern = STORES_ITEM_ID if platform == "stores" else BASE_ITEM_ID
        host = urlparse(base_url).netloc
        urls: list[str] = []
        seen: set[str] = set()
        for match in pattern.finditer(html):
            item_id = match.group(1)
            item_url = f"{urlparse(base_url).scheme}://{host}/items/{item_id}"
            if item_url not in seen:
                seen.add(item_url)
                urls.append(item_url)
        return urls

    async def _fetch_html(
        self,
        client: httpx.AsyncClient,
        url: str,
        platform: str,
        allow_empty: bool = False,
    ) -> str:
        try:
            response = await client.get(url)
            if response.status_code == 403 and platform == "stores":
                return await self._fetch_html_playwright(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError:
            if allow_empty:
                return ""
            return await self._fetch_html_playwright(url)

    async def _fetch_html_playwright(self, url: str) -> str:
        try:
            return await asyncio.to_thread(self._fetch_html_playwright_sync, url)
        except RuntimeError:
            raise
        except Exception as exc:
            raise self._playwright_runtime_error(exc) from exc

    def _fetch_html_playwright_sync(self, url: str) -> str:
        user_agent = self._default_headers(url)["User-Agent"]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(locale="ja-JP", user_agent=user_agent)
                page.goto(url, wait_until="networkidle", timeout=90000)
                self._wait_for_item_links_sync(page)
                return page.content()
            finally:
                browser.close()

    def _wait_for_item_links_sync(self, page) -> None:
        try:
            page.wait_for_selector('a[href*="/items/"]', timeout=15000)
        except Exception:
            page.wait_for_timeout(2000)

    def _playwright_runtime_error(self, exc: Exception) -> RuntimeError:
        message = str(exc)
        if "Executable doesn't exist" in message:
            return RuntimeError(
                "Playwright 浏览器未安装，请在 backend 目录执行：playwright install chromium"
            )
        return RuntimeError(f"Playwright 获取页面失败：{exc}")

    def _parse_item_page(
        self,
        source: SourceConfig,
        item_url: str,
        html: str,
        platform: str,
    ) -> RawProduct:
        soup = BeautifulSoup(html, "html.parser")
        title = self._meta_content(soup, "og:title") or self._page_title(soup)
        image_url = self._meta_content(soup, "og:image")
        text = soup.get_text(" ", strip=True)
        price = self._parse_price_from_html(html, text)
        stock_status = self._parse_stock_status(text, html)
        release_date = self._extract_release_date(text)
        search_text = self._meta_content(soup, "og:description") or ""

        if platform == "base":
            datalayer = self._parse_base_datalayer(html)
            title = datalayer.get("product_name") or title
            price = datalayer.get("price") or price

        return RawProduct(
            product_name=self._clean_title(title),
            shop=source.shop,
            source_url=item_url,
            source_platform=source.source_platform,
            search_text=search_text,
            price=price,
            stock_status=stock_status,
            release_date=release_date,
            image_url=image_url,
        )

    def _parse_base_datalayer(self, html: str) -> dict[str, object]:
        payload: dict[str, object] = {}
        price_match = re.search(r"'itemPrice':\s*(\d+)", html)
        if price_match:
            payload["price"] = int(price_match.group(1))

        name_match = re.search(r"'item_name':\s*\"((?:\\.|[^\"])*)\"", html)
        if name_match:
            payload["product_name"] = json.loads(f"\"{name_match.group(1)}\"")

        if "product_name" not in payload:
            ga4_match = re.search(r"'GA4ViewItems':\s*\[\s*\{([^}]+)\}", html, re.S)
            if ga4_match:
                block = "{" + ga4_match.group(1) + "}"
                block = re.sub(r"(\w+):", r'"\1":', block)
                block = block.replace("'", '"')
                try:
                    item = json.loads(block)
                    if item.get("item_name"):
                        payload["product_name"] = item["item_name"]
                    if item.get("price"):
                        payload["price"] = int(item["price"])
                except json.JSONDecodeError:
                    pass
        return payload

    def _parse_price_from_html(self, html: str, text: str) -> int | None:
        for pattern in [
            r"'itemPrice':\s*(\d+)",
            r'"price"\s*:\s*(\d+)',
            r"¥\s*([\d,]+)",
            r"([\d,]+)\s*円",
        ]:
            match = re.search(pattern, html if "itemPrice" in pattern else text)
            if match:
                return int(match.group(1).replace(",", ""))
        return None

    def _parse_list_stock_status(self, text: str, html: str) -> str:
        if any(marker in text for marker in ("SOLD OUT", "売り切れ", "完売", "在庫なし")):
            return "缺货"
        if "販売期間" in text:
            window = self._extract_sales_window(text)
            if window:
                now = datetime.now(timezone(timedelta(hours=9)))
                if now < window[0]:
                    return "未开售"
                if now > window[1]:
                    return "已结束"
        return "可购买"

    def _parse_stock_status(self, text: str, html: str) -> str:
        lowered = text.lower()
        if any(marker in text for marker in ("SOLD OUT", "売り切れ", "完売", "在庫なし")):
            return "缺货"
        if "販売期間" in text:
            window = self._extract_sales_window(text)
            if window:
                now = datetime.now(timezone(timedelta(hours=9)))
                if now < window[0]:
                    return "未开售"
                if now > window[1]:
                    return "已结束"
        if "カートに入れる" in html or "カートに追加" in html or "購入する" in text:
            return "可购买"
        if "予約" in text and "SOLD OUT" not in text:
            return "可购买"
        return "未知"

    def _extract_sales_window(self, text: str) -> tuple[datetime, datetime] | None:
        match = re.search(
            r"販売期間\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s*\d{0,2}:?\d{0,2}\s*〜\s*"
            r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})",
            text,
        )
        if not match:
            return None
        tz = timezone(timedelta(hours=9))
        start = datetime(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            tzinfo=tz,
        )
        end = datetime(
            int(match.group(4)),
            int(match.group(5)),
            int(match.group(6)),
            23,
            59,
            59,
            tzinfo=tz,
        )
        return start, end

    def _extract_release_date(self, text: str) -> str | None:
        match = re.search(
            r"開催日\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})",
            text,
        )
        if match:
            return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

        match = re.search(
            r"(?:商品のお届け|お届け予定日|発売予定日|発売日|発送予定|出荷予定|お届け時期)"
            r"[^。．\n\r]*?(?:(\d{4})年)?\s*(\d{1,2})月\s*(上旬|中旬|下旬|\d{1,2}日)?",
            text,
        )
        if not match:
            match = re.search(
                r"(\d{4})年\s*(\d{1,2})月\s*(上旬|中旬|下旬|\d{1,2}日)?"
                r"[^。．\n\r]*?(?:発送予定|出荷予定|お届け予定|発売予定)",
                text,
            )
        if not match:
            return None

        year_text, month_text, day_or_period = match.groups()
        year = int(year_text) if year_text else datetime.now(timezone(timedelta(hours=9))).year
        month = int(month_text)
        if not day_or_period:
            return f"{year:04d}-{month:02d}"
        if day_or_period.endswith("日"):
            return f"{year:04d}-{month:02d}-{int(day_or_period[:-1]):02d}"
        return f"{year:04d}-{month:02d}-{day_or_period}"

    def _meta_content(self, soup: BeautifulSoup, key: str) -> str | None:
        tag = soup.find("meta", property=key) or soup.find("meta", attrs={"name": key})
        if tag and tag.get("content"):
            return str(tag["content"]).strip()
        return None

    def _page_title(self, soup: BeautifulSoup) -> str:
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        return "名称未取得"

    def _clean_title(self, title: str) -> str:
        cleaned = title.split("|", 1)[0].strip()
        cleaned = re.sub(r"\s+powered by BASE.*$", "", cleaned, flags=re.I).strip()
        return cleaned or "名称未取得"
