from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "动漫周边资讯聚合"
    database_path: Path = Path("data/animegood.sqlite")
    source_config_path: Path = Path("config/sources.json")
    event_source_config_path: Path = Path("config/event_sources.json")
    ip_alias_path: Path = Path("data/ip_aliases.json")
    name_glossary_path: Path = Path("data/name_glossary.json")
    request_timeout_seconds: float = 20
    scrape_concurrency: int = 3
    # 为空则不鉴权（本机开发）；公网部署务必设置
    admin_token: str | None = None
    # 0 = 关闭定时抓取；例如 6 表示每 6 小时跑一次全量抓取
    scrape_interval_hours: float = 0

    @field_validator("scrape_concurrency")
    @classmethod
    def validate_scrape_concurrency(cls, value: int) -> int:
        if value < 1 or value > 8:
            raise ValueError("scrape_concurrency must be between 1 and 8")
        return value

    @field_validator("scrape_interval_hours")
    @classmethod
    def validate_scrape_interval_hours(cls, value: float) -> float:
        if value < 0:
            raise ValueError("scrape_interval_hours must be >= 0")
        if value > 168:
            raise ValueError("scrape_interval_hours must be <= 168 (7 days)")
        return value

    @field_validator("admin_token", mode="before")
    @classmethod
    def empty_admin_token_as_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ANIMEGOOD_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
