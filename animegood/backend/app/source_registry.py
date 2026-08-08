from __future__ import annotations

from pathlib import Path

from app.database import connect, count_products_for_source, latest_runs_by_source
from app.models import SourceRegistry, SourceRegistryItem
from app.source_config import SourceConfig, load_sources

EASY_DIFFICULTIES = {"极低", "低", "中低"}
DIFFICULTY_ORDER = {"极低": 0, "低": 1, "中低": 2, "中": 3, "中高": 4, "高": 5, "极高": 6}


def _sort_key(source: SourceConfig) -> tuple[int, int, int, str]:
    return (
        0 if source.enabled else 1,
        DIFFICULTY_ORDER.get(source.difficulty, 99),
        source.priority,
        source.shop,
    )


def build_source_registry(database_path: Path, source_config_path: Path) -> SourceRegistry:
    sources = sorted(load_sources(source_config_path), key=_sort_key)
    with connect(database_path) as conn:
        runs_by_source = latest_runs_by_source(conn)
        items: list[SourceRegistryItem] = []

        for source in sources:
            latest_run = runs_by_source.get(source.id)
            items.append(
                SourceRegistryItem(
                    id=source.id,
                    shop=source.shop,
                    base_url=str(source.base_url),
                    source_platform=source.source_platform,
                    enabled=source.enabled,
                    inclusion_status="已收录" if source.enabled else "未收录",
                    difficulty=source.difficulty,
                    priority=source.priority,
                    core_ips=source.core_ips,
                    notes=source.notes,
                    product_count=count_products_for_source(
                        conn,
                        source.shop,
                        source.source_platform,
                        str(source.base_url),
                    ),
                    last_run_status=latest_run["status"] if latest_run else None,
                    last_run_at=latest_run["finished_at"] if latest_run else None,
                    last_run_message=latest_run["message"] if latest_run else None,
                )
            )

    included_count = sum(1 for item in items if item.enabled)
    easy_pending_count = sum(
        1 for item in items if not item.enabled and item.difficulty in EASY_DIFFICULTIES
    )
    return SourceRegistry(
        items=items,
        included_count=included_count,
        excluded_count=len(items) - included_count,
        easy_pending_count=easy_pending_count,
    )
