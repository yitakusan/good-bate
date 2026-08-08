from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, HttpUrl


class EventSourceConfig(BaseModel):
    id: str
    shop: str
    source_platform: Literal["html-news"]
    base_url: HttpUrl
    list_path: str
    url_prefix: str
    enabled: bool = True
    priority: int = 3
    notes: str | None = None
    # 标题/摘要需至少命中一个；空列表表示不过滤
    include_keywords: list[str] = []
    # 命中任一则丢弃
    exclude_keywords: list[str] = []
    title_min_length: int = 8


def load_event_sources(path: Path) -> list[EventSourceConfig]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [EventSourceConfig.model_validate(item) for item in raw]
