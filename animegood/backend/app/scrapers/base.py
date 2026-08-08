from __future__ import annotations

from dataclasses import dataclass

from app.source_config import SourceConfig


@dataclass(slots=True)
class RawProduct:
    product_name: str
    shop: str
    source_url: str
    source_platform: str
    ip_hint: str | None = None
    search_text: str = ""
    stock_status: str = "未知"
    price: int | None = None
    release_date: str | None = None
    preorder_date: str | None = None
    image_url: str | None = None


class Scraper:
    source_platform: str

    async def scrape(self, source: SourceConfig, limit: int | None = None) -> list[RawProduct]:
        raise NotImplementedError
