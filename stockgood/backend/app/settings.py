from __future__ import annotations

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
    # production = 实际库存；shadow = 测试影子库（采购导入等，不参与实库存）
    db_mode: DbMode = "production"
    # Optional staff write protection for order-request APIs (and UI prompt).
    admin_token: Optional[str] = None

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

    @property
    def database_path(self) -> Path:
        if self.db_mode == "shadow":
            return DATA_DIR / "stockgood.shadow.sqlite"
        return DATA_DIR / "stockgood.sqlite"

    @property
    def is_shadow(self) -> bool:
        return self.db_mode == "shadow"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="STOCKGOOD_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
