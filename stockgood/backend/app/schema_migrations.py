from __future__ import annotations

# ============================================================
# SHARED MODULE
#
# [用途] 可记录、可跳过的幂等 schema 迁移（非 Alembic）
# [使用功能] 全部写路径（init_db）
# [代码索引] docs/CODE_INDEX.md#shared-modules
# ============================================================
import sqlite3
from datetime import datetime, timezone
from typing import Callable

MigrationFn = Callable[[sqlite3.Connection], None]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL
        )
        """
    )


def _applied_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM schema_migrations").fetchall()
    return {r["name"] for r in rows}


def migrate_ensure_legacy_columns(conn: sqlite3.Connection) -> None:
    from app.database import _ensure_column

    _ensure_column(conn, "action_logs", "actor_user_id", "INTEGER")
    _ensure_column(conn, "order_requests", "user_id", "INTEGER")
    _ensure_column(conn, "order_requests", "account_order_no", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "order_requests", "deposit_rate", "REAL")
    _ensure_column(conn, "order_requests", "deposit_amount", "REAL")
    _ensure_column(conn, "order_requests", "deposit_paid_at", "TEXT")
    _ensure_column(conn, "order_requests", "payment_ref", "TEXT NOT NULL DEFAULT ''")
    conn.execute(
        """
        UPDATE order_requests
        SET account_order_no = request_code
        WHERE IFNULL(TRIM(account_order_no), '') = ''
          AND request_code GLOB 'SG[0-9]*[0-9]-*'
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_order_requests_user ON order_requests(user_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_order_requests_account_no ON order_requests(account_order_no)"
    )
    _ensure_column(conn, "items", "source_url", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "items", "image_url", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "items", "ip", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "items", "product_kind", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "items", "expected_ship_at", "TEXT")
    _ensure_column(conn, "items", "expected_ship_period", "TEXT")
    _ensure_column(conn, "items", "barcode", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "items", "order_qty", "INTEGER")
    _ensure_column(conn, "items", "order_image_url", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "items", "order_id", "INTEGER")
    _ensure_column(conn, "orders", "shipping_fee", "REAL")
    _ensure_column(conn, "orders", "exchange_rate", "REAL")
    _ensure_column(conn, "stock_boxes", "parent_id", "INTEGER")
    _ensure_column(conn, "outbound_batches", "goods_jpy", "REAL")
    _ensure_column(conn, "outbound_batches", "order_shipping_jpy", "REAL")
    _ensure_column(conn, "outbound_batches", "goods_receivable_cny", "REAL")
    _ensure_column(conn, "outbound_batches", "freight_exchange_rate", "REAL")
    _ensure_column(conn, "outbound_batches", "freight_unit_price_jpy", "REAL")
    _ensure_column(conn, "outbound_batches", "chargeable_weight", "REAL")
    _ensure_column(conn, "outbound_batches", "freight_cny", "REAL")
    _ensure_column(conn, "outbound_batches", "amount_receivable_cny", "REAL")
    _ensure_column(
        conn, "outbound_batches", "amount_received_cny", "REAL NOT NULL DEFAULT 0"
    )
    _ensure_column(
        conn, "outbound_batches", "payment_status", "TEXT NOT NULL DEFAULT 'unpaid'"
    )
    _ensure_column(
        conn, "outbound_batches", "payment_note", "TEXT NOT NULL DEFAULT ''"
    )
    _ensure_column(conn, "shipments", "direction", "TEXT NOT NULL DEFAULT 'inbound'")
    _ensure_column(conn, "shipments", "carrier", "TEXT NOT NULL DEFAULT 'other'")
    _ensure_column(conn, "shipments", "order_id", "INTEGER")
    _ensure_column(conn, "shipments", "batch_id", "INTEGER")
    _ensure_column(conn, "shipments", "box_no", "INTEGER")
    _ensure_column(conn, "shipments", "note", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "shipments", "net_weight", "REAL")
    _ensure_column(conn, "shipments", "gross_weight", "REAL")
    _ensure_column(conn, "shipments", "length_cm", "REAL")
    _ensure_column(conn, "shipments", "width_cm", "REAL")
    _ensure_column(conn, "shipments", "height_cm", "REAL")
    _ensure_column(conn, "outbound_batches", "invoice_ship_date", "TEXT")


def migrate_drop_shipments_tracking_unique(conn: sqlite3.Connection) -> None:
    from app.database import _drop_shipments_tracking_unique

    _drop_shipments_tracking_unique(conn)


def migrate_items_to_orders(conn: sqlite3.Connection) -> None:
    from app.database import _migrate_items_to_orders, _table_exists

    if _table_exists(conn, "items"):
        _migrate_items_to_orders(conn)


def migrate_indexes_and_status_cleanup(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_order_id ON items(order_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_shipments_batch ON shipments(batch_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_items_expected_ship ON items(expected_ship_at)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_barcode ON items(barcode)")
    conn.execute(
        """
        UPDATE items
        SET expected_ship_period = NULL
        WHERE expected_ship_period IS NOT NULL
          AND expected_ship_period NOT IN ('early', 'mid', 'late')
        """
    )
    conn.execute(
        "UPDATE items SET status = 'inbound_shipped' WHERE status = 'in_transit'"
    )
    conn.execute(
        """
        UPDATE shipments
        SET direction = 'inbound'
        WHERE direction IS NULL OR direction NOT IN ('inbound', 'outbound')
        """
    )
    conn.execute(
        """
        UPDATE shipments
        SET carrier = 'other'
        WHERE carrier IS NULL OR carrier NOT IN ('yamato', 'sagawa', 'other')
        """
    )


def migrate_product_kind_backfill(conn: sqlite3.Connection) -> None:
    from app.product_kind import ProductKindNormalizer
    from app.settings import get_settings

    detector = ProductKindNormalizer(get_settings().product_kind_path)
    empty_rows = conn.execute(
        """
        SELECT id, name FROM items
        WHERE IFNULL(TRIM(product_kind), '') = ''
          AND IFNULL(TRIM(name), '') != ''
        """
    ).fetchall()
    for row in empty_rows:
        kind = detector.detect(row["name"] or "")
        if kind:
            conn.execute(
                "UPDATE items SET product_kind = ? WHERE id = ?",
                (kind, row["id"]),
            )
    mislabeled = conn.execute(
        """
        SELECT id, name FROM items
        WHERE product_kind = '挂件'
          AND IFNULL(TRIM(name), '') != ''
        """
    ).fetchall()
    for row in mislabeled:
        kind = detector.detect(row["name"] or "")
        if kind == "玩偶":
            conn.execute(
                "UPDATE items SET product_kind = ? WHERE id = ?",
                (kind, row["id"]),
            )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_items_product_kind ON items(product_kind)"
    )


MIGRATIONS: list[tuple[str, MigrationFn]] = [
    ("0001_ensure_legacy_columns", migrate_ensure_legacy_columns),
    ("0002_drop_shipments_tracking_unique", migrate_drop_shipments_tracking_unique),
    ("0003_migrate_items_to_orders", migrate_items_to_orders),
    ("0004_indexes_and_status_cleanup", migrate_indexes_and_status_cleanup),
    ("0005_product_kind_backfill", migrate_product_kind_backfill),
]

MIGRATION_NAMES: tuple[str, ...] = tuple(name for name, _ in MIGRATIONS)


def apply_schema_migrations(conn: sqlite3.Connection) -> list[str]:
    """Run pending named migrations. Each step is idempotent; skip if recorded."""
    _ensure_migrations_table(conn)
    done = _applied_names(conn)
    applied: list[str] = []
    for name, fn in MIGRATIONS:
        if name in done:
            continue
        fn(conn)
        conn.execute(
            "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
            (name, _now()),
        )
        applied.append(name)
    return applied
