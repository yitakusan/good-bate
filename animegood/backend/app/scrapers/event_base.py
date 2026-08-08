from __future__ import annotations

from dataclasses import dataclass

from app.event_source_config import EventSourceConfig


@dataclass(slots=True)
class RawEvent:
    title: str
    shop: str
    source_url: str
    source_platform: str
    summary: str = ""
    ip_hint: str | None = None
    image_url: str | None = None
    published_at: str | None = None
    ends_at: str | None = None


class EventScraper:
    source_platform: str

    async def scrape(
        self,
        source: EventSourceConfig,
        limit: int | None = None,
    ) -> list[RawEvent]:
        raise NotImplementedError
