from __future__ import annotations

import unittest

from fastapi import HTTPException

from app.database import get_conn
from app.models import LineCreate, OrderCreate
from app.services import action_log as action_log_svc
from app.services import orders as orders_svc
from app.services import outbound_batches as outbound_svc
from app.services import shipments as shipments_svc
from app.services import stock_boxes as boxes_svc
from factories import BOX_PACKING, make_packed_outbound_batch, make_priced_in_stock_order
from harness import IsolatedDbTestCase


def _item_status(item_id: int) -> str:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status FROM items WHERE id = ?", (item_id,)
        ).fetchone()
        assert row is not None
        return str(row["status"])


class OrderLifecycleTests(IsolatedDbTestCase):
    def test_inbound_stock_box_outbound_lock_and_undo(self) -> None:
        order = orders_svc.create_order(
            OrderCreate(
                order_ref="FLOW-001",
                shop="test-shop",
                shipping_fee=500,
                exchange_rate=0.05,
                lines=[
                    LineCreate(
                        name="Flow Item A", qty=2, unit_cost=1000, barcode="111"
                    ),
                    LineCreate(
                        name="Flow Item B", qty=1, unit_cost=2000, barcode="222"
                    ),
                ],
            )
        )
        item_ids = [line["id"] for line in order["lines"]]
        self.assertEqual(orders_svc.get_order(order["id"])["status"], "ordered")

        inbound = shipments_svc.create_inbound_for_order(
            order["id"],
            tracking_no="FLOW-IN-001",
            carrier="yamato",
            item_ids=item_ids,
        )
        self.assertEqual(
            orders_svc.get_order(order["id"])["status"], "inbound_shipped"
        )
        for iid in item_ids:
            self.assertEqual(_item_status(iid), "inbound_shipped")

        shipments_svc.confirm_shipment(inbound["id"])
        self.assertEqual(orders_svc.get_order(order["id"])["status"], "in_stock")
        for iid in item_ids:
            self.assertEqual(_item_status(iid), "in_stock")

        box = boxes_svc.combine_orders(
            order_ids=[order["id"]], note="FLOW-BOX"
        )
        self.assertEqual(box["order_count"], 1)
        self.assertEqual(orders_svc.get_order(order["id"])["status"], "in_stock")
        for iid in item_ids:
            self.assertEqual(_item_status(iid), "in_stock")

        batch = outbound_svc.create_batch(
            boxes=[
                {
                    "box_no": 1,
                    "carrier": "yamato",
                    "tracking_no": "FLOW-OUT-001",
                    "item_ids": item_ids,
                }
            ],
            note="FLOW batch",
            freight_exchange_rate=0.048,
            freight_unit_price_jpy=1000,
            chargeable_weight=2.5,
        )
        self.assertAlmostEqual(batch["goods_receivable_cny"], 225.0)
        self.assertEqual(
            orders_svc.get_order(order["id"])["status"], "outbound_shipped"
        )

        latest = action_log_svc.get_latest_undoable()
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest["action_type"], "create_outbound_batch")
        action_log_svc.undo(latest["id"])
        self.assertEqual(orders_svc.get_order(order["id"])["status"], "in_stock")
        for iid in item_ids:
            self.assertEqual(_item_status(iid), "in_stock")
        with get_conn() as conn:
            leftover = conn.execute(
                "SELECT COUNT(*) AS c FROM outbound_batches WHERE id = ?",
                (batch["id"],),
            ).fetchone()["c"]
        self.assertEqual(leftover, 0)

    def test_undo_inbound_confirm_restores_inbound_shipped(self) -> None:
        order = orders_svc.create_order(
            OrderCreate(
                order_ref="IN-UNDO-001",
                shop="test-shop",
                lines=[LineCreate(name="Undo Item", qty=1, barcode="U1")],
            )
        )
        item_id = order["lines"][0]["id"]
        inbound = shipments_svc.create_inbound_for_order(
            order["id"],
            tracking_no="IN-UNDO-TRK",
            carrier="yamato",
            item_ids=[item_id],
        )
        shipments_svc.confirm_shipment(inbound["id"])
        self.assertEqual(orders_svc.get_order(order["id"])["status"], "in_stock")
        self.assertEqual(_item_status(item_id), "in_stock")

        latest = action_log_svc.get_latest_undoable()
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest["action_type"], "confirm_shipment")
        action_log_svc.undo(latest["id"])

        self.assertEqual(
            orders_svc.get_order(order["id"])["status"], "inbound_shipped"
        )
        self.assertEqual(_item_status(item_id), "inbound_shipped")
        ship = shipments_svc.get_shipment(inbound["id"])
        self.assertEqual(ship["status"], "shipped")
        self.assertIsNone(ship.get("delivered_at"))

    def test_update_batch_recalculates_goods_receivable(self) -> None:
        order = make_priced_in_stock_order(order_ref="EDIT-001")
        item_ids = [line["id"] for line in order["lines"]]
        batch = make_packed_outbound_batch(
            order, tracking_no="EDIT-TRK-001", note="EDIT batch"
        )
        self.assertAlmostEqual(batch["goods_receivable_cny"], 225.0)

        updated = outbound_svc.update_batch(
            batch["id"],
            boxes=[
                {
                    "box_no": 1,
                    "carrier": "yamato",
                    "tracking_no": "EDIT-TRK-001",
                    "items": [
                        {"item_id": item_ids[0], "qty": 1},
                        {"item_id": item_ids[1], "qty": 1},
                    ],
                    **BOX_PACKING,
                }
            ],
        )
        self.assertAlmostEqual(updated["goods_receivable_cny"], 175.0)
        self.assertEqual(_item_status(item_ids[0]), "outbound_shipped")
        with get_conn() as conn:
            qty = conn.execute(
                "SELECT qty FROM items WHERE id = ?", (item_ids[0],)
            ).fetchone()["qty"]
        self.assertEqual(int(qty), 1)

    def test_add_to_box_rejects_order_already_in_another_box(self) -> None:
        orders = []
        for i, name in enumerate(("A", "B", "C", "D"), start=1):
            order = orders_svc.create_order(
                OrderCreate(
                    order_ref=f"BOX-{i}",
                    shop="box-shop",
                    lines=[LineCreate(name=name, qty=1, barcode=f"B{i}")],
                )
            )
            with get_conn() as conn:
                conn.execute(
                    "UPDATE items SET status = 'in_stock' WHERE order_id = ?",
                    (order["id"],),
                )
                conn.execute(
                    "UPDATE orders SET status = 'in_stock' WHERE id = ?",
                    (order["id"],),
                )
            orders.append(order)
        o1, o2, o3, o4 = orders
        box = boxes_svc.combine_orders(
            order_ids=[o1["id"], o2["id"]], note="BOX-A"
        )
        added = boxes_svc.add_orders(box["id"], [o3["id"]])
        self.assertEqual(added["order_count"], 3)
        boxes_svc.combine_orders(order_ids=[o4["id"]], note="BOX-B")
        with self.assertRaises(HTTPException) as ctx:
            boxes_svc.add_orders(box["id"], [o4["id"]])
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
