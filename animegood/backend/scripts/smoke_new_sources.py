"""Smoke-test newly enabled sources with limit=3."""
from __future__ import annotations

import asyncio

from app.pipeline import ScrapePipeline
from app.settings import Settings
from app.source_config import load_sources

NEWLY_ENABLED = [
    "miraithings",
    "pricafe",
    "i-rightsshop",
    "vvstore",
    "hakuichi",
    "shop-asobistore",
    "medicos-e-shop",
    "store-kadokawa",
]


async def main() -> None:
    settings = Settings()
    pipeline = ScrapePipeline(settings)
    sources = {source.id: source for source in load_sources(settings.source_config_path)}
    for source_id in NEWLY_ENABLED:
        source = sources[source_id]
        result = await pipeline.run_source(source, limit=3)
        print(
            f"{source_id}: {result['status']} stored={result['stored']} "
            f"message={result.get('message')}"
        )


if __name__ == "__main__":
    asyncio.run(main())
