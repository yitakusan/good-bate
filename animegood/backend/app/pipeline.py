from __future__ import annotations

import asyncio
import re
from dataclasses import asdict
from hashlib import sha1

from app.database import connect, insert_product_if_new, record_source_run, upsert_product, utc_now
from app.ip_normalizer import IpNormalizer
from app.product_display import resolve_display_name_zh
from app.series_extractor import extract_series
from app.scrapers.base import RawProduct, Scraper
from app.scrapers.base_stores import BaseStoresScraper
from app.scrapers.color_me import ColorMeScraper
from app.scrapers.ec_cube import EcCubeScraper
from app.scrapers.futureshop import FutureshopScraper
from app.scrapers.ochanoko import OchanokoScraper
from app.scrapers.placeholders import TemplateNotImplementedScraper
from app.scrapers.shopify import ShopifyScraper
from app.settings import Settings
from app.source_config import SourceConfig, load_sources

RUN_STATUS_SUCCESS = "成功"
RUN_STATUS_FAILED = "失败"


def normalize_name(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value).strip().lower()
    return normalized


def build_dedupe_key(product: RawProduct, normalized_name: str) -> str:
    stable = f"{product.source_url}|{normalized_name}"
    return sha1(stable.encode("utf-8")).hexdigest()


def build_scrapers(settings: Settings) -> dict[str, Scraper]:
    return {
        "shopify": ShopifyScraper(settings.request_timeout_seconds),
        "ec-cube": EcCubeScraper(settings.request_timeout_seconds),
        "base-stores": BaseStoresScraper(settings.request_timeout_seconds),
        "ochanoko": OchanokoScraper(settings.request_timeout_seconds),
        "color-me": ColorMeScraper(settings.request_timeout_seconds),
        "futureshop": FutureshopScraper(settings.request_timeout_seconds),
        "large-ec": TemplateNotImplementedScraper("large-ec"),
    }


class ScrapePipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.scrapers = build_scrapers(settings)
        self.normalizer = IpNormalizer(settings.ip_alias_path)

    async def run_all(
        self,
        limit_per_source: int | None = None,
        *,
        source_ids: list[str] | None = None,
        incremental: bool = False,
    ) -> dict[str, int]:
        sources = [source for source in load_sources(self.settings.source_config_path) if source.enabled]
        if source_ids:
            wanted = set(source_ids)
            sources = [source for source in sources if source.id in wanted]
        semaphore = asyncio.Semaphore(self.settings.scrape_concurrency)

        async def run_limited(source: SourceConfig) -> dict[str, int | str]:
            async with semaphore:
                return await self.run_source(
                    source,
                    limit=limit_per_source,
                    incremental=incremental,
                )

        results = await asyncio.gather(
            *[run_limited(source) for source in sources],
            return_exceptions=True,
        )

        total = 0
        skipped = 0
        failed = 0
        for result in results:
            if isinstance(result, BaseException):
                failed += 1
                continue
            total += int(result["stored"])
            skipped += int(result.get("skipped") or 0)
            failed += 0 if result["status"] == RUN_STATUS_SUCCESS else 1

        return {
            "sources": len(sources),
            "stored": total,
            "skipped": skipped,
            "failed": failed,
        }

    async def run_source(
        self,
        source: SourceConfig,
        limit: int | None = None,
        *,
        incremental: bool = False,
    ) -> dict[str, int | str]:
        started_at = utc_now()
        scraper = self.scrapers[source.source_platform]

        try:
            raw_products = await scraper.scrape(source, limit=limit)
            stored, skipped = self._store_products(raw_products, incremental=incremental)
            status = RUN_STATUS_SUCCESS
            message = None
            if incremental and skipped:
                message = f"增量跳过已有 {skipped} 条"
        except Exception as exc:
            # Do not deactivate existing rows on failure; the frontend keeps the
            # last successful data for this source instead of showing a blank state.
            stored = 0
            skipped = 0
            status = RUN_STATUS_FAILED
            message = str(exc).strip() or f"{type(exc).__name__}（无详细错误信息）"

        with connect(self.settings.database_path) as conn:
            record_source_run(
                conn,
                source_id=source.id,
                shop=source.shop,
                source_platform=source.source_platform,
                status=status,
                message=message,
                product_count=stored,
                started_at=started_at,
            )

        return {
            "source_id": source.id,
            "status": status,
            "stored": stored,
            "skipped": skipped,
            "message": message,
        }

    def _store_products(
        self,
        products: list[RawProduct],
        *,
        incremental: bool = False,
    ) -> tuple[int, int]:
        stored = 0
        skipped = 0
        with connect(self.settings.database_path) as conn:
            for product in products:
                normalized_name = normalize_name(product.product_name)
                payload = asdict(product)
                ip_hint = payload.pop("ip_hint", None)
                search_text = payload.get("search_text") or ""
                payload["normalized_name"] = normalized_name
                payload["ip"] = ip_hint or self.normalizer.normalize(
                    f"{product.product_name} {search_text}"
                )
                payload["display_name_zh"] = resolve_display_name_zh(
                    product.product_name,
                    glossary_path=self.settings.name_glossary_path,
                )
                payload["series"] = extract_series(product.product_name) or ""
                payload["dedupe_key"] = build_dedupe_key(product, normalized_name)
                if incremental:
                    if insert_product_if_new(conn, payload):
                        stored += 1
                    else:
                        skipped += 1
                else:
                    upsert_product(conn, payload)
                    stored += 1
        return stored, skipped
