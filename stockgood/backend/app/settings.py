from __future__ import annotations

# ============================================================
# SHARED MODULE
#
# [用途] 环境变量、库模式（production/shadow）、CORS
# [使用功能] FEATURE: SYSTEM / AUTH
# ============================================================
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_ROOT / "data"

DbMode = Literal["production", "shadow"]


class Settings(BaseSettings):
    app_name: str = "Stockgood"
    ip_alias_path: Path = DATA_DIR / "ip_aliases.json"
    product_kind_path: Path = DATA_DIR / "product_kinds.json"
    # production = 实际库存；shadow = 测试影子库（采购导入等，不参与实库存）
    db_mode: DbMode = "production"
    # Optional legacy staff shared secret (compat). Prefer user sessions.
    admin_token: Optional[str] = None
    # None = auto (require when users exist or admin_token set)
    auth_required: Optional[bool] = None
    session_secret: Optional[str] = None
    cookie_secure: bool = False
    cors_origins: str = "*"
    # First-boot admin (only if users table empty)
    bootstrap_admin_email: Optional[str] = None
    bootstrap_admin_password: Optional[str] = None
    # Serve built SPA from this directory when set (Docker / production)
    static_dir: Optional[Path] = None
    # SMTP notifications (optional)
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_use_tls: bool = True
    notify_enabled: bool = True
    # Deposit rate for customer apply (0.3 = 30%); finance gateway later
    deposit_rate: float = 0.3
    # Env STOCKGOOD_DATABASE_PATH: tests point at a temp sqlite so they never
    # touch production or the shared shadow file. Empty/unset → db_mode path.
    database_path: Optional[Path] = None

    @field_validator("db_mode", mode="before")
    @classmethod
    def normalize_db_mode(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip().lower()
            if text in ("prod", "live", "real"):
                return "production"
            if text in ("test", "shadow", "demo"):
                return "shadow"
            return text
        return value

    @field_validator("admin_token", mode="before")
    @classmethod
    def empty_admin_token_as_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("auth_required", mode="before")
    @classmethod
    def empty_auth_required_as_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip().lower()
            if text in ("", "auto", "none"):
                return None
            if text in ("1", "true", "yes", "on"):
                return True
            if text in ("0", "false", "no", "off"):
                return False
        return value

    @field_validator("database_path", mode="before")
    @classmethod
    def empty_database_path_as_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "session_secret",
        "bootstrap_admin_email",
        "bootstrap_admin_password",
        "smtp_host",
        "smtp_user",
        "smtp_password",
        "smtp_from",
        mode="before",
    )
    @classmethod
    def empty_str_as_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def is_shadow(self) -> bool:
        return self.db_mode == "shadow"

    @property
    def cors_origin_list(self) -> list[str]:
        raw = (self.cors_origins or "*").strip()
        if raw == "*":
            return ["*"]
        return [p.strip() for p in raw.split(",") if p.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="STOCKGOOD_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
