from __future__ import annotations

from app.scrapers.base import RawProduct, Scraper
from app.source_config import SourceConfig


class TemplateNotImplementedScraper(Scraper):
    def __init__(self, source_platform: str):
        self.source_platform = source_platform

    async def scrape(self, source: SourceConfig, limit: int | None = None) -> list[RawProduct]:
        raise NotImplementedError(
            f"{source.source_platform} 平台解析模板尚未实现，请在添加解析器前保持该数据源为禁用状态。"
        )
