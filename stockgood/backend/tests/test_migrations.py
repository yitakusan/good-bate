from __future__ import annotations

import sqlite3
import unittest

from app.database import _shipments_tracking_has_unique, get_conn, init_db
from app.schema_migrations import MIGRATION_NAMES
from harness import IsolatedDbTestCase


class SchemaMigrationTests(IsolatedDbTestCase):
    def test_fresh_db_records_all_migrations(self) -> None:
        with get_conn() as conn:
            names = [
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM schema_migrations ORDER BY id"
                ).fetchall()
            ]
        self.assertEqual(names, list(MIGRATION_NAMES))

    def test_second_init_does_not_duplicate(self) -> None:
        init_db()
        with get_conn() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM schema_migrations"
            ).fetchone()["c"]
            cols = {
                r["name"] for r in conn.execute("PRAGMA table_info(shipments)")
            }
            batch_cols = {
                r["name"]
                for r in conn.execute("PRAGMA table_info(outbound_batches)")
            }
            item_cols = {
                r["name"] for r in conn.execute("PRAGMA table_info(items)")
            }
        self.assertEqual(count, len(MIGRATION_NAMES))
        self.assertIn("net_weight", cols)
        self.assertIn("gross_weight", cols)
        self.assertIn("invoice_ship_date", batch_cols)
        self.assertIn("product_kind", item_cols)
        with get_conn() as conn:
            self.assertFalse(_shipments_tracking_has_unique(conn))


class DropTrackingUniqueTests(IsolatedDbTestCase):
    auto_init_db = False

    def test_rebuild_keeps_shipment_items(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            """
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_ref TEXT NOT NULL DEFAULT '',
                shop TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'ordered',
                ordered_at TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                name TEXT NOT NULL,
                shop TEXT NOT NULL DEFAULT '',
                order_ref TEXT NOT NULL DEFAULT '',
                qty INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'ordered',
                ordered_at TEXT NOT NULL,
                barcode TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (order_id) REFERENCES orders(id)
            );
            CREATE TABLE outbound_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE shipments (
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
                note TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL,
                FOREIGN KEY (batch_id) REFERENCES outbound_batches(id) ON DELETE CASCADE
            );
            CREATE TABLE shipment_items (
                shipment_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                qty INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (shipment_id, item_id),
                FOREIGN KEY (shipment_id) REFERENCES shipments(id) ON DELETE CASCADE,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            );
            """
        )
        conn.execute(
            "INSERT INTO orders (order_ref, ordered_at) VALUES ('MIG-1', '2026-01-01T00:00:00+00:00')"
        )
        conn.execute(
            """
            INSERT INTO items (order_id, name, qty, ordered_at)
            VALUES (1, 'legacy item', 1, '2026-01-01T00:00:00+00:00')
            """
        )
        conn.execute(
            """
            INSERT INTO shipments (tracking_no, shipped_at, order_id)
            VALUES ('MIG-TRK', '2026-01-02T00:00:00+00:00', 1)
            """
        )
        conn.execute(
            "INSERT INTO shipment_items (shipment_id, item_id, qty) VALUES (1, 1, 1)"
        )
        conn.commit()
        conn.close()

        init_db()

        with get_conn() as conn:
            self.assertFalse(_shipments_tracking_has_unique(conn))
            ship_count = conn.execute(
                "SELECT COUNT(*) AS c FROM shipments"
            ).fetchone()["c"]
            link_count = conn.execute(
                "SELECT COUNT(*) AS c FROM shipment_items"
            ).fetchone()["c"]
            names = [
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM schema_migrations ORDER BY id"
                ).fetchall()
            ]
        self.assertEqual(ship_count, 1)
        self.assertEqual(link_count, 1)
        self.assertEqual(names, list(MIGRATION_NAMES))


if __name__ == "__main__":
    unittest.main()
