"""Simple admin token gate (optional).

If STOCKGOOD_ADMIN_TOKEN is unset/empty, staff APIs stay open (local-only default).
When set, require matching X-Admin-Token header.
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Header, HTTPException

from app.settings import get_settings


def require_admin(
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> None:
    expected = get_settings().admin_token
    if not expected:
        return
    if not x_admin_token or x_admin_token != expected:
        raise HTTPException(status_code=401, detail="admin token required")


def admin_auth_required() -> bool:
    return bool(get_settings().admin_token)
