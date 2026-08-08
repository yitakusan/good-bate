from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.event_expiry import today_jst


SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    search_text TEXT NOT NULL DEFAULT '',
    series TEXT NOT NULL DEFAULT '',
    ip TEXT NOT NULL DEFAULT '未分类',
    shop TEXT NOT NULL,
    source_url TEXT NOT NULL,
    price INTEGER,
    stock_status TEXT NOT NULL DEFAULT '未知',
    release_date TEXT,
    preorder_date TEXT,
    image_url TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    source_platform TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    dedupe_key TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_products_first_seen ON products(first_seen DESC);
CREATE INDEX IF NOT EXISTS idx_products_ip ON products(ip);
CREATE INDEX IF NOT EXISTS idx_products_shop ON products(shop);
CREATE INDEX IF NOT EXISTS idx_products_series ON products(series);
CREATE INDEX IF NOT EXISTS idx_products_release_date ON products(release_date);

CREATE TABLE IF NOT EXISTS source_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    shop TEXT NOT NULL,
    source_platform TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    product_count INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    ip TEXT NOT NULL DEFAULT '未分类',
    shop TEXT NOT NULL,
    source_url TEXT NOT NULL,
    image_url TEXT,
    published_at TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    source_platform TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    dedupe_key TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_events_first_seen ON events(first_seen DESC);
CREATE INDEX IF NOT EXISTS idx_events_published_at ON events(published_at DESC);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as conn:
        conn.executescript(SCHEMA)
        ensure_product_columns(conn)
        ensure_event_columns(conn)


def ensure_product_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(products)").fetchall()
    }
    if "stock_status" not in existing_columns:
        conn.execute("ALTER TABLE products ADD COLUMN stock_status TEXT NOT NULL DEFAULT '未知'")
    if "search_text" not in existing_columns:
        conn.execute("ALTER TABLE products ADD COLUMN search_text TEXT NOT NULL DEFAULT ''")
    if "favorite_count" not in existing_columns:
        conn.execute("ALTER TABLE products ADD COLUMN favorite_count INTEGER NOT NULL DEFAULT 0")
    if "display_name_zh" not in existing_columns:
        conn.execute("ALTER TABLE products ADD COLUMN display_name_zh TEXT")
    added_series = False
    if "series" not in existing_columns:
        conn.execute("ALTER TABLE products ADD COLUMN series TEXT NOT NULL DEFAULT ''")
        added_series = True
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_products_stock_status ON products(stock_status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_products_favorite_count ON products(favorite_count DESC)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_products_series ON products(series)")
    if added_series:
        backfill_product_series(conn)
    else:
        row = conn.execute(
            """
            SELECT
              SUM(CASE WHEN series = '' OR series IS NULL THEN 1 ELSE 0 END) AS empty_count,
              COUNT(*) AS total
            FROM products
            """
        ).fetchone()
        if row is not None:
            empty_count = int(row["empty_count"] if isinstance(row, sqlite3.Row) else row[0] or 0)
            total = int(row["total"] if isinstance(row, sqlite3.Row) else row[1] or 0)
            if total > 0 and empty_count == total:
                backfill_product_series(conn)


def backfill_product_series(conn: sqlite3.Connection) -> int:
    from app.series_extractor import extract_series

    rows = conn.execute("SELECT id, product_name FROM products").fetchall()
    for row in rows:
        series = extract_series(row["product_name"]) or ""
        conn.execute("UPDATE products SET series = ? WHERE id = ?", (series, row["id"]))
    return len(rows)


def ensure_event_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()
    }
    if "ends_at" not in existing_columns:
        conn.execute("ALTER TABLE events ADD COLUMN ends_at TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ends_at ON events(ends_at)")


def deactivate_expired_events(conn: sqlite3.Connection) -> int:
    today = today_jst().isoformat()
    result = conn.execute(
        """
        UPDATE events
        SET is_active = 0
        WHERE is_active = 1
          AND ends_at IS NOT NULL
          AND substr(ends_at, 1, 10) < :today
        """,
        {"today": today},
    )
    return result.rowcount


@contextmanager
def connect(database_path: Path) -> Iterator[sqlite3.Connection]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    try:
        ensure_product_columns(conn)
        ensure_event_columns(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_product(conn: sqlite3.Connection, product: dict[str, Any]) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO products (
            product_name, display_name_zh, normalized_name, search_text, series, ip, shop, source_url, price,
            stock_status, release_date, preorder_date, image_url, first_seen, last_seen,
            source_platform, dedupe_key
        )
        VALUES (
            :product_name, :display_name_zh, :normalized_name, :search_text, :series, :ip, :shop, :source_url, :price,
            :stock_status, :release_date, :preorder_date, :image_url, :first_seen, :last_seen,
            :source_platform, :dedupe_key
        )
        ON CONFLICT(dedupe_key) DO UPDATE SET
            product_name = excluded.product_name,
            display_name_zh = COALESCE(excluded.display_name_zh, products.display_name_zh),
            normalized_name = excluded.normalized_name,
            search_text = excluded.search_text,
            series = excluded.series,
            ip = excluded.ip,
            shop = excluded.shop,
            price = excluded.price,
            stock_status = excluded.stock_status,
            release_date = excluded.release_date,
            preorder_date = excluded.preorder_date,
            image_url = excluded.image_url,
            last_seen = excluded.last_seen,
            source_platform = excluded.source_platform,
            is_active = 1
        """,
        {
            **product,
            "series": product.get("series") or "",
            "first_seen": product.get("first_seen") or now,
            "last_seen": now,
        },
    )


def insert_product_if_new(conn: sqlite3.Connection, product: dict[str, Any]) -> bool:
    """增量模式：已存在相同 dedupe_key 则跳过，不更新价格/库存。"""
    existing = conn.execute(
        "SELECT 1 FROM products WHERE dedupe_key = ?",
        (product["dedupe_key"],),
    ).fetchone()
    if existing:
        return False
    upsert_product(conn, product)
    return True


def record_source_run(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    shop: str,
    source_platform: str,
    status: str,
    message: str | None,
    product_count: int,
    started_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO source_runs (
            source_id, shop, source_platform, status, message,
            product_count, started_at, finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_id,
            shop,
            source_platform,
            status,
            message,
            product_count,
            started_at,
            utc_now(),
        ),
    )


def _product_list_filters(
    *,
    q: str | None = None,
    ip: str | None = None,
    shop: str | None = None,
    series: str | None = None,
    release_month: str | None = None,
    stock_status: str | None = None,
    available_only: bool = False,
) -> tuple[list[str], dict[str, Any]]:
    filters = ["is_active = 1"]
    params: dict[str, Any] = {}

    if q:
        filters.append(
            """
            (
                product_name LIKE :q
                OR display_name_zh LIKE :q
                OR normalized_name LIKE :normalized_q
                OR search_text LIKE :q
                OR search_text LIKE :normalized_q
                OR source_url LIKE :q
                OR ip LIKE :q
                OR shop LIKE :q
                OR series LIKE :q
            )
            """
        )
        params["q"] = f"%{q}%"
        params["normalized_q"] = f"%{q.strip().lower()}%"
    if ip:
        filters.append("ip = :ip")
        params["ip"] = ip
    if shop:
        filters.append("shop = :shop")
        params["shop"] = shop
    if series:
        filters.append("series = :series")
        params["series"] = series
    if release_month:
        filters.append("release_date LIKE :release_month")
        params["release_month"] = f"{release_month}%"
    if available_only:
        filters.append("stock_status = '可购买'")
    elif stock_status:
        filters.append("stock_status = :stock_status")
        params["stock_status"] = stock_status

    return filters, params


def count_products(
    conn: sqlite3.Connection,
    *,
    q: str | None = None,
    ip: str | None = None,
    shop: str | None = None,
    series: str | None = None,
    release_month: str | None = None,
    stock_status: str | None = None,
    available_only: bool = False,
) -> int:
    filters, params = _product_list_filters(
        q=q,
        ip=ip,
        shop=shop,
        series=series,
        release_month=release_month,
        stock_status=stock_status,
        available_only=available_only,
    )
    row = conn.execute(
        f"SELECT COUNT(*) AS total FROM products WHERE {' AND '.join(filters)}",
        params,
    ).fetchone()
    return int(row["total"] if row else 0)


def list_products(
    conn: sqlite3.Connection,
    *,
    q: str | None = None,
    ip: str | None = None,
    shop: str | None = None,
    series: str | None = None,
    release_month: str | None = None,
    stock_status: str | None = None,
    available_only: bool = False,
    sort: str = "newest",
    limit: int = 60,
    offset: int = 0,
) -> list[dict[str, Any]]:
    filters, params = _product_list_filters(
        q=q,
        ip=ip,
        shop=shop,
        series=series,
        release_month=release_month,
        stock_status=stock_status,
        available_only=available_only,
    )
    params["limit"] = limit
    params["offset"] = offset

    order_clause = {
        "newest": "first_seen DESC, id DESC",
        "popular": "favorite_count DESC, first_seen DESC, id DESC",
        "price_asc": "CASE WHEN price IS NULL THEN 1 ELSE 0 END, price ASC, id DESC",
        "price_desc": "CASE WHEN price IS NULL THEN 1 ELSE 0 END, price DESC, id DESC",
    }.get(sort, "first_seen DESC, id DESC")

    rows = conn.execute(
        f"""
        SELECT *
        FROM products
        WHERE {' AND '.join(filters)}
        ORDER BY {order_clause}
        LIMIT :limit OFFSET :offset
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def upsert_event(conn: sqlite3.Connection, event: dict[str, Any]) -> None:
    now = utc_now()
    is_active = event.get("is_active", 1)
    conn.execute(
        """
        INSERT INTO events (
            title, normalized_title, summary, ip, shop, source_url, image_url,
            published_at, ends_at, first_seen, last_seen, source_platform, dedupe_key, is_active
        )
        VALUES (
            :title, :normalized_title, :summary, :ip, :shop, :source_url, :image_url,
            :published_at, :ends_at, :first_seen, :last_seen, :source_platform, :dedupe_key, :is_active
        )
        ON CONFLICT(dedupe_key) DO UPDATE SET
            title = excluded.title,
            normalized_title = excluded.normalized_title,
            summary = excluded.summary,
            ip = excluded.ip,
            shop = excluded.shop,
            image_url = excluded.image_url,
            published_at = excluded.published_at,
            ends_at = excluded.ends_at,
            last_seen = excluded.last_seen,
            source_platform = excluded.source_platform,
            is_active = excluded.is_active
        """,
        {
            **event,
            "first_seen": event.get("first_seen") or now,
            "last_seen": now,
            "is_active": is_active,
        },
    )


def insert_event_if_new(conn: sqlite3.Connection, event: dict[str, Any]) -> bool:
    existing = conn.execute(
        "SELECT 1 FROM events WHERE dedupe_key = ?",
        (event["dedupe_key"],),
    ).fetchone()
    if existing:
        return False
    upsert_event(conn, event)
    return True


def list_events(
    conn: sqlite3.Connection,
    *,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    ensure_event_columns(conn)
    deactivate_expired_events(conn)
    today = today_jst().isoformat()
    rows = conn.execute(
        """
        SELECT *
        FROM events
        WHERE is_active = 1
          AND (
            ends_at IS NULL
            OR substr(ends_at, 1, 10) >= :today
          )
        ORDER BY
            COALESCE(published_at, first_seen) DESC,
            id DESC
        LIMIT :limit OFFSET :offset
        """,
        {"limit": limit, "offset": offset, "today": today},
    ).fetchall()
    return [dict(row) for row in rows]


def get_products_by_ids(conn: sqlite3.Connection, product_ids: list[int]) -> list[dict[str, Any]]:
    if not product_ids:
        return []
    unique_ids = list(dict.fromkeys(product_ids))
    placeholders = ",".join("?" for _ in unique_ids)
    rows = conn.execute(
        f"""
        SELECT *
        FROM products
        WHERE is_active = 1
          AND id IN ({placeholders})
        """,
        unique_ids,
    ).fetchall()
    by_id = {int(row["id"]): dict(row) for row in rows}
    return [by_id[pid] for pid in unique_ids if pid in by_id]


def adjust_favorite_count(conn: sqlite3.Connection, product_id: int, delta: int) -> int:
    row = conn.execute(
        "SELECT id FROM products WHERE id = ? AND is_active = 1",
        (product_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"未找到商品：{product_id}")

    conn.execute(
        """
        UPDATE products
        SET favorite_count = CASE
            WHEN COALESCE(favorite_count, 0) + ? < 0 THEN 0
            ELSE COALESCE(favorite_count, 0) + ?
        END
        WHERE id = ?
        """,
        (delta, delta, product_id),
    )
    result = conn.execute(
        "SELECT favorite_count FROM products WHERE id = ?",
        (product_id,),
    ).fetchone()
    return int(result["favorite_count"])


def list_filters(conn: sqlite3.Connection) -> dict[str, list[str]]:
    ips = [
        row["ip"]
        for row in conn.execute(
            "SELECT DISTINCT ip FROM products WHERE is_active = 1 ORDER BY ip"
        )
    ]
    shops = [
        row["shop"]
        for row in conn.execute(
            "SELECT DISTINCT shop FROM products WHERE is_active = 1 ORDER BY shop"
        )
    ]
    release_months = [
        row["month"]
        for row in conn.execute(
            """
            SELECT DISTINCT substr(release_date, 1, 7) AS month
            FROM products
            WHERE is_active = 1 AND release_date IS NOT NULL AND release_date != ''
            ORDER BY month DESC
            """
        )
    ]
    series = [
        row["series"]
        for row in conn.execute(
            """
            SELECT DISTINCT series
            FROM products
            WHERE is_active = 1 AND series IS NOT NULL AND series != ''
            ORDER BY series
            """
        )
    ]
    return {
        "ips": ips,
        "shops": shops,
        "release_months": release_months,
        "series": series,
    }


def latest_runs(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM source_runs
        ORDER BY finished_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def latest_runs_by_source(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT sr.*
        FROM source_runs sr
        INNER JOIN (
            SELECT source_id, MAX(finished_at) AS latest_finished_at
            FROM source_runs
            GROUP BY source_id
        ) latest
            ON sr.source_id = latest.source_id
           AND sr.finished_at = latest.latest_finished_at
        """
    ).fetchall()
    return {row["source_id"]: dict(row) for row in rows}


def count_products_for_source(
    conn: sqlite3.Connection,
    shop: str,
    source_platform: str,
    base_url: str,
) -> int:
    normalized_base = base_url.rstrip("/")
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM products
        WHERE is_active = 1
          AND shop = ?
          AND source_platform = ?
          AND source_url LIKE ?
        """,
        (shop, source_platform, f"{normalized_base}%"),
    ).fetchone()
    return int(row["count"])


def deactivate_events_matching_keywords(
    conn: sqlite3.Connection,
    *,
    shop: str,
    exclude_keywords: list[str],
) -> int:
    """Hide already-stored announcements that match noise keywords (e.g. shipping delays)."""
    keywords = [kw for kw in exclude_keywords if kw and kw.strip()]
    if not keywords:
        return 0

    rows = conn.execute(
        """
        SELECT id, title, summary
        FROM events
        WHERE shop = ?
          AND is_active = 1
        """,
        (shop,),
    ).fetchall()

    deactivated = 0
    for row in rows:
        haystack = f"{row['title']}\n{row['summary'] or ''}".casefold()
        if any(kw.casefold() in haystack for kw in keywords):
            conn.execute("UPDATE events SET is_active = 0 WHERE id = ?", (row["id"],))
            deactivated += 1
    return deactivated


def clear_scraped_data(conn: sqlite3.Connection) -> dict[str, int]:
    product_count = conn.execute("SELECT COUNT(*) AS count FROM products").fetchone()["count"]
    run_count = conn.execute("SELECT COUNT(*) AS count FROM source_runs").fetchone()["count"]

    conn.execute("DELETE FROM products")
    conn.execute("DELETE FROM source_runs")
    conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('products', 'source_runs')")

    return {"deleted_products": product_count, "deleted_runs": run_count}
