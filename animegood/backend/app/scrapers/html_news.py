from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from app.event_expiry import resolve_event_expiry
from app.event_source_config import EventSourceConfig
from app.scrapers.event_base import EventScraper, RawEvent

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

ARTICLE_CARD_SELECTORS = (
    ".article-item",
    "article.article",
    "article.article--layout",
    ".blog-post-list .block-list__item",
    ".article-card",
    "article",
)

RE_JA_DATE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")


def matches_keywords(
    text: str,
    *,
    include_keywords: list[str],
    exclude_keywords: list[str],
) -> bool:
    haystack = text.casefold()
    if exclude_keywords and any(kw.casefold() in haystack for kw in exclude_keywords if kw):
        return False
    if not include_keywords:
        return True
    return any(kw.casefold() in haystack for kw in include_keywords if kw)


def parse_published_at(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip()
    if not value:
        return None
    if "T" in value or value.count("-") >= 2:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass
    match = RE_JA_DATE.search(value)
    if match:
        year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return None
    return None


class HtmlNewsScraper(EventScraper):
    source_platform = "html-news"

    def __init__(self, timeout_seconds: float = 20):
        self.timeout_seconds = timeout_seconds

    async def scrape(
        self,
        source: EventSourceConfig,
        limit: int | None = None,
    ) -> list[RawEvent]:
        base_url = str(source.base_url).rstrip("/")
        list_url = urljoin(base_url + "/", source.list_path.lstrip("/"))

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers=DEFAULT_HEADERS,
        ) as client:
            response = await client.get(list_url)
            response.raise_for_status()
            events = self._parse_list_page(source, base_url, response.text, limit)

            for event in events:
                details = await self._fetch_article_details(client, event)
                event.image_url = details["image_url"]
                event.ends_at = details["ends_at"]
                if details["summary"]:
                    event.summary = details["summary"]
                if details["published_at"] and not event.published_at:
                    event.published_at = details["published_at"]

            events = [
                event
                for event in events
                if matches_keywords(
                    f"{event.title}\n{event.summary}",
                    include_keywords=source.include_keywords,
                    exclude_keywords=source.exclude_keywords,
                )
            ]

        return events

    def _parse_list_page(
        self,
        source: EventSourceConfig,
        base_url: str,
        html: str,
        limit: int | None,
    ) -> list[RawEvent]:
        soup = BeautifulSoup(html, "html.parser")
        cards = self._find_article_cards(soup)
        if cards:
            events = self._events_from_cards(source, base_url, cards, limit)
            if events:
                return events
        return self._events_from_anchors(source, base_url, soup, limit)

    def _find_article_cards(self, soup: BeautifulSoup) -> list[Tag]:
        for selector in ARTICLE_CARD_SELECTORS:
            nodes = [node for node in soup.select(selector) if isinstance(node, Tag)]
            if len(nodes) >= 2:
                return nodes
        return []

    def _events_from_cards(
        self,
        source: EventSourceConfig,
        base_url: str,
        cards: list[Tag],
        limit: int | None,
    ) -> list[RawEvent]:
        seen: set[str] = set()
        events: list[RawEvent] = []

        for card in cards:
            anchor = self._pick_article_anchor(card, source)
            if anchor is None:
                continue

            absolute = self._absolute_article_url(base_url, source, anchor["href"])
            if absolute is None or absolute in seen:
                continue

            title = self._card_title(card, anchor)
            if len(title) < source.title_min_length:
                continue

            # 列表页只做排除词；include 等拉完正文后再判，避免漏掉正文关键词
            if not matches_keywords(
                title,
                include_keywords=[],
                exclude_keywords=source.exclude_keywords,
            ):
                continue

            seen.add(absolute)
            published_at = self._extract_published_at(card)
            ends_at = resolve_event_expiry(title)
            events.append(
                RawEvent(
                    title=title,
                    shop=source.shop,
                    source_url=absolute,
                    source_platform=source.source_platform,
                    summary=title,
                    published_at=published_at,
                    ends_at=ends_at,
                )
            )
            if limit is not None and len(events) >= limit:
                break

        return events

    def _events_from_anchors(
        self,
        source: EventSourceConfig,
        base_url: str,
        soup: BeautifulSoup,
        limit: int | None,
    ) -> list[RawEvent]:
        seen: set[str] = set()
        events: list[RawEvent] = []

        for anchor in soup.find_all("a", href=True):
            absolute = self._absolute_article_url(base_url, source, anchor["href"])
            if absolute is None or absolute in seen:
                continue

            title = anchor.get_text(" ", strip=True)
            if len(title) < source.title_min_length:
                continue

            if not matches_keywords(
                title,
                include_keywords=[],
                exclude_keywords=source.exclude_keywords,
            ):
                continue

            seen.add(absolute)
            parent = anchor.parent if isinstance(anchor.parent, Tag) else None
            published_at = self._extract_published_at(parent) if parent else None
            ends_at = resolve_event_expiry(title)
            events.append(
                RawEvent(
                    title=title,
                    shop=source.shop,
                    source_url=absolute,
                    source_platform=source.source_platform,
                    summary=title,
                    published_at=published_at,
                    ends_at=ends_at,
                )
            )
            if limit is not None and len(events) >= limit:
                break

        return events

    def _pick_article_anchor(self, card: Tag, source: EventSourceConfig) -> Tag | None:
        candidates: list[Tag] = []
        for anchor in card.find_all("a", href=True):
            if source.url_prefix not in anchor["href"]:
                continue
            path = urlparse(urljoin("https://example.com/", anchor["href"])).path.rstrip("/")
            if path.endswith(source.list_path.rstrip("/")):
                continue
            candidates.append(anchor)
        if not candidates:
            return None

        titled = [a for a in candidates if len(a.get_text(" ", strip=True)) >= source.title_min_length]
        pool = titled or candidates
        return max(pool, key=lambda a: len(a.get_text(" ", strip=True)))

    def _card_title(self, card: Tag, anchor: Tag) -> str:
        for selector in (
            ".article-item__title",
            ".article__h3",
            "h1",
            "h2",
            "h3",
            ".article__title",
        ):
            node = card.select_one(selector)
            if node:
                text = node.get_text(" ", strip=True)
                if text:
                    return text
        return anchor.get_text(" ", strip=True)

    def _absolute_article_url(
        self,
        base_url: str,
        source: EventSourceConfig,
        href: str,
    ) -> str | None:
        href = href.strip()
        if source.url_prefix not in href:
            return None
        absolute = urljoin(base_url + "/", href.lstrip("/"))
        path = urlparse(absolute).path.rstrip("/")
        if path.endswith(source.list_path.rstrip("/")):
            return None
        return absolute

    def _extract_published_at(self, node: Tag) -> str | None:
        time_node = node.find("time")
        if time_node:
            return parse_published_at(time_node.get("datetime") or time_node.get_text(" ", strip=True))
        return None

    async def _fetch_article_details(
        self,
        client: httpx.AsyncClient,
        event: RawEvent,
    ) -> dict[str, str | None]:
        try:
            response = await client.get(event.source_url)
            response.raise_for_status()
        except httpx.HTTPError:
            return {
                "image_url": None,
                "ends_at": event.ends_at,
                "summary": event.summary,
                "published_at": event.published_at,
            }

        soup = BeautifulSoup(response.text, "html.parser")
        article_text = self._extract_article_text(soup)
        ends_at = resolve_event_expiry(event.title, article_text) or event.ends_at
        summary = self._extract_summary(article_text) or event.summary
        published_at = self._extract_published_at(soup) or event.published_at

        meta = soup.find("meta", property="og:image")
        content = meta.get("content").strip() if meta and meta.get("content") else None
        image_url = self._normalize_image_url(content, event.source_url)

        return {
            "image_url": image_url,
            "ends_at": ends_at,
            "summary": summary,
            "published_at": published_at,
        }

    def _extract_article_text(self, soup: BeautifulSoup) -> str:
        for selector in (
            ".article__content.rte",
            ".article__content",
            ".rte",
            "article .article__inner",
            "article",
        ):
            node = soup.select_one(selector)
            if node:
                return node.get_text("\n", strip=True)
        return ""

    def _extract_summary(self, article_text: str) -> str | None:
        if not article_text:
            return None
        for line in article_text.splitlines():
            cleaned = line.strip()
            if not cleaned:
                continue
            if "開催期間" in cleaned or "期間" in cleaned:
                return cleaned[:240]
        return article_text[:240]

    def _normalize_image_url(self, image_url: str | None, page_url: str) -> str | None:
        if not image_url:
            return None
        absolute = urljoin(page_url, image_url)
        if absolute.startswith("http://"):
            return "https://" + absolute.removeprefix("http://")
        return absolute
