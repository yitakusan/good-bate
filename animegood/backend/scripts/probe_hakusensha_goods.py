import asyncio
import re

import httpx

from app.pipeline import ScrapePipeline
from app.settings import Settings
from app.source_config import load_sources

BASE = "https://goods.hakusensha-shop.jp/"


async def probe() -> None:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
        for path in ("", "products/list", "products/list.php"):
            url = BASE.rstrip("/") + (f"/{path}" if path else "/")
            response = await client.get(url)
            detail = len(re.findall(r"/products/detail/[^\"']+", response.text))
            detail_php = len(re.findall(r"products/detail.php", response.text))
            print(path or "/", response.status_code, detail, detail_php)


async def scrape_test() -> None:
    settings = Settings()
    source = next(item for item in load_sources(settings.source_config_path) if item.id == "hakusensha-shop")
  # temporarily patch url for test - will update json
    from dataclasses import replace
    source = replace(source, base_url=BASE, enabled=True)
    result = await ScrapePipeline(settings).run_source(source, limit=3)
    print("scrape", result)


async def main() -> None:
    await probe()
    await scrape_test()


if __name__ == "__main__":
    asyncio.run(main())
