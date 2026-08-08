"""Benchmark limit=20 with different site-level concurrency."""
from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path

from app.pipeline import ScrapePipeline
from app.scrapers.base_stores import BaseStoresScraper
from app.settings import Settings
from app.source_config import load_sources


async def bench_all(concurrency: int, limit: int = 20) -> tuple[float, dict[str, int]]:
    settings = Settings(scrape_concurrency=concurrency)
    started = time.perf_counter()
    result = await ScrapePipeline(settings).run_all(limit_per_source=limit)
    return time.perf_counter() - started, result


async def bench_source(source_id: str, limit: int = 20) -> tuple[float, int, str | None]:
    settings = Settings()
    source = next(item for item in load_sources(settings.source_config_path) if item.id == source_id)
    pipeline = ScrapePipeline(settings)
    started = time.perf_counter()
    outcome = await pipeline.run_source(source, limit=limit)
    elapsed = time.perf_counter() - started
    message = outcome.get("message")
    return elapsed, int(outcome["stored"]), str(message) if message else None


def latest_stores_errors(db_path: Path, limit: int = 5) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            """
            SELECT status, message, product_count, finished_at
            FROM source_runs
            WHERE source_id = 'shibuyatsutaya'
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()


async def main() -> None:
    limit = 20
    print(f"=== Full scrape limit_per_source={limit} ===")
    rows: list[tuple[int, float, dict[str, int]]] = []
    for concurrency in (1, 3, 5):
        elapsed, result = await bench_all(concurrency, limit=limit)
        rows.append((concurrency, elapsed, result))
        print(
            f"concurrency={concurrency}: {elapsed:.1f}s | "
            f"stored={result['stored']} failed={result['failed']} sources={result['sources']}"
        )

    baseline = rows[0][1]
    best = min(rows, key=lambda row: row[1])
    print(
        f"Best: concurrency={best[0]} -> {best[1]:.1f}s "
        f"(speedup {baseline / best[1]:.2f}x vs serial)"
    )

    print(f"\n=== Per-source limit={limit} (concurrency=3 pipeline) ===")
    for source_id in ("csmcanvas", "mono-mo", "shibuyatsutaya"):
        elapsed, stored, message = await bench_source(source_id, limit=limit)
        extra = f" | error: {message}" if message else ""
        print(f"{source_id}: {elapsed:.1f}s stored={stored}{extra}")

    print("\n=== STORES recent runs ===")
    for status, message, count, finished_at in latest_stores_errors(Path("data/animegood.sqlite")):
        print(f"{finished_at} | {status} | count={count} | {message}")


if __name__ == "__main__":
    asyncio.run(main())
