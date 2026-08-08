from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.database import get_conn
from app.services import action_log
from app.services.order_status import group_items_by_order, sync_order_status
from app.services.shipments import _shipment_with_items


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _box_out(conn, shipment_id: int) -> dict[str, Any]:
    ship = _shipment_with_items(conn, shipment_id)
    return {
        "id": ship["id"],
        "batch_id": ship["batch_id"],
        "box_no": ship["box_no"],
        "carrier": ship["carrier"],
        "tracking_no": ship["tracking_no"],
        "tracking_url": ship["tracking_url"],
        "status": ship["status"],
        "shipped_at": ship["shipped_at"],
        "delivered_at": ship["delivered_at"],
        "items": ship["items"],
        "order_groups": ship["order_groups"],
    }


def _batch_out(conn, batch_id: int) -> dict[str, Any]:
    batch = conn.execute(
        "SELECT * FROM outbound_batches WHERE id = ?", (batch_id,)
    ).fetchone()
    if not batch:
        raise HTTPException(status_code=404, detail="outbound batch not found")
    boxes = conn.execute(
        """
        SELECT id FROM shipments
        WHERE batch_id = ? AND direction = 'outbound'
        ORDER BY box_no, id
        """,
        (batch_id,),
    ).fetchall()
    box_outs = [_box_out(conn, b["id"]) for b in boxes]
    return {
        "id": batch["id"],
        "note": batch["note"],
        "created_at": batch["created_at"],
        "boxes": box_outs,
        "box_count": len(box_outs),
        "item_count": sum(len(b["items"]) for b in box_outs),
    }


def list_batches(limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 200))
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id FROM outbound_batches ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_batch_out(conn, r["id"]) for r in rows]


def get_batch(batch_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        return _batch_out(conn, batch_id)


def create_batch(boxes: list[dict[str, Any]], note: str = "") -> dict[str, Any]:
    """
    Outbound batch: multiple boxes, each with independent box_no + tracking.
    A box may contain lines from multiple orders (secondary group by order).
    No partial outbound: if any line of an order is included, all in_stock
    lines of that order must be in this batch (any boxes).
    """
    if not boxes:
        raise HTTPException(status_code=400, detail="boxes required")

    normalized: list[dict[str, Any]] = []
    seen_items: set[int] = set()
    used_box_nos: set[int] = set()
    used_tracking: set[str] = set()

    for i, box in enumerate(boxes, start=1):
        ids = list(box.get("item_ids") or [])
        if not ids:
            raise HTTPException(status_code=400, detail=f"第{i}箱没有明细行")
        unique: list[int] = []
        for iid in ids:
            if iid in seen_items:
                raise HTTPException(
                    status_code=400, detail=f"明细行 #{iid} 被分到多个箱"
                )
            seen_items.add(iid)
            unique.append(iid)

        carrier = (box.get("carrier") or "other").strip().lower()
        if carrier not in ("yamato", "sagawa", "other"):
            raise HTTPException(status_code=400, detail=f"第{i}箱承运商无效")
        tracking_no = (box.get("tracking_no") or "").strip()
        if not tracking_no:
            raise HTTPException(status_code=400, detail=f"第{i}箱需要运单号")
        if tracking_no in used_tracking:
            raise HTTPException(
                status_code=400, detail=f"运单号重复: {tracking_no}"
            )
        used_tracking.add(tracking_no)

        box_no = box.get("box_no")
        if box_no is None:
            box_no = i
        box_no = int(box_no)
        if box_no < 1:
            raise HTTPException(status_code=400, detail=f"第{i}箱箱号无效")
        if box_no in used_box_nos:
            raise HTTPException(status_code=400, detail=f"箱号重复: {box_no}")
        used_box_nos.add(box_no)

        normalized.append(
            {
                "box_no": box_no,
                "carrier": carrier,
                "tracking_no": tracking_no,
                "item_ids": unique,
            }
        )

    with get_conn() as conn:
        for tracking_no in used_tracking:
            exists = conn.execute(
                "SELECT id FROM shipments WHERE tracking_no = ?",
                (tracking_no,),
            ).fetchone()
            if exists:
                raise HTTPException(
                    status_code=409, detail=f"tracking_no already exists: {tracking_no}"
                )

        placeholders = ",".join("?" * len(seen_items))
        rows = conn.execute(
            f"""
            SELECT id, order_id, order_ref, status, qty, name
            FROM items WHERE id IN ({placeholders})
            """,
            list(seen_items),
        ).fetchall()
        by_id = {r["id"]: r for r in rows}
        if len(by_id) != len(seen_items):
            missing = [iid for iid in seen_items if iid not in by_id]
            raise HTTPException(status_code=404, detail=f"items not found: {missing}")

        for iid, row in by_id.items():
            if row["status"] != "in_stock":
                raise HTTPException(
                    status_code=400,
                    detail=f"「{row['name']}」不是在库，不能出库",
                )
            if row["order_id"] is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"明细行 #{iid} 未关联订单",
                )

        already = conn.execute(
            f"""
            SELECT item_id FROM shipment_items
            JOIN shipments s ON s.id = shipment_items.shipment_id
            WHERE item_id IN ({placeholders}) AND s.direction = 'outbound'
            """,
            list(seen_items),
        ).fetchall()
        if already:
            ids = [r["item_id"] for r in already]
            raise HTTPException(
                status_code=400, detail=f"items already in outbound shipment: {ids}"
            )

        # No partial outbound: every in_stock line of touched orders must be included
        order_ids = {int(by_id[iid]["order_id"]) for iid in seen_items}
        for oid in order_ids:
            stock_rows = conn.execute(
                """
                SELECT id FROM items
                WHERE order_id = ? AND status = 'in_stock'
                """,
                (oid,),
            ).fetchall()
            stock_ids = {r["id"] for r in stock_rows}
            missing = stock_ids - seen_items
            if missing:
                ref = conn.execute(
                    "SELECT order_ref FROM orders WHERE id = ?", (oid,)
                ).fetchone()
                label = (ref["order_ref"] if ref else "") or f"#{oid}"
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"订单 {label} 不能部分出库，未装箱的在库明细: "
                        f"{sorted(missing)}"
                    ),
                )

        cur = conn.execute(
            "INSERT INTO outbound_batches (note, created_at) VALUES (?, ?)",
            (note.strip(), _now()),
        )
        batch_id = int(cur.lastrowid)
        shipment_ids: list[int] = []
        item_restores: list[dict[str, Any]] = []
        order_restores = {
            oid: conn.execute(
                "SELECT status FROM orders WHERE id = ?", (oid,)
            ).fetchone()["status"]
            for oid in order_ids
        }

        for box in sorted(normalized, key=lambda b: b["box_no"]):
            scur = conn.execute(
                """
                INSERT INTO shipments (
                    direction, carrier, tracking_no, shipped_at, status,
                    batch_id, box_no
                ) VALUES ('outbound', ?, ?, ?, 'shipped', ?, ?)
                """,
                (
                    box["carrier"],
                    box["tracking_no"],
                    _now(),
                    batch_id,
                    box["box_no"],
                ),
            )
            shipment_id = int(scur.lastrowid)
            shipment_ids.append(shipment_id)
            for iid in box["item_ids"]:
                item_restores.append(
                    {"id": iid, "status": by_id[iid]["status"]}
                )
                conn.execute(
                    """
                    INSERT INTO shipment_items (shipment_id, item_id, qty)
                    VALUES (?, ?, ?)
                    """,
                    (shipment_id, iid, by_id[iid]["qty"]),
                )
                conn.execute(
                    "UPDATE items SET status = 'outbound_shipped' WHERE id = ?",
                    (iid,),
                )

        for oid in order_ids:
            sync_order_status(conn, oid)

        action_log.record(
            conn,
            "create_outbound_batch",
            f"出库批次 #{batch_id}（{len(normalized)} 箱 / {len(seen_items)} 行）",
            {
                "batch_id": batch_id,
                "shipment_ids": shipment_ids,
                "item_restores": item_restores,
                "order_restores": order_restores,
            },
        )
        return _batch_out(conn, batch_id)


def confirm_batch(batch_id: int) -> dict[str, Any]:
    """Confirm all shipped boxes in a batch as delivered (user signed)."""
    with get_conn() as conn:
        batch = conn.execute(
            "SELECT id FROM outbound_batches WHERE id = ?", (batch_id,)
        ).fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="outbound batch not found")
        ships = conn.execute(
            """
            SELECT id FROM shipments
            WHERE batch_id = ? AND direction = 'outbound' AND status = 'shipped'
            ORDER BY box_no
            """,
            (batch_id,),
        ).fetchall()
        for ship in ships:
            # inline confirm to share connection
            shipment_id = ship["id"]
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
            order_ids: set[int] = set()
            for r in item_rows:
                if r["status"] == "cancelled":
                    continue
                conn.execute(
                    "UPDATE items SET status = 'delivered', arrived_at = ? WHERE id = ?",
                    (now, r["id"]),
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

        if ships:
            action_log.record(
                conn,
                "confirm_outbound_batch",
                f"确认出库批次 #{batch_id} 签收（{len(ships)} 箱）",
                {"batch_id": batch_id, "shipment_ids": [s["id"] for s in ships]},
            )
        return _batch_out(conn, batch_id)
