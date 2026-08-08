import asyncio
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from app.database import init_db
from app.pipeline import ScrapePipeline
from app.scrapers.base import RawProduct
from app.settings import Settings
from app.source_config import SourceConfig


def _make_source(source_id: str) -> SourceConfig:
    return SourceConfig(
        id=source_id,
        shop=f"Shop {source_id}",
        source_platform="shopify",
        base_url="https://example.com",
        enabled=True,
    )


class TrackingScraper:
    source_platform = "shopify"

    def __init__(self, delay: float = 0.05) -> None:
        self.delay = delay
        self.concurrent = 0
        self.max_concurrent = 0

    async def scrape(self, source: SourceConfig, limit: int | None = None) -> list[RawProduct]:
        self.concurrent += 1
        self.max_concurrent = max(self.max_concurrent, self.concurrent)
        await asyncio.sleep(self.delay)
        self.concurrent -= 1
        return [
            RawProduct(
                product_name=f"Product {source.id}",
                shop=source.shop,
                source_url=f"https://example.com/{source.id}",
                source_platform="shopify",
            )
        ]


def test_scrape_concurrency_setting_bounds() -> None:
    assert Settings(scrape_concurrency=1).scrape_concurrency == 1
    assert Settings(scrape_concurrency=8).scrape_concurrency == 8

    try:
        Settings(scrape_concurrency=0)
        raise AssertionError("expected ValidationError for scrape_concurrency=0")
    except ValidationError:
        pass

    try:
        Settings(scrape_concurrency=9)
        raise AssertionError("expected ValidationError for scrape_concurrency=9")
    except ValidationError:
        pass


def test_run_all_concurrent_aggregation(tmp_path: Path) -> None:
    asyncio.run(_run_all_concurrent_aggregation(tmp_path))


async def _run_all_concurrent_aggregation(tmp_path: Path) -> None:
    sources = [_make_source(f"src-{index}") for index in range(5)]
    scraper = TrackingScraper(delay=0.05)
    settings = Settings(
        database_path=tmp_path / "test.sqlite",
        source_config_path=tmp_path / "sources.json",
        ip_alias_path=tmp_path / "ip_aliases.json",
        name_glossary_path=tmp_path / "name_glossary.json",
        scrape_concurrency=3,
    )
    init_db(settings.database_path)

    with patch("app.pipeline.load_sources", return_value=sources):
        pipeline = ScrapePipeline(settings)
        pipeline.scrapers = {"shopify": scraper}
        result = await pipeline.run_all()

    assert result == {"sources": 5, "stored": 5, "failed": 0}
    assert scraper.max_concurrent <= 3
    assert scraper.max_concurrent > 1
