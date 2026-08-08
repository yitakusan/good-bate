from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from app.settings import DATA_DIR, get_settings

__all__ = ["DATA_DIR", "DB_PATH", "get_conn", "init_db", "row_to_dict", "get_db_path"]


def get_db_path() -> Path:
    return get_settings().database_path


def _connect() -> sqlite3.Connection:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _migrate_items_to_orders(conn: sqlite3.Connection) -> None:
    """Lift flat items.order_ref groups into orders + items.order_id."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(items)").fetchall()}
    if "order_id" not in cols:
        conn.execute("ALTER TABLE items ADD COLUMN order_id INTEGER")

    orphan = conn.execute(
        "SELECT COUNT(*) FROM items WHERE order_id IS NULL"
    ).fetchone()[0]
    if not orphan:
        return

    # Group by non-empty order_ref; empty ref → one order per item
    refs = conn.execute(
        """
        SELECT DISTINCT order_ref FROM items
        WHERE order_id IS NULL AND TRIM(order_ref) != ''
        ORDER BY order_ref
        """
    ).fetchall()
    for row in refs:
        ref = row["order_ref"]
        sample = conn.execute(
            """
            SELECT shop, order_qty, order_image_url, ordered_at,
                   expected_ship_at, expected_ship_period, note, status
            FROM items
            WHERE order_id IS NULL AND order_ref = ?
            ORDER BY id
            LIMIT 1
            """,
            (ref,),
        ).fetchone()
        # Prefer order-level qty/image from any row that has them
        qty_row = conn.execute(
            """
            SELECT order_qty, order_image_url FROM items
            WHERE order_id IS NULL AND order_ref = ?
              AND (order_qty IS NOT NULL OR IFNULL(order_image_url,'') != '')
            ORDER BY id LIMIT 1
            """,
            (ref,),
        ).fetchone()
        statuses = [
            r["status"]
            for r in conn.execute(
                "SELECT status FROM items WHERE order_id IS NULL AND order_ref = ?",
                (ref,),
            ).fetchall()
        ]
        active = [s for s in statuses if s != "cancelled"]
        rank = {
            "ordered": 0,
            "inbound_shipped": 1,
            "in_stock": 2,
            "outbound_shipped": 3,
            "delivered": 4,
        }
        if not active:
            order_status = "cancelled"
        else:
            order_status = min(active, key=lambda s: rank.get(s, 0))

        cur = conn.execute(
            """
            INSERT INTO orders (
                order_ref, shop, status, ordered_at, order_qty, order_image_url,
                note, expected_ship_at, expected_ship_period
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ref,
                sample["shop"] or "",
                order_status,
                sample["ordered_at"],
                qty_row["order_qty"] if qty_row else sample["order_qty"],
                (qty_row["order_image_url"] if qty_row else sample["order_image_url"])
                or "",
                sample["note"] or "",
                sample["expected_ship_at"],
                sample["expected_ship_period"],
            ),
        )
        order_id = cur.lastrowid
        conn.execute(
            """
            UPDATE items SET order_id = ?
            WHERE order_id IS NULL AND order_ref = ?
            """,
            (order_id, ref),
        )

    # Items with empty order_ref → solo orders
    solos = conn.execute(
        """
        SELECT id, shop, order_qty, order_image_url, ordered_at,
               expected_ship_at, expected_ship_period, note, status, name
        FROM items
        WHERE order_id IS NULL
        ORDER BY id
        """
    ).fetchall()
    for item in solos:
        cur = conn.execute(
            """
            INSERT INTO orders (
                order_ref, shop, status, ordered_at, order_qty, order_image_url,
                note, expected_ship_at, expected_ship_period
            ) VALUES ('', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["shop"] or "",
                item["status"],
                item["ordered_at"],
                item["order_qty"],
                item["order_image_url"] or "",
                item["note"] or "",
                item["expected_ship_at"],
                item["expected_ship_period"],
            ),
        )
        conn.execute(
            "UPDATE items SET order_id = ? WHERE id = ?",
            (cur.lastrowid, item["id"]),
        )


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_ref TEXT NOT NULL DEFAULT '',
                shop TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'ordered',
                ordered_at TEXT NOT NULL,
                order_qty INTEGER,
                shipping_fee REAL,
                order_image_url TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                expected_ship_at TEXT,
                expected_ship_period TEXT
            );

            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                name TEXT NOT NULL,
                shop TEXT NOT NULL DEFAULT '',
                order_ref TEXT NOT NULL DEFAULT '',
                qty INTEGER NOT NULL DEFAULT 1,
                unit_cost REAL,
                status TEXT NOT NULL DEFAULT 'ordered',
                ordered_at TEXT NOT NULL,
                arrived_at TEXT,
                expected_ship_at TEXT,
                expected_ship_period TEXT,
                barcode TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                animegood_product_id INTEGER,
                ip TEXT NOT NULL DEFAULT '',
                image_url TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                order_qty INTEGER,
                order_image_url TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS outbound_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS shipments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                direction TEXT NOT NULL DEFAULT 'inbound',
                carrier TEXT NOT NULL DEFAULT 'other',
                tracking_no TEXT NOT NULL UNIQUE,
                shipped_at TEXT NOT NULL,
                delivered_at TEXT,
                status TEXT NOT NULL DEFAULT 'shipped',
                order_id INTEGER,
                batch_id INTEGER,
                box_no INTEGER,
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL,
                FOREIGN KEY (batch_id) REFERENCES outbound_batches(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS shipment_items (
                shipment_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                qty INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (shipment_id, item_id),
                FOREIGN KEY (shipment_id) REFERENCES shipments(id) ON DELETE CASCADE,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS action_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                undone_at TEXT
            );

            CREATE TABLE IF NOT EXISTS order_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_code TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'submitted',
                name TEXT NOT NULL,
                shop TEXT NOT NULL DEFAULT '',
                unit_cost REAL,
                image_url TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                ip TEXT NOT NULL DEFAULT '',
                barcode TEXT NOT NULL DEFAULT '',
                qty INTEGER NOT NULL DEFAULT 1,
                contact TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                shop_order_ref TEXT NOT NULL DEFAULT '',
                ordered_at TEXT,
                staff_note TEXT NOT NULL DEFAULT '',
                reject_reason TEXT NOT NULL DEFAULT '',
                stock_order_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (stock_order_id) REFERENCES orders(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
            CREATE INDEX IF NOT EXISTS idx_orders_ref ON orders(order_ref);
            CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
            CREATE INDEX IF NOT EXISTS idx_items_shop ON items(shop);
            CREATE INDEX IF NOT EXISTS idx_items_order_ref ON items(order_ref);
            CREATE INDEX IF NOT EXISTS idx_shipments_status ON shipments(status);
            CREATE INDEX IF NOT EXISTS idx_action_logs_created ON action_logs(id DESC);
            CREATE INDEX IF NOT EXISTS idx_order_requests_status ON order_requests(status);
            CREATE INDEX IF NOT EXISTS idx_order_requests_code ON order_requests(request_code);
            """
        )
        _ensure_column(conn, "items", "source_url", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "items", "image_url", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "items", "ip", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "items", "expected_ship_at", "TEXT")
        _ensure_column(conn, "items", "expected_ship_period", "TEXT")
        _ensure_column(conn, "items", "barcode", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "items", "order_qty", "INTEGER")
        _ensure_column(conn, "items", "order_image_url", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "items", "order_id", "INTEGER")
        _ensure_column(conn, "orders", "shipping_fee", "REAL")
        _ensure_column(conn, "shipments", "direction", "TEXT NOT NULL DEFAULT 'inbound'")
        _ensure_column(conn, "shipments", "carrier", "TEXT NOT NULL DEFAULT 'other'")
        _ensure_column(conn, "shipments", "order_id", "INTEGER")
        _ensure_column(conn, "shipments", "batch_id", "INTEGER")
        _ensure_column(conn, "shipments", "box_no", "INTEGER")

        if _table_exists(conn, "items"):
            _migrate_items_to_orders(conn)

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_items_order_id ON items(order_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_shipments_batch ON shipments(batch_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_items_expected_ship ON items(expected_ship_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_items_barcode ON items(barcode)"
        )
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


def row_to_dict(row: sqlite3.Row | None) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    return dict(row)


DB_PATH = DATA_DIR / "stockgood.sqlite"
