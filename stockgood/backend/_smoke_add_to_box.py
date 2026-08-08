# -*- coding: utf-8 -*-
"""Shadow-DB smoke: add a free order into an existing stock box."""
from __future__ import annotations

import os
import sys

os.environ["STOCKGOOD_DB_MODE"] = "shadow"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import HTTPException

from app.database import get_conn, get_db_path, init_db
from app.models import LineCreate, OrderCreate
from app.services import orders as orders_svc
from app.services import stock_boxes as boxes_svc


def _mark_in_stock(order_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE items SET status = 'in_stock' WHERE order_id = ?",
            (order_id,),
        )
        conn.execute(
            "UPDATE orders SET status = 'in_stock' WHERE id = ?",
            (order_id,),
        )


def main() -> None:
    print("DB:", get_db_path())
    assert "shadow" in str(get_db_path()), "must use shadow DB"
    init_db()

    with get_conn() as conn:
        refs = conn.execute(
            "SELECT id FROM orders WHERE order_ref LIKE 'ADD-BOX-SMOKE%'"
        ).fetchall()
        for row in refs:
            oid = row["id"]
            conn.execute(
                "DELETE FROM stock_box_orders WHERE order_id = ?", (oid,)
            )
            conn.execute("DELETE FROM orders WHERE id = ?", (oid,))
        conn.execute(
            "DELETE FROM stock_boxes WHERE note LIKE 'ADD-BOX-SMOKE%'"
        )

    orders = []
    for i, name in enumerate(("Item A", "Item B", "Item C", "Item D"), start=1):
        order = orders_svc.create_order(
            OrderCreate(
                order_ref=f"ADD-BOX-SMOKE-{i}",
                shop="add-box",
                lines=[LineCreate(name=name, qty=1, barcode=f"AB{i}")],
            )
        )
        _mark_in_stock(order["id"])
        orders.append(order)

    o1, o2, o3, o4 = orders
    box = boxes_svc.combine_orders(
        order_ids=[o1["id"], o2["id"]],
        note="ADD-BOX-SMOKE",
    )
    print("combined box", box["id"], "orders", box["order_count"])
    assert box["order_count"] == 2

    added = boxes_svc.add_orders(box["id"], [o3["id"]])
    print("after add", added["order_count"], "order_ids", added.get("order_ids"))
    assert added["order_count"] == 3
    assert o3["id"] in added["order_ids"]

    other = boxes_svc.combine_orders(
        order_ids=[o4["id"]], note="ADD-BOX-SMOKE-B"
    )
    try:
        boxes_svc.add_orders(box["id"], [o4["id"]])
        raise AssertionError("expected reject when order already in another box")
    except HTTPException as exc:
        print("reject ok:", exc.detail)

    print("other box", other["id"], "OK")


if __name__ == "__main__":
    main()
