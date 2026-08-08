from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache
def load_name_glossary(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    pairs = [(str(jp), str(zh)) for jp, zh in data.items()]
    pairs.sort(key=lambda item: len(item[0]), reverse=True)
    return pairs


def apply_glossary(name: str, glossary: list[tuple[str, str]]) -> str:
    result = name
    for jp, zh in glossary:
        result = result.replace(jp, zh)
    return result


def resolve_display_name_zh(product_name: str, *, glossary_path: Path) -> str | None:
    """按本地术语表替换；有改动则返回展示名，否则返回 None。"""
    glossed = apply_glossary(product_name, load_name_glossary(glossary_path))
    if glossed != product_name:
        return glossed
    return None


def enrich_product_display_names(products: list[dict], glossary_path: Path) -> None:
    for product in products:
        product["display_name_zh"] = resolve_display_name_zh(
            product["product_name"],
            glossary_path=glossary_path,
        )
