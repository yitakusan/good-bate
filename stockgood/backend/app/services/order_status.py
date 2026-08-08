from __future__ import annotations

from typing import Any

STATUS_RANK = {
    "ordered": 0,
    "inbound_shipped": 1,
    "in_stock": 2,
    "outbound_shipped": 3,
    "delivered": 4,
}


def sync_order_status(conn, order_id: int) -> str:
    """Set order.status from the slowest non-cancelled line. Returns new status."""
    rows = conn.execute(
        "SELECT status FROM items WHERE order_id = ?",
        (order_id,),
    ).fetchall()
    if not rows:
        conn.execute(
            "UPDATE orders SET status = 'cancelled' WHERE id = ?",
            (order_id,),
        )
        return "cancelled"

    active = [r["status"] for r in rows if r["status"] != "cancelled"]
    if not active:
        conn.execute(
            "UPDATE orders SET status = 'cancelled' WHERE id = ?",
            (order_id,),
        )
        return "cancelled"

    slowest = min(active, key=lambda s: STATUS_RANK.get(s, 0))
    conn.execute(
        "UPDATE orders SET status = ? WHERE id = ?",
        (slowest, order_id),
    )
    return slowest


def sync_orders_for_items(conn, item_ids: list[int]) -> None:
    if not item_ids:
        return
    placeholders = ",".join("?" * len(item_ids))
    rows = conn.execute(
        f"SELECT DISTINCT order_id FROM items WHERE id IN ({placeholders})",
        item_ids,
    ).fetchall()
    for row in rows:
        if row["order_id"] is not None:
            sync_order_status(conn, int(row["order_id"]))


def order_ids_for_items(conn, item_ids: list[int]) -> list[int]:
    if not item_ids:
        return []
    placeholders = ",".join("?" * len(item_ids))
    rows = conn.execute(
        f"SELECT DISTINCT order_id FROM items WHERE id IN ({placeholders})",
        item_ids,
    ).fetchall()
    return [int(r["order_id"]) for r in rows if r["order_id"] is not None]


def group_items_by_order(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Secondary classification: [{order_id, order_ref, items: [...]}]."""
    groups: dict[int | str, dict[str, Any]] = {}
    order: list[int | str] = []
    for item in items:
        oid = item.get("order_id")
        key: int | str = int(oid) if oid is not None else f"line-{item.get('id')}"
        if key not in groups:
            groups[key] = {
                "order_id": oid,
                "order_ref": item.get("order_ref") or "",
                "items": [],
            }
            order.append(key)
        groups[key]["items"].append(item)
    return [groups[k] for k in order]
