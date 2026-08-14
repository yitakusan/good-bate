"""In-memory rate limit for public scrape / submit endpoints."""

# ============================================================
# SHARED MODULE
#
# [用途] 公开接口限流
# [使用功能] FEATURE: ORDER_REQUEST
# ============================================================

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request

_lock = Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(request: Request, *, limit: int = 20, window: float = 60.0) -> None:
    """Allow `limit` calls per `window` seconds per client IP + path."""
    client = request.client.host if request.client else "unknown"
    key = f"{client}:{request.url.path}"
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(status_code=429, detail="too many requests, try later")
        q.append(now)
