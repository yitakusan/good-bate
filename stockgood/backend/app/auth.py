"""Session cookie auth + optional legacy admin token."""

# ============================================================
# FEATURE: AUTH
#
# [用途] 密码哈希、Cookie 会话、角色依赖（require_staff 等）
# [接口] /api/auth/*  /api/users*
# [数据库] users, sessions
# [代码索引] docs/CODE_INDEX.md#feature-auth
# ============================================================
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal, Optional

from fastapi import Cookie, Depends, Header, HTTPException, Request, Response
from passlib.context import CryptContext

from app.auth_context import set_actor_user_id
from app.database import get_conn, row_to_dict
from app.settings import get_settings

UserRole = Literal["admin", "warehouse", "finance", "customer"]
STAFF_ROLES: frozenset[str] = frozenset({"admin", "warehouse", "finance"})
SESSION_COOKIE = "stockgood_session"
SESSION_DAYS = 14

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().replace(microsecond=0).isoformat()


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _pwd.verify(password, password_hash)
    except Exception:
        return False


def hash_session_token(token: str) -> str:
    secret = get_settings().session_secret or "stockgood-dev-session"
    return hmac.new(
        secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def user_count() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        return int(row["c"] if row else 0)


def auth_required() -> bool:
    settings = get_settings()
    if settings.auth_required is True:
        return True
    if settings.auth_required is False:
        return False
    if settings.admin_token:
        return True
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c FROM users
            WHERE role IN ('admin', 'warehouse', 'finance') AND is_active = 1
            """
        ).fetchone()
        return int(row["c"] if row else 0) > 0


def user_out(row: Any) -> dict[str, Any]:
    data = row_to_dict(row) or {}
    return {
        "id": int(data["id"]),
        "email": data.get("email") or "",
        "display_name": data.get("display_name") or "",
        "role": data.get("role") or "customer",
        "is_active": bool(data.get("is_active", 1)),
        "created_at": data.get("created_at") or "",
    }


def get_user_by_id(user_id: int) -> Optional[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return user_out(row) if row else None


def get_user_by_email(email: str) -> Optional[dict[str, Any]]:
    email = email.strip().lower()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE lower(email) = ?", (email,)
        ).fetchone()
        if not row:
            return None
        data = row_to_dict(row) or {}
        out = user_out(row)
        out["_password_hash"] = data.get("password_hash") or ""
        return out


def create_user(
    *,
    email: str,
    password: str,
    role: UserRole,
    display_name: str = "",
) -> dict[str, Any]:
    email_n = email.strip().lower()
    if not email_n or "@" not in email_n:
        raise HTTPException(status_code=400, detail="invalid email")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="password must be at least 8 characters")
    if role not in ("admin", "warehouse", "finance", "customer"):
        raise HTTPException(status_code=400, detail="invalid role")
    now = _now_iso()
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE lower(email) = ?", (email_n,)
        ).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail="email already registered")
        cur = conn.execute(
            """
            INSERT INTO users (email, password_hash, role, display_name, is_active, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (
                email_n,
                hash_password(password),
                role,
                (display_name or "").strip() or email_n.split("@")[0],
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return user_out(row)


def list_users() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY id ASC"
        ).fetchall()
        return [user_out(r) for r in rows]


def set_user_active(user_id: int, is_active: bool) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="user not found")
        conn.execute(
            "UPDATE users SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, user_id),
        )
        if not is_active:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        updated = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return user_out(updated)


def change_password(user_id: int, new_password: str) -> None:
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="password must be at least 8 characters")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="user not found")
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(new_password), user_id),
        )
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def create_session(user_id: int, response: Response) -> str:
    raw = secrets.token_urlsafe(32)
    token_hash = hash_session_token(raw)
    expires = (_now() + timedelta(days=SESSION_DAYS)).replace(microsecond=0)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO sessions (token_hash, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (token_hash, user_id, _now_iso(), expires.isoformat()),
        )
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=raw,
        httponly=True,
        samesite="lax",
        secure=bool(settings.cookie_secure),
        max_age=SESSION_DAYS * 24 * 3600,
        path="/",
    )
    return raw


def clear_session(response: Response, raw_token: Optional[str]) -> None:
    if raw_token:
        token_hash = hash_session_token(raw_token)
        with get_conn() as conn:
            conn.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (token_hash,)
            )
    response.delete_cookie(SESSION_COOKIE, path="/")


def _user_from_session(raw_token: Optional[str]) -> Optional[dict[str, Any]]:
    if not raw_token:
        return None
    token_hash = hash_session_token(raw_token)
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT u.*, s.expires_at AS session_expires_at
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        if not row:
            return None
        exp = row["session_expires_at"]
        if exp:
            try:
                exp_dt = datetime.fromisoformat(str(exp))
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if exp_dt < _now():
                    conn.execute(
                        "DELETE FROM sessions WHERE token_hash = ?", (token_hash,)
                    )
                    return None
            except ValueError:
                pass
        if not row["is_active"]:
            return None
        return user_out(row)


def _legacy_admin_user(
    x_admin_token: Optional[str],
) -> Optional[dict[str, Any]]:
    expected = get_settings().admin_token
    if not expected or not x_admin_token or x_admin_token != expected:
        return None
    return {
        "id": 0,
        "email": "legacy-admin-token",
        "display_name": "Admin Token",
        "role": "admin",
        "is_active": True,
        "created_at": "",
    }


def resolve_user(
    request: Request,
    stockgood_session: Annotated[Optional[str], Cookie(alias=SESSION_COOKIE)] = None,
    x_admin_token: Annotated[Optional[str], Header(alias="X-Admin-Token")] = None,
) -> Optional[dict[str, Any]]:
    user = _user_from_session(stockgood_session)
    if not user:
        user = _legacy_admin_user(x_admin_token)
    if user:
        set_actor_user_id(int(user["id"]) if user["id"] else None)
        request.state.user = user
    else:
        set_actor_user_id(None)
        request.state.user = None
    return user


def get_optional_user(
    user: Annotated[Optional[dict[str, Any]], Depends(resolve_user)],
) -> Optional[dict[str, Any]]:
    return user


def get_current_user(
    user: Annotated[Optional[dict[str, Any]], Depends(resolve_user)],
) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="login required")
    return user


def require_staff(
    user: Annotated[Optional[dict[str, Any]], Depends(resolve_user)],
) -> dict[str, Any]:
    if not auth_required():
        if user and user["role"] not in STAFF_ROLES and user["role"] != "admin":
            # open local mode but customer session should not hit staff APIs
            if user["role"] == "customer":
                raise HTTPException(status_code=403, detail="staff only")
        return user or {
            "id": 0,
            "email": "local",
            "display_name": "Local",
            "role": "admin",
            "is_active": True,
            "created_at": "",
        }
    if not user:
        raise HTTPException(status_code=401, detail="login required")
    if user["role"] not in STAFF_ROLES:
        raise HTTPException(status_code=403, detail="staff only")
    return user


def require_roles(*roles: str):
    allowed = frozenset(roles)

    def _dep(
        user: Annotated[dict[str, Any], Depends(require_staff)],
    ) -> dict[str, Any]:
        if user.get("role") == "admin":
            return user
        if user.get("role") not in allowed and "admin" not in allowed:
            # admin already returned; check membership
            pass
        if user.get("role") == "admin" or user.get("role") in allowed:
            return user
        raise HTTPException(status_code=403, detail="insufficient role")

    return _dep


def require_admin_role(
    user: Annotated[dict[str, Any], Depends(require_staff)],
) -> dict[str, Any]:
    if not auth_required():
        return user
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return user


def require_warehouse(
    user: Annotated[dict[str, Any], Depends(require_staff)],
) -> dict[str, Any]:
    if not auth_required():
        return user
    if user.get("role") not in ("admin", "warehouse"):
        raise HTTPException(status_code=403, detail="warehouse role required")
    return user


def require_finance(
    user: Annotated[dict[str, Any], Depends(require_staff)],
) -> dict[str, Any]:
    if not auth_required():
        return user
    if user.get("role") not in ("admin", "finance"):
        raise HTTPException(status_code=403, detail="finance role required")
    return user


def bootstrap_admin_if_needed() -> None:
    settings = get_settings()
    email = (settings.bootstrap_admin_email or "").strip().lower()
    password = settings.bootstrap_admin_password or ""
    if not email or not password:
        return
    if user_count() > 0:
        return
    create_user(
        email=email,
        password=password,
        role="admin",
        display_name="Admin",
    )


def purge_expired_sessions() -> int:
    now = _now_iso()
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM sessions WHERE expires_at < ?", (now,)
        )
        return cur.rowcount or 0
