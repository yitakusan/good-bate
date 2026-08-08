from __future__ import annotations

import asyncio
import re
from dataclasses import asdict
from hashlib import sha1

from app.database import (
    connect,
    deactivate_events_matching_keywords,
    insert_event_if_new,
    record_source_run,
    upsert_event,
    utc_now,
)
from app.event_expiry import is_event_expired, resolve_event_expiry
from app.event_source_config import EventSourceConfig, load_event_sources
from app.ip_normalizer import IpNormalizer
from app.scrapers.event_base import EventScraper, RawEvent
from app.scrapers.html_news import HtmlNewsScraper, matches_keywords
from app.settings import Settings

RUN_STATUS_SUCCESS = "成功"
RUN_STATUS_FAILED = "失败"


def normalize_title(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def build_event_dedupe_key(event: RawEvent, normalized_title: str) -> str:
    stable = f"{event.source_url}|{normalized_title}"
    return sha1(stable.encode("utf-8")).hexdigest()


def build_event_scrapers(settings: Settings) -> dict[str, EventScraper]:
    return {
        "html-news": HtmlNewsScraper(settings.request_timeout_seconds),
    }


class EventPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.scrapers = build_event_scrapers(settings)
        self.normalizer = IpNormalizer(settings.ip_alias_path)

    async def run_all(
        self,
        limit_per_source: int | None = None,
        *,
        source_ids: list[str] | None = None,
        incremental: bool = False,
    ) -> dict[str, int]:
        sources = [
            source
            for source in load_event_sources(self.settings.event_source_config_path)
            if source.enabled
        ]
        if source_ids:
            wanted = set(source_ids)
            sources = [source for source in sources if source.id in wanted]
        semaphore = asyncio.Semaphore(self.settings.scrape_concurrency)

        async def run_limited(source: EventSourceConfig) -> dict[str, int | str]:
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

        stored = 0
        skipped = 0
        failed = 0
        for result in results:
            if isinstance(result, BaseException):
                failed += 1
                continue
            stored += int(result["stored"])
            skipped += int(result.get("skipped") or 0)
            failed += 0 if result["status"] == RUN_STATUS_SUCCESS else 1

        return {
            "sources": len(sources),
            "stored": stored,
            "skipped": skipped,
            "failed": failed,
        }

    async def run_source(
        self,
        source: EventSourceConfig,
        limit: int | None = None,
        *,
        incremental: bool = False,
    ) -> dict[str, int | str]:
        started_at = utc_now()
        scraper = self.scrapers[source.source_platform]

        try:
            raw_events = await scraper.scrape(source, limit=limit)
            stored, skipped = self._store_events(raw_events, source, incremental=incremental)
            hidden = self._hide_noise_events(source)
            status = RUN_STATUS_SUCCESS
            notes: list[str] = []
            if incremental and skipped:
                notes.append(f"增量跳过已有 {skipped} 条")
            if hidden:
                notes.append(f"已隐藏噪音公告 {hidden} 条")
            message = "；".join(notes) or None
        except Exception as exc:
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

    def _hide_noise_events(self, source: EventSourceConfig) -> int:
        if not source.exclude_keywords:
            return 0
        with connect(self.settings.database_path) as conn:
            return deactivate_events_matching_keywords(
                conn,
                shop=source.shop,
                exclude_keywords=source.exclude_keywords,
            )

    def _store_events(
        self,
        events: list[RawEvent],
        source: EventSourceConfig,
        *,
        incremental: bool = False,
    ) -> tuple[int, int]:
        stored = 0
        skipped = 0
        with connect(self.settings.database_path) as conn:
            for event in events:
                if not matches_keywords(
                    f"{event.title}\n{event.summary}",
                    include_keywords=source.include_keywords,
                    exclude_keywords=source.exclude_keywords,
                ):
                    continue
                normalized_title = normalize_title(event.title)
                payload = asdict(event)
                ip_hint = payload.pop("ip_hint", None)
                payload["normalized_title"] = normalized_title
                payload["ip"] = ip_hint or self.normalizer.normalize(event.title)
                payload["dedupe_key"] = build_event_dedupe_key(event, normalized_title)
                payload["ends_at"] = event.ends_at or resolve_event_expiry(event.title, event.summary)
                payload["is_active"] = 0 if is_event_expired(payload["ends_at"]) else 1
                if incremental:
                    if insert_event_if_new(conn, payload):
                        if payload["is_active"]:
                            stored += 1
                    else:
                        skipped += 1
                else:
                    upsert_event(conn, payload)
                    if payload["is_active"]:
                        stored += 1
        return stored, skipped
