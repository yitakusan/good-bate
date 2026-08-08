from __future__ import annotations

from fastapi import Header, HTTPException

from app.settings import Settings


def require_admin(
    settings: Settings,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    """未配置 admin_token 时放行；配置后必须匹配请求头。"""
    expected = settings.admin_token
    if not expected:
        return
    if not x_admin_token or x_admin_token != expected:
        raise HTTPException(
            status_code=401,
            detail="需要有效的管理口令（请求头 X-Admin-Token）",
        )
