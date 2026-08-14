from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from app.auth_context import get_actor_user_id
from app.database import get_conn
from app.services.order_status import sync_order_status, sync_orders_for_items

# ============================================================
# FEATURE: ACTION_LOG
#
# [用途] 写操作记录与撤回
# [接口] /api/action-logs*
# [数据库] action_logs
# [代码索引] docs/CODE_INDEX.md#feature-action_log
# ============================================================


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def record(
    conn,
    action_type: str,
    summary: str,
    payload: dict[str, Any],
    actor_user_id: Optional[int] = None,
) -> dict[str, Any]:
    actor = actor_user_id if actor_user_id is not None else get_actor_user_id()
    cur = conn.execute(
        """
        INSERT INTO action_logs (action_type, summary, payload_json, created_at, actor_user_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (action_type, summary, json.dumps(payload, ensure_ascii=False), _now(), actor),
    )
    row = conn.execute(
        "SELECT * FROM action_logs WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return _row_out(row)


def list_logs(limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 200))
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM action_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_out(r) for r in rows]


def get_latest_undoable() -> Optional[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM action_logs
            WHERE undone_at IS NULL
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        return _row_out(row) if row else None


def undo(log_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM action_logs WHERE id = ?", (log_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="action log not found")
        if row["undone_at"]:
            raise HTTPException(status_code=400, detail="already undone")

        latest = conn.execute(
            """
            SELECT id FROM action_logs
            WHERE undone_at IS NULL
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        if not latest or latest["id"] != log_id:
            raise HTTPException(
                status_code=400,
                detail="only the latest undoable action can be undone",
            )

        payload = json.loads(row["payload_json"])
        action_type = row["action_type"]
        if action_type == "create_shipment":
            _undo_create_shipment(conn, payload)
        elif action_type == "confirm_shipment":
            _undo_confirm_shipment(conn, payload)
        elif action_type == "create_outbound_batch":
            _undo_create_outbound_batch(conn, payload)
        elif action_type == "cancel_item":
            _undo_cancel_item(conn, payload)
        elif action_type == "cancel_order":
            _undo_cancel_order(conn, payload)
        elif action_type in ("create_item", "create_items_batch"):
            _undo_create_items(conn, payload)
        elif action_type == "create_order":
            _undo_create_order(conn, payload)
        elif action_type == "create_order_batch":
            _undo_create_order_batch(conn, payload)
        elif action_type == "add_lines":
            _undo_add_lines(conn, payload)
        else:
            raise HTTPException(
                status_code=400, detail=f"unsupported action type: {action_type}"
            )

        conn.execute(
            "UPDATE action_logs SET undone_at = ? WHERE id = ?",
            (_now(), log_id),
        )
        updated = conn.execute(
            "SELECT * FROM action_logs WHERE id = ?", (log_id,)
        ).fetchone()
        return _row_out(updated)


def _row_out(row) -> dict[str, Any]:
    keys = row.keys()
    return {
        "id": row["id"],
        "action_type": row["action_type"],
        "summary": row["summary"],
        "created_at": row["created_at"],
        "undone_at": row["undone_at"],
        "undoable": row["undone_at"] is None,
        "actor_user_id": row["actor_user_id"] if "actor_user_id" in keys else None,
    }


def _undo_create_shipment(conn, payload: dict[str, Any]) -> None:
    shipment_id = payload["shipment_id"]
    ship = conn.execute(
        "SELECT * FROM shipments WHERE id = ?", (shipment_id,)
    ).fetchone()
    if not ship:
        raise HTTPException(status_code=400, detail="shipment already removed")
    if ship["status"] != "shipped":
        raise HTTPException(
            status_code=400,
            detail="shipment already confirmed; undo confirm first if needed",
        )

    item_ids = [item["id"] for item in payload["item_restores"]]
    for item in payload["item_restores"]:
        current = conn.execute(
            "SELECT status FROM items WHERE id = ?", (item["id"],)
        ).fetchone()
        if not current:
            raise HTTPException(status_code=400, detail=f"item {item['id']} missing")
        expected = (
            "inbound_shipped"
            if payload.get("direction") == "inbound"
            else "outbound_shipped"
        )
        if current["status"] != expected:
            raise HTTPException(
                status_code=400,
                detail=f"item {item['id']} status changed; cannot undo",
            )
        conn.execute(
            "UPDATE items SET status = ? WHERE id = ?",
            (item["status"], item["id"]),
        )

    conn.execute("DELETE FROM shipments WHERE id = ?", (shipment_id,))
    sync_orders_for_items(conn, item_ids)


def _undo_confirm_shipment(conn, payload: dict[str, Any]) -> None:
    shipment_id = payload["shipment_id"]
    ship = conn.execute(
        "SELECT * FROM shipments WHERE id = ?", (shipment_id,)
    ).fetchone()
    if not ship:
        raise HTTPException(status_code=400, detail="shipment missing")
    if ship["status"] != "delivered":
        raise HTTPException(status_code=400, detail="shipment is not confirmed")

    confirmed_status = (
        "in_stock" if payload.get("direction") == "inbound" else "delivered"
    )
    item_ids = [item["id"] for item in payload["item_restores"]]
    for item in payload["item_restores"]:
        current = conn.execute(
            "SELECT status FROM items WHERE id = ?", (item["id"],)
        ).fetchone()
        if not current:
            raise HTTPException(status_code=400, detail=f"item {item['id']} missing")
        if current["status"] not in (confirmed_status, "cancelled"):
            raise HTTPException(
                status_code=400,
                detail=f"item {item['id']} status changed; cannot undo",
            )
        if current["status"] == "cancelled":
            continue
        conn.execute(
            "UPDATE items SET status = ?, arrived_at = ? WHERE id = ?",
            (item["status"], item.get("arrived_at"), item["id"]),
        )

    conn.execute(
        """
        UPDATE shipments
        SET status = 'shipped', delivered_at = NULL
        WHERE id = ?
        """,
        (shipment_id,),
    )
    sync_orders_for_items(conn, item_ids)


def _undo_create_outbound_batch(conn, payload: dict[str, Any]) -> None:
    batch_id = payload["batch_id"]
    batch = conn.execute(
        "SELECT id FROM outbound_batches WHERE id = ?", (batch_id,)
    ).fetchone()
    if not batch:
        raise HTTPException(status_code=400, detail="batch already removed")

    ships = conn.execute(
        "SELECT id, status FROM shipments WHERE batch_id = ?",
        (batch_id,),
    ).fetchall()
    if any(s["status"] != "shipped" for s in ships):
        raise HTTPException(
            status_code=400,
            detail="batch already confirmed; cannot undo",
        )

    for item in payload["item_restores"]:
        current = conn.execute(
            "SELECT status FROM items WHERE id = ?", (item["id"],)
        ).fetchone()
        if not current:
            raise HTTPException(status_code=400, detail=f"item {item['id']} missing")
        if current["status"] != "outbound_shipped":
            raise HTTPException(
                status_code=400,
                detail=f"item {item['id']} status changed; cannot undo",
            )
        conn.execute(
            "UPDATE items SET status = ? WHERE id = ?",
            (item["status"], item["id"]),
        )

    conn.execute("DELETE FROM outbound_batches WHERE id = ?", (batch_id,))
    for oid, prev in (payload.get("order_restores") or {}).items():
        conn.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (prev, int(oid)),
        )
    # Prefer re-sync from lines in case restores incomplete
    sync_orders_for_items(conn, [i["id"] for i in payload["item_restores"]])


def _undo_cancel_item(conn, payload: dict[str, Any]) -> None:
    item_id = payload["item_id"]
    current = conn.execute(
        "SELECT status FROM items WHERE id = ?", (item_id,)
    ).fetchone()
    if not current:
        raise HTTPException(status_code=400, detail="item missing")
    if current["status"] != "cancelled":
        raise HTTPException(status_code=400, detail="item is not cancelled")
    conn.execute(
        "UPDATE items SET status = ? WHERE id = ?",
        (payload["prev_status"], item_id),
    )
    if payload.get("order_id") is not None:
        sync_order_status(conn, int(payload["order_id"]))


def _undo_cancel_order(conn, payload: dict[str, Any]) -> None:
    order_id = payload["order_id"]
    for item in payload.get("item_restores") or []:
        conn.execute(
            "UPDATE items SET status = ? WHERE id = ?",
            (item["status"], item["id"]),
        )
    conn.execute(
        "UPDATE orders SET status = ? WHERE id = ?",
        (payload["prev_status"], order_id),
    )


def _undo_create_items(conn, payload: dict[str, Any]) -> None:
    item_ids = payload["item_ids"]
    if not item_ids:
        return
    placeholders = ",".join("?" * len(item_ids))
    rows = conn.execute(
        f"SELECT id, status, order_id FROM items WHERE id IN ({placeholders})",
        item_ids,
    ).fetchall()
    found = {r["id"]: r for r in rows}
    for iid in item_ids:
        if iid not in found:
            raise HTTPException(status_code=400, detail=f"item {iid} already deleted")
        if found[iid]["status"] != "ordered":
            raise HTTPException(
                status_code=400,
                detail=f"item {iid} already progressed; cannot undo create",
            )
    linked = conn.execute(
        f"SELECT item_id FROM shipment_items WHERE item_id IN ({placeholders})",
        item_ids,
    ).fetchall()
    if linked:
        raise HTTPException(
            status_code=400,
            detail="items already linked to shipments; cannot undo create",
        )
    order_ids = {r["order_id"] for r in rows if r["order_id"] is not None}
    conn.execute(
        f"DELETE FROM items WHERE id IN ({placeholders})",
        item_ids,
    )
    for oid in order_ids:
        remaining = conn.execute(
            "SELECT COUNT(*) FROM items WHERE order_id = ?", (oid,)
        ).fetchone()[0]
        if remaining == 0:
            conn.execute("DELETE FROM orders WHERE id = ?", (oid,))


def _undo_create_order(conn, payload: dict[str, Any]) -> None:
    order_id = payload["order_id"]
    order = conn.execute(
        "SELECT id, status FROM orders WHERE id = ?", (order_id,)
    ).fetchone()
    if not order:
        raise HTTPException(status_code=400, detail="order already deleted")
    if order["status"] != "ordered":
        raise HTTPException(
            status_code=400, detail="order already progressed; cannot undo"
        )
    linked = conn.execute(
        """
        SELECT si.item_id FROM shipment_items si
        JOIN items i ON i.id = si.item_id
        WHERE i.order_id = ?
        """,
        (order_id,),
    ).fetchall()
    if linked:
        raise HTTPException(
            status_code=400, detail="order lines already in shipments; cannot undo"
        )
    conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))


def _undo_create_order_batch(conn, payload: dict[str, Any]) -> None:
    for order_id in payload.get("order_ids") or []:
        _undo_create_order(conn, {"order_id": order_id})


def _undo_add_lines(conn, payload: dict[str, Any]) -> None:
    item_ids = payload.get("item_ids") or []
    if not item_ids:
        return
    placeholders = ",".join("?" * len(item_ids))
    rows = conn.execute(
        f"SELECT id, status FROM items WHERE id IN ({placeholders})",
        item_ids,
    ).fetchall()
    found = {r["id"]: r["status"] for r in rows}
    for iid in item_ids:
        if iid not in found:
            raise HTTPException(status_code=400, detail=f"item {iid} missing")
        if found[iid] != "ordered":
            raise HTTPException(
                status_code=400, detail=f"item {iid} already progressed"
            )
    linked = conn.execute(
        f"SELECT item_id FROM shipment_items WHERE item_id IN ({placeholders})",
        item_ids,
    ).fetchall()
    if linked:
        raise HTTPException(status_code=400, detail="lines already in shipments")
    conn.execute(f"DELETE FROM items WHERE id IN ({placeholders})", item_ids)
    if payload.get("order_id") is not None:
        sync_order_status(conn, int(payload["order_id"]))
