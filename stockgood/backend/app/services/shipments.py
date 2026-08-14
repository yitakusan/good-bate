from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import HTTPException

from app.database import get_conn
from app.services import action_log
from app.services.order_status import group_items_by_order, sync_order_status
from app.tracking_links import tracking_url

# ============================================================
# FEATURE: INBOUND
#
# [用途] 进库运单创建与确认到仓
# [接口] POST /api/orders/{id}/inbound  /api/shipments*
# [数据库] shipments, shipment_items, items.status
# [代码索引] docs/CODE_INDEX.md#feature-inbound
# ============================================================

# SQLite UNIQUE on tracking_no cannot hold multiple empty strings.
_NO_TRACKING_PREFIX = "__none__"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _store_tracking_no(tracking_no: str) -> str:
    value = tracking_no.strip()
    return value if value else f"{_NO_TRACKING_PREFIX}{uuid4().hex}"


def _display_tracking_no(tracking_no: str) -> str:
    if tracking_no.startswith(_NO_TRACKING_PREFIX):
        return ""
    return tracking_no


def _shipment_with_items(conn, shipment_id: int) -> dict[str, Any]:
    ship = conn.execute(
        "SELECT * FROM shipments WHERE id = ?", (shipment_id,)
    ).fetchone()
    if not ship:
        raise HTTPException(status_code=404, detail="shipment not found")
    items = conn.execute(
        """
        SELECT i.id, i.order_id, i.order_ref, i.name, i.shop, si.qty, i.status, i.barcode
        FROM shipment_items si
        JOIN items i ON i.id = si.item_id
        WHERE si.shipment_id = ?
        ORDER BY i.order_ref, i.id
        """,
        (shipment_id,),
    ).fetchall()
    item_dicts = [dict(r) for r in items]
    result = dict(ship)
    result["tracking_no"] = _display_tracking_no(result["tracking_no"] or "")
    result["tracking_url"] = tracking_url(result["carrier"], result["tracking_no"])
    result["items"] = item_dicts
    result["order_groups"] = group_items_by_order(item_dicts)
    return result


def list_shipments(
    status: Optional[str] = None,
    tracking_no: Optional[str] = None,
    direction: Optional[str] = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if tracking_no:
        clauses.append("tracking_no LIKE ?")
        params.append(f"%{tracking_no}%")
    if direction:
        clauses.append("direction = ?")
        params.append(direction)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT id FROM shipments {where} ORDER BY id DESC", params
        ).fetchall()
        return [_shipment_with_items(conn, r["id"]) for r in rows]


def get_shipment(shipment_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        return _shipment_with_items(conn, shipment_id)


# ============================================================
# FEATURE: INBOUND
# [业务逻辑] create_inbound_for_order — 按订单进库
# [接口] POST /api/orders/{id}/inbound
# ============================================================
def create_inbound_for_order(
    order_id: int,
    tracking_no: str,
    carrier: str,
    item_ids: list[int],
) -> dict[str, Any]:
    """Inbound: one package, single order, one or more lines (split by line OK)."""
    tracking_no = (tracking_no or "").strip()
    carrier = carrier.strip().lower()
    if carrier not in ("yamato", "sagawa", "other"):
        raise HTTPException(status_code=400, detail="invalid carrier")
    if not item_ids:
        raise HTTPException(status_code=400, detail="item_ids required")

    seen: set[int] = set()
    unique_ids: list[int] = []
    for iid in item_ids:
        if iid not in seen:
            seen.add(iid)
            unique_ids.append(iid)

    with get_conn() as conn:
        order = conn.execute(
            "SELECT id, order_ref, status FROM orders WHERE id = ?",
            (order_id,),
        ).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="order not found")
        if order["status"] == "cancelled":
            raise HTTPException(status_code=400, detail="order is cancelled")

        if tracking_no:
            existing = conn.execute(
                "SELECT id FROM shipments WHERE tracking_no = ?", (tracking_no,)
            ).fetchone()
            if existing:
                raise HTTPException(status_code=409, detail="tracking_no already exists")

        placeholders = ",".join("?" * len(unique_ids))
        rows = conn.execute(
            f"""
            SELECT id, order_id, status, qty FROM items
            WHERE id IN ({placeholders})
            """,
            unique_ids,
        ).fetchall()
        found = {r["id"]: r for r in rows}
        missing = [iid for iid in unique_ids if iid not in found]
        if missing:
            raise HTTPException(status_code=404, detail=f"items not found: {missing}")

        wrong_order = [
            iid for iid in unique_ids if int(found[iid]["order_id"]) != order_id
        ]
        if wrong_order:
            raise HTTPException(
                status_code=400,
                detail=f"items not in this order: {wrong_order}",
            )

        invalid = [iid for iid in unique_ids if found[iid]["status"] != "ordered"]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"only ordered lines can be inbound-shipped: {invalid}",
            )

        already_linked = conn.execute(
            f"""
            SELECT item_id FROM shipment_items
            JOIN shipments s ON s.id = shipment_items.shipment_id
            WHERE item_id IN ({placeholders}) AND s.direction = 'inbound'
            """,
            unique_ids,
        ).fetchall()
        if already_linked:
            ids = [r["item_id"] for r in already_linked]
            raise HTTPException(
                status_code=400,
                detail=f"items already in an inbound shipment: {ids}",
            )

        stored_tracking = _store_tracking_no(tracking_no)
        cur = conn.execute(
            """
            INSERT INTO shipments (
                direction, carrier, tracking_no, shipped_at, status, order_id
            ) VALUES ('inbound', ?, ?, ?, 'shipped', ?)
            """,
            (carrier, stored_tracking, _now(), order_id),
        )
        shipment_id = cur.lastrowid
        item_restores = [
            {"id": iid, "status": found[iid]["status"]} for iid in unique_ids
        ]
        for iid in unique_ids:
            conn.execute(
                """
                INSERT INTO shipment_items (shipment_id, item_id, qty)
                VALUES (?, ?, ?)
                """,
                (shipment_id, iid, found[iid]["qty"]),
            )
            conn.execute(
                "UPDATE items SET status = 'inbound_shipped' WHERE id = ?",
                (iid,),
            )

        sync_order_status(conn, order_id)
        tracking_label = tracking_no or "无单号"
        action_log.record(
            conn,
            "create_shipment",
            f"登记进库包裹 {tracking_label}（订单 {order['order_ref'] or order_id}，{len(unique_ids)} 行）",
            {
                "shipment_id": shipment_id,
                "direction": "inbound",
                "order_id": order_id,
                "item_restores": item_restores,
            },
        )
        return _shipment_with_items(conn, shipment_id)


def create_shipment(
    tracking_no: str,
    carrier: str,
    item_ids: list[int],
    direction: str = "inbound",
    order_id: Optional[int] = None,
) -> dict[str, Any]:
    if direction == "outbound":
        raise HTTPException(
            status_code=400,
            detail="outbound must use POST /api/outbound-batches",
        )
    if order_id is None:
        # Infer single order from item_ids
        with get_conn() as conn:
            if not item_ids:
                raise HTTPException(status_code=400, detail="item_ids required")
            placeholders = ",".join("?" * len(item_ids))
            rows = conn.execute(
                f"SELECT DISTINCT order_id FROM items WHERE id IN ({placeholders})",
                item_ids,
            ).fetchall()
            oids = [r["order_id"] for r in rows if r["order_id"] is not None]
            if len(set(oids)) != 1:
                raise HTTPException(
                    status_code=400,
                    detail="inbound package must contain lines from exactly one order",
                )
            order_id = int(oids[0])
    return create_inbound_for_order(order_id, tracking_no, carrier, item_ids)


def confirm_shipment(shipment_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        ship = conn.execute(
            "SELECT * FROM shipments WHERE id = ?", (shipment_id,)
        ).fetchone()
        if not ship:
            raise HTTPException(status_code=404, detail="shipment not found")
        if ship["status"] == "delivered":
            return _shipment_with_items(conn, shipment_id)

        now = _now()
        item_rows = conn.execute(
            """
            SELECT i.id, i.order_id, i.status, i.arrived_at
            FROM shipment_items si
            JOIN items i ON i.id = si.item_id
            WHERE si.shipment_id = ?
            """,
            (shipment_id,),
        ).fetchall()
        item_restores = [
            {
                "id": r["id"],
                "status": r["status"],
                "arrived_at": r["arrived_at"],
            }
            for r in item_rows
        ]
        next_status = "in_stock" if ship["direction"] == "inbound" else "delivered"
        order_ids: set[int] = set()
        for r in item_rows:
            if r["status"] == "cancelled":
                continue
            conn.execute(
                """
                UPDATE items
                SET status = ?, arrived_at = ?
                WHERE id = ?
                """,
                (next_status, now, r["id"]),
            )
            if r["order_id"] is not None:
                order_ids.add(int(r["order_id"]))

        conn.execute(
            """
            UPDATE shipments
            SET status = 'delivered', delivered_at = ?
            WHERE id = ?
            """,
            (now, shipment_id),
        )
        for oid in order_ids:
            sync_order_status(conn, oid)

        label = "到仓" if ship["direction"] == "inbound" else "签收"
        tracking_label = _display_tracking_no(ship["tracking_no"] or "") or "无单号"
        action_log.record(
            conn,
            "confirm_shipment",
            f"确认{label} {tracking_label}（{len(item_rows)} 行）",
            {
                "shipment_id": shipment_id,
                "direction": ship["direction"],
                "item_restores": item_restores,
                "order_ids": list(order_ids),
            },
        )
        return _shipment_with_items(conn, shipment_id)
