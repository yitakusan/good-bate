"""Backward-compatible admin token helpers (prefer app.auth)."""

from __future__ import annotations

from app.auth import auth_required as admin_auth_required
from app.auth import require_staff as require_admin

__all__ = ["admin_auth_required", "require_admin"]
