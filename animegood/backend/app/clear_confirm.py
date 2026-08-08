from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

WAIT_SECONDS = 3
TOKEN_TTL_SECONDS = 120


@dataclass
class PendingClear:
    created_at: float


_pending: dict[str, PendingClear] = {}


def _prune_expired() -> None:
    now = time.time()
    expired = [
        token
        for token, pending in _pending.items()
        if now - pending.created_at > TOKEN_TTL_SECONDS
    ]
    for token in expired:
        _pending.pop(token, None)


def issue_clear_token() -> tuple[str, int, int]:
    _prune_expired()
    token = secrets.token_urlsafe(24)
    _pending[token] = PendingClear(created_at=time.time())
    return token, WAIT_SECONDS, TOKEN_TTL_SECONDS


def consume_clear_token(token: str) -> None:
    _prune_expired()
    pending = _pending.pop(token, None)
    if pending is None:
        raise ValueError("无效或已过期的确认令牌，请重新发起清空准备")

    elapsed = time.time() - pending.created_at
    if elapsed < WAIT_SECONDS:
        remaining = max(1, int(WAIT_SECONDS - elapsed + 0.999))
        raise ValueError(f"请等待 {remaining} 秒后再确认清空")
