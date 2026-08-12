"""Request-scoped actor for action logs / audit."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

current_actor_user_id: ContextVar[Optional[int]] = ContextVar(
    "current_actor_user_id", default=None
)


def set_actor_user_id(user_id: Optional[int]) -> None:
    current_actor_user_id.set(user_id)


def get_actor_user_id() -> Optional[int]:
    return current_actor_user_id.get()
