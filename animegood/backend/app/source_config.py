from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, HttpUrl


class SourceConfig(BaseModel):
    id: str
    shop: str
    source_platform: Literal[
        "shopify",
        "ec-cube",
        "base-stores",
        "ochanoko",
        "color-me",
        "futureshop",
        "large-ec",
    ]
    base_url: HttpUrl
    collections: list[str] = []
    enabled: bool = True
    priority: int = 3
    difficulty: str = "中"
    core_ips: list[str] = []
    notes: str | None = None


def load_sources(path: Path) -> list[SourceConfig]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [SourceConfig.model_validate(item) for item in raw]
