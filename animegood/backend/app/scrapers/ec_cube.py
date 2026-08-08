from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone

from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.scrapers.base import RawProduct, Scraper
from app.source_config import SourceConfig


class EcCubeScraper(Scraper):
    source_platform = "ec-cube"

    def __init__(self, timeout_seconds: float = 20):
        self.timeout_seconds = timeout_seconds

    async def scrape(self, source: SourceConfig, limit: int | None = None) -> list[RawProduct]:
        if "shop.yostar.co.jp" in str(source.base_url):
            return await YostarApiScraper(self.timeout_seconds).scrape(source, limit=limit)

        return await EcCubeHtmlScraper(self.timeout_seconds).scrape(source, limit=limit)


class YostarApiScraper(Scraper):
    source_platform = "ec-cube"
    api_base = "https://shop.yostar.co.jp/ecshop-api"

    def __init__(self, timeout_seconds: float = 20):
        self.timeout_seconds = timeout_seconds

    async def scrape(self, source: SourceConfig, limit: int | None = None) -> list[RawProduct]:
        category_ids = [int(value) for value in (source.collections or ["19"])]
        products: list[RawProduct] = []

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": "animegood/0.1 (+local crawler)",
                "Content-Type": "application/json",
                "Origin": "https://shop.yostar.co.jp",
                "Referer": "https://shop.yostar.co.jp/products/list",
            },
        ) as client:
            detail_semaphore = asyncio.Semaphore(8)
            seen_ids: set[int] = set()
            for category_id in category_ids:
                page = 1
                while True:
                    page_size = min(limit or 60, 60)
                    payload = await self._fetch_list(client, category_id, page, page_size)
                    items = payload.get("list") or []
                    if not items:
                        break
                    if limit is not None:
                        remaining = limit - len(products)
                        items = items[:remaining]

                    page_items = []
                    detail_tasks = []
                    for item in items:
                        product_id = int(item.get("id") or 0)
                        if not product_id or product_id in seen_ids:
                            continue
                        seen_ids.add(product_id)
                        page_items.append(item)
                        detail_tasks.append(
                            self._fetch_detail_with_limit(client, product_id, detail_semaphore)
                        )

                    details = await asyncio.gather(*detail_tasks, return_exceptions=True)
                    for item, detail_result in zip(page_items, details):
                        detail = detail_result if isinstance(detail_result, dict) else {}
                        products.append(self._parse_product(source, item, detail))
                        if limit is not None and len(products) >= limit:
                            return products

                    paginate = payload.get("paginate") or {}
                    total = int(paginate.get("total") or 0)
                    page_size = int(paginate.get("page_size") or len(items) or 20)
                    if page * page_size >= total:
                        break
                    page += 1

        return products

    async def _fetch_detail_with_limit(
        self,
        client: httpx.AsyncClient,
        product_id: int,
        semaphore: asyncio.Semaphore,
    ) -> dict:
        async with semaphore:
            return await self._fetch_detail(client, product_id)

    async def _fetch_list(
        self,
        client: httpx.AsyncClient,
        category_id: int,
        page: int,
        page_size: int,
    ) -> dict:
        response = await client.post(
            f"{self.api_base}/api/v1/product/list",
            json={
                "page": {"page": page, "page_size": page_size},
                "available_buy": 0,
                "category_id": category_id,
                "keyword": None,
                "sort_type": 2,
            },
        )
        response.raise_for_status()
        return self._unwrap(response.json())

    async def _fetch_detail(self, client: httpx.AsyncClient, product_id: int) -> dict:
        response = await client.post(
            f"{self.api_base}/api/v1/product/detail",
            json={"product_id": product_id},
        )
        response.raise_for_status()
        return self._unwrap(response.json())

    def _unwrap(self, payload: dict) -> dict:
        if payload.get("code") != 200:
            raise RuntimeError(payload.get("msg") or "Yostar API 返回错误")
        data = payload.get("data")
        if not isinstance(data, dict):
            return {}
        return data

    def _parse_product(
        self,
        source: SourceConfig,
        item: dict,
        detail: dict,
    ) -> RawProduct:
        product_id = int(item.get("id") or detail.get("id"))
        sku_list = detail.get("sku") or item.get("sku_list") or []
        detail_content = ((detail.get("detail") or {}).get("content") or "") + " " + (
            (detail.get("detail") or {}).get("hint") or ""
        )
        search_text = self._build_search_text(detail, item, detail_content)

        return RawProduct(
            product_name=detail.get("name") or item.get("name") or "名称未取得",
            shop=source.shop,
            source_url=f"https://shop.yostar.co.jp/products/detail/{product_id}",
            source_platform=source.source_platform,
            ip_hint=source.core_ips[0] if len(source.core_ips) == 1 else None,
            search_text=search_text,
            price=self._parse_price(sku_list, detail.get("price") or item.get("price")),
            stock_status=self._parse_stock_status(detail or item, sku_list),
            release_date=self._extract_release_date(detail_content, detail.get("publish_start_at")),
            preorder_date=self._timestamp_to_date(detail.get("buy_start_at") or item.get("buy_start_at")),
            image_url=detail.get("head_image") or item.get("head_image"),
        )

    def _parse_price(self, sku_list: list[dict], fallback: object) -> int | None:
        prices = [int(sku.get("price")) for sku in sku_list if sku.get("price")]
        if prices:
            return min(prices)
        if fallback:
            try:
                price = int(fallback)
                return price or None
            except (TypeError, ValueError):
                return None
        return None

    def _parse_stock_status(self, product: dict, sku_list: list[dict]) -> str:
        now = datetime.now(timezone.utc).timestamp()
        buy_start_at = self._parse_timestamp(product.get("buy_start_at"))
        buy_end_at = self._parse_timestamp(product.get("buy_end_at"))

        if buy_start_at and now < buy_start_at:
            return "未开售"
        if buy_end_at and now > buy_end_at:
            return "已结束"
        if not sku_list:
            return "未知"
        if any((sku.get("stock_unlimited") == 1) or int(sku.get("stock") or 0) > 0 for sku in sku_list):
            return "可购买"
        return "缺货"

    def _build_search_text(self, detail: dict, item: dict, detail_content: str) -> str:
        category_names: list[str] = []
        for category in detail.get("category_list") or []:
            category_names.append(str(category.get("name") or ""))
            for child in category.get("children") or []:
                category_names.append(str(child.get("name") or ""))

        parts = [
            item.get("description") or "",
            detail.get("description") or "",
            " ".join(category_names),
            BeautifulSoup(detail_content, "html.parser").get_text(" ", strip=True),
        ]
        return " ".join(part for part in parts if part)

    def _extract_release_date(self, html: str, fallback_timestamp: object = None) -> str | None:
        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        match = re.search(
            r"(?:お届け予定日|発売予定日|発売日|発送予定|発送開始|販売開始)"
            r"[^。．\n\r]*?(\d{4})年\s*(\d{1,2})月(?:\s*(\d{1,2})日)?",
            text,
        )
        if not match:
            return self._timestamp_to_date(fallback_timestamp)

        year = int(match.group(1))
        month = int(match.group(2))
        day = match.group(3)
        if day:
            return f"{year:04d}-{month:02d}-{int(day):02d}"
        return f"{year:04d}-{month:02d}"

    def _parse_timestamp(self, value: object) -> int | None:
        if not value:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _timestamp_to_date(self, value: object) -> str | None:
        timestamp = self._parse_timestamp(value)
        if timestamp is None:
            return None
        japan_tz = timezone(timedelta(hours=9))
        return datetime.fromtimestamp(timestamp, tz=japan_tz).date().isoformat()


DETAIL_PATH = re.compile(
    r"/products/detail(?:\.php\?product_id=(\d+)|/([^\"'\s>?#]+))",
    re.I,
)
ITEM_PAGE_CONCURRENCY = 6


class EcCubeHtmlScraper(Scraper):
    source_platform = "ec-cube"

    def __init__(self, timeout_seconds: float = 20):
        self.timeout_seconds = timeout_seconds

    async def scrape(self, source: SourceConfig, limit: int | None = None) -> list[RawProduct]:
        base_url = str(source.base_url).rstrip("/") + "/"
        list_paths = source.collections or ["products/list"]
        item_urls = await self._discover_item_urls(base_url, list_paths)
        if not item_urls:
            raise RuntimeError(f"未在 {base_url} 找到 EC-CUBE 商品链接")
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
                page = 1
                while True:
                    try:
                        response = await client.get(list_url, params={"page": page} if page > 1 else None)
                        response.raise_for_status()
                    except httpx.HTTPError:
                        break
                    batch = self._extract_detail_urls(base_url, response.text)
                    if not batch:
                        break
                    for item_url in batch:
                        if item_url not in seen:
                            seen.add(item_url)
                            ordered.append(item_url)
                    if page >= 30 or len(batch) < 5:
                        break
                    page += 1
        return ordered

    def _extract_detail_urls(self, base_url: str, html: str) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for match in DETAIL_PATH.finditer(html):
            product_id = match.group(1) or match.group(2)
            if not product_id or product_id.startswith("${"):
                continue
            if match.group(1):
                item_url = urljoin(base_url, f"products/detail.php?product_id={product_id}")
            else:
                item_url = urljoin(base_url, f"products/detail/{product_id}")
            if item_url not in seen:
                seen.add(item_url)
                urls.append(item_url)
        return urls

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
            image_tag = soup.select_one(".ec-productRole__profile img, .product_visual img, img")
            image_url = str(image_tag["src"]).strip() if image_tag and image_tag.get("src") else None
        text = soup.get_text(" ", strip=True)
        price = self._parse_price(soup, text, html)
        stock_status = self._parse_stock_status(text, html)
        release_date = self._extract_release_date(html)

        return RawProduct(
            product_name=title,
            shop=source.shop,
            source_url=item_url,
            source_platform=source.source_platform,
            search_text=title,
            price=price,
            stock_status=stock_status,
            release_date=release_date,
            image_url=image_url,
        )

    def _parse_price(self, soup: BeautifulSoup, text: str, html: str) -> int | None:
        for selector in [".price02-default", ".ec-price", ".item_price", ".price"]:
            node = soup.select_one(selector)
            if node:
                match = re.search(r"([\d,]+)", node.get_text(" ", strip=True))
                if match:
                    return int(match.group(1).replace(",", ""))
        match = re.search(r"([\d,]+)\s*円", text)
        if match:
            return int(match.group(1).replace(",", ""))
        match = re.search(r'"price"\s*:\s*"?([\d,]+)"?', html)
        if match:
            return int(match.group(1).replace(",", ""))
        return None

    def _parse_stock_status(self, text: str, html: str) -> str:
        if any(marker in text for marker in ("SOLD OUT", "売り切れ", "完売", "品切れ", "在庫なし")):
            return "缺货"
        if "予約" in text and "カート" in html:
            return "可购买"
        if "カートに入れる" in html or "カートに追加" in html:
            return "可购买"
        return "未知"

    def _extract_release_date(self, html: str) -> str | None:
        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        match = re.search(
            r"(?:お届け予定日|発売予定日|発売日|発送予定|出荷予定)"
            r"[^。．\n\r]*?(\d{4})年\s*(\d{1,2})月(?:\s*(\d{1,2})日)?",
            text,
        )
        if not match:
            return None
        year = int(match.group(1))
        month = int(match.group(2))
        day = match.group(3)
        if day:
            return f"{year:04d}-{month:02d}-{int(day):02d}"
        return f"{year:04d}-{month:02d}"

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
