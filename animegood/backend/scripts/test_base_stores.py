import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.scrapers.base_stores import BaseStoresScraper
from app.source_config import load_sources


async def main() -> None:
    scraper = BaseStoresScraper()
    sources = {source.id: source for source in load_sources(Path(__file__).resolve().parents[1] / "config" / "sources.json")}
    for source_id in ("csmcanvas", "shibuyatsutaya"):
        source = sources[source_id]
        products = await scraper.scrape(source, limit=3)
        print(source_id, len(products))
        for product in products:
            print(" ", product.product_name[:60], product.price, product.stock_status)


if __name__ == "__main__":
    asyncio.run(main())
