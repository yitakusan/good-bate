"""Bic Camera access-wall detection helpers."""

from __future__ import annotations

from urllib.parse import urlparse


def is_biccamera_url(url: str) -> bool:
    host = urlparse(url).netloc.lower().split(":", 1)[0]
    return host == "biccamera.com" or host.endswith(".biccamera.com")


def is_biccamera_blocked_page(html: str) -> bool:
    """Recognize rate-limit and bot-wall responses that have no product data."""
    lowered = (html or "").lower()
    markers = (
        "access denied",
        "access forbidden",
        "captcha",
        "robot check",
        "アクセスが集中",
        "しばらく時間をおいて",
        "不正なアクセス",
    )
    return any(marker in lowered for marker in markers)
