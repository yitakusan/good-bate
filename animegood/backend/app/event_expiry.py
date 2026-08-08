from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

RE_YMD_JA = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
RE_YMD_SLASH = re.compile(r"(\d{4})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{1,2})")
RE_RANGE_JA = re.compile(
    r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日[^0-9]*[〜～\-–—至]\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
)
RE_RANGE_SLASH = re.compile(
    r"(\d{4})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[〜～\-–—]\s*(\d{1,2})\s*[/.-]\s*(\d{1,2})"
)
RE_UNTIL_JA = re.compile(r"[〜～]\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*まで")
RE_MD_JA = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日")


def today_jst() -> date:
    return datetime.now(JST).date()


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_event_end_date(text: str, *, reference: date | None = None) -> date | None:
    """从标题/摘要中解析活动结束日（含当日仍视为未结束）。"""
    if not text.strip():
        return None

    reference = reference or today_jst()
    dates: list[date] = []

    for match in RE_RANGE_JA.finditer(text):
        parsed = _safe_date(int(match.group(1)), int(match.group(4)), int(match.group(5)))
        if parsed:
            dates.append(parsed)

    for match in RE_RANGE_SLASH.finditer(text):
        parsed = _safe_date(int(match.group(1)), int(match.group(4)), int(match.group(5)))
        if parsed:
            dates.append(parsed)

    for match in RE_YMD_JA.finditer(text):
        parsed = _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if parsed:
            dates.append(parsed)

    for match in RE_YMD_SLASH.finditer(text):
        parsed = _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if parsed:
            dates.append(parsed)

    for match in RE_UNTIL_JA.finditer(text):
        parsed = _safe_date(reference.year, int(match.group(1)), int(match.group(2)))
        if parsed:
            dates.append(parsed)

    if not dates:
        for match in RE_MD_JA.finditer(text):
            parsed = _safe_date(reference.year, int(match.group(1)), int(match.group(2)))
            if parsed:
                dates.append(parsed)

    if not dates:
        return None

    return max(dates)


def format_end_date(value: date) -> str:
    return value.isoformat()


def is_event_expired(ends_at: str | None, *, reference: date | None = None) -> bool:
    if not ends_at:
        return False
    reference = reference or today_jst()
    try:
        end_date = date.fromisoformat(ends_at[:10])
    except ValueError:
        return False
    return reference > end_date


def resolve_event_expiry(title: str, summary: str = "") -> str | None:
    for text in (title, summary):
        parsed = parse_event_end_date(text)
        if parsed:
            return format_end_date(parsed)
    return None
