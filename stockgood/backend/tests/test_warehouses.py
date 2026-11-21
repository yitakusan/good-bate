"""Warehouses keep orders and stock boxes apart."""

from __future__ import annotations

from fastapi import HTTPException

from app.models import LineCreate, OrderCreate
from app.services import orders as orders_svc
from app.services import stock_boxes as boxes_svc
from app.services import warehouses as warehouses_svc
from app.warehouse_scope import use_warehouse
from harness import IsolatedDbTestCase


class WarehouseIsolationTests(IsolatedDbTestCase):
    def test_orders_and_box_numbers_stay_inside_one_warehouse(self) -> None:
        default = warehouses_svc.list_warehouses()[0]
        self.assertEqual(default["name"], "默认仓库")
        other = warehouses_svc.create_warehouse("大阪仓")

        with use_warehouse(default["id"]):
            home = orders_svc.create_order(
                OrderCreate(
                    order_ref="HOME-1",
                    shop="shop-a",
                    lines=[LineCreate(name="home item", qty=1, unit_cost=10)],
                )
            )
            self.assertEqual(len(orders_svc.list_orders()), 1)
            self.assertEqual(orders_svc.list_orders()[0]["order_ref"], "HOME-1")

        with use_warehouse(other["id"]):
            self.assertEqual(orders_svc.list_orders(), [])
            with self.assertRaises(HTTPException) as caught:
                orders_svc.get_order(home["id"])
            self.assertEqual(caught.exception.status_code, 404)
            away = orders_svc.create_order(
                OrderCreate(
                    order_ref="AWAY-1",
                    shop="shop-b",
                    lines=[LineCreate(name="away item", qty=2, unit_cost=20)],
                )
            )
            self.assertEqual(
                [row["order_ref"] for row in orders_svc.list_orders()],
                ["AWAY-1"],
            )
            self.assertEqual(away["order_ref"], "AWAY-1")

        with use_warehouse(default["id"]):
            self.assertEqual(
                [row["order_ref"] for row in orders_svc.list_orders()],
                ["HOME-1"],
            )

    def test_each_warehouse_can_use_box_number_one(self) -> None:
        default = warehouses_svc.list_warehouses()[0]
        other = warehouses_svc.create_warehouse("第二仓")

        def _stock_order(ref: str) -> int:
            order = orders_svc.create_order(
                OrderCreate(
                    order_ref=ref,
                    shop="shop",
                    lines=[LineCreate(name=ref, qty=1, unit_cost=1)],
                )
            )
            from app.database import get_conn

            with get_conn() as conn:
                conn.execute(
                    "UPDATE items SET status = 'in_stock' WHERE order_id = ?",
                    (order["id"],),
                )
                conn.execute(
                    "UPDATE orders SET status = 'in_stock' WHERE id = ?",
                    (order["id"],),
                )
            return int(order["id"])

        with use_warehouse(default["id"]):
            first = _stock_order("BOX-A")
            box_a = boxes_svc.create_box([first], note="a", box_no=1)
            self.assertEqual(box_a["box_no"], 1)
        with use_warehouse(other["id"]):
            second = _stock_order("BOX-B")
            box_b = boxes_svc.create_box([second], note="b", box_no=1)
            self.assertEqual(box_b["box_no"], 1)
            self.assertEqual(len(boxes_svc.list_boxes()), 1)
            third = _stock_order("BOX-C")
            with self.assertRaises(HTTPException) as caught:
                boxes_svc.create_box([third], note="dup", box_no=1)
            self.assertEqual(caught.exception.status_code, 409)
        with use_warehouse(default["id"]):
            self.assertEqual(len(boxes_svc.list_boxes()), 1)
            self.assertEqual(boxes_svc.list_boxes()[0]["note"], "a")
