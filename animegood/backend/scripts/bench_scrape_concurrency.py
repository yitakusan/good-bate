"""Quick scrape concurrency benchmark (limit_per_source=5)."""
from __future__ import annotations

import asyncio
import time

from app.pipeline import ScrapePipeline
from app.scrapers.base_stores import BaseStoresScraper
from app.settings import Settings
from app.source_config import load_sources


async def bench(concurrency: int, limit: int = 5) -> tuple[int, float, dict[str, int], int]:
    settings = Settings(scrape_concurrency=concurrency)
    sources = [source for source in load_sources(settings.source_config_path) if source.enabled]
    pipeline = ScrapePipeline(settings)
    started = time.perf_counter()
    result = await pipeline.run_all(limit_per_source=limit)
    elapsed = time.perf_counter() - started
    return concurrency, elapsed, result, len(sources)


async def bench_csmcanvas(limit: int = 5) -> float:
    settings = Settings()
    source = next(
        item for item in load_sources(settings.source_config_path) if item.id == "csmcanvas"
    )
    scraper = BaseStoresScraper(settings.request_timeout_seconds)
    started = time.perf_counter()
    products = await scraper.scrape(source, limit=limit)
    elapsed = time.perf_counter() - started
    print(f"  csmcanvas limit={limit}: {elapsed:.1f}s, products={len(products)}")
    return elapsed


async def main() -> None:
    limit = 5
    print(f"Benchmark: enabled sources, limit_per_source={limit}")
    rows: list[tuple[int, float, dict[str, int], int]] = []
    for concurrency in (1, 3, 5):
        rows.append(await bench(concurrency, limit=limit))

    baseline = rows[0][1]
    for concurrency, elapsed, result, source_count in rows:
        speedup = baseline / elapsed if elapsed > 0 else 0
        print(
            f"  concurrency={concurrency}: {elapsed:.1f}s "
            f"(speedup {speedup:.2f}x) | sources={source_count} "
            f"stored={result['stored']} failed={result['failed']}"
        )

    print("BASE item-page concurrency (csmcanvas):")
    await bench_csmcanvas(limit=limit)


if __name__ == "__main__":
    asyncio.run(main())
