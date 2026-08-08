from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.scrapers.base import RawProduct, Scraper
from app.source_config import SourceConfig

ITEM_PATH = re.compile(r"/view/item/(\d+)")
ITEM_PAGE_CONCURRENCY = 6
DEFAULT_LIST_PATH = "view/category/all_items"
MAX_LIST_PAGES = 30


class OchanokoScraper(Scraper):
    source_platform = "ochanoko"

    def __init__(self, timeout_seconds: float = 20):
        self.timeout_seconds = timeout_seconds

    async def scrape(self, source: SourceConfig, limit: int | None = None) -> list[RawProduct]:
        base_url = str(source.base_url).rstrip("/") + "/"
        list_paths = source.collections or [DEFAULT_LIST_PATH]
        item_urls = await self._discover_item_urls(base_url, list_paths)
        if not item_urls:
            raise RuntimeError(f"未在 {base_url} 找到おちゃのこ商品链接")
        if limit is not None:
            item_urls = item_urls[:limit]

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers=self._headers(base_url),
        ) as client:
            return await self._fetch_items(client, source, base_url, item_urls)

    async def _discover_item_urls(self, base_url: str, list_paths: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers=self._headers(base_url),
        ) as client:
            for list_path in list_paths:
                list_url = urljoin(base_url, list_path)
                for page_num in range(1, MAX_LIST_PAGES + 1):
                    params = {"page": page_num} if page_num > 1 else None
                    try:
                        response = await client.get(list_url, params=params)
                        response.raise_for_status()
                    except httpx.HTTPError:
                        break
                    new_count = 0
                    for item_id in ITEM_PATH.findall(response.text):
                        item_url = urljoin(base_url, f"view/item/{item_id}")
                        if item_url in seen:
                            continue
                        seen.add(item_url)
                        ordered.append(item_url)
                        new_count += 1
                    if page_num > 1 and new_count == 0:
                        break
        return ordered

    async def _fetch_items(
        self,
        client: httpx.AsyncClient,
        source: SourceConfig,
        base_url: str,
        item_urls: list[str],
    ) -> list[RawProduct]:
        semaphore = asyncio.Semaphore(ITEM_PAGE_CONCURRENCY)

        async def fetch_one(item_url: str) -> RawProduct:
            async with semaphore:
                response = await client.get(item_url)
                response.raise_for_status()
                return self._parse_item_page(source, item_url, response.text)

        return list(await asyncio.gather(*(fetch_one(item_url) for item_url in item_urls)))

    def _parse_item_page(self, source: SourceConfig, item_url: str, html: str) -> RawProduct:
        soup = BeautifulSoup(html, "html.parser")
        title = self._meta_content(soup, "og:title") or self._page_title(soup)
        title = title.split("|", 1)[0].strip() or "名称未取得"
        image_url = self._meta_content(soup, "og:image")
        if not image_url:
            image_tag = soup.select_one(".itemThumb img, .item_photo img, img")
            image_url = str(image_tag["src"]).strip() if image_tag and image_tag.get("src") else None

        text = soup.get_text(" ", strip=True)
        price = self._parse_price(text, html)
        stock_status = self._parse_stock_status(text, html)

        return RawProduct(
            product_name=title,
            shop=source.shop,
            source_url=item_url,
            source_platform=source.source_platform,
            search_text=title,
            price=price,
            stock_status=stock_status,
            image_url=image_url,
        )

    def _parse_price(self, text: str, html: str) -> int | None:
        for pattern in [r"￥\s*([\d,]+)", r"¥\s*([\d,]+)", r"([\d,]+)\s*円"]:
            match = re.search(pattern, text if "円" in pattern else html)
            if match:
                return int(match.group(1).replace(",", ""))
        return None

    def _parse_stock_status(self, text: str, html: str) -> str:
        if any(marker in text for marker in ("SOLD OUT", "売り切れ", "完売", "在庫なし", "品切れ")):
            return "缺货"
        if "カートに入れる" in html or "カートに追加" in html:
            return "可购买"
        return "未知"

    def _meta_content(self, soup: BeautifulSoup, key: str) -> str | None:
        tag = soup.find("meta", property=key) or soup.find("meta", attrs={"name": key})
        if tag and tag.get("content"):
            return str(tag["content"]).strip()
        return None

    def _page_title(self, soup: BeautifulSoup) -> str:
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        return "名称未取得"

    def _headers(self, referer: str) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ja,en-US;q=0.9",
            "Referer": referer,
        }
