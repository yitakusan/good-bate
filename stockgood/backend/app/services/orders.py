from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from app.database import get_conn
from app.models import LineCreate, OrderCreate, OrderUpdate
from app.services import action_log
from app.services.order_status import sync_order_status
from app.tracking_links import tracking_url

_EXPECTED_SHIP_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")
_VALID_PERIODS = frozenset({"early", "mid", "late"})


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_expected_ship(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if not _EXPECTED_SHIP_RE.fullmatch(text):
        raise HTTPException(
            status_code=400,
            detail="expected_ship_at must be YYYY-MM or YYYY-MM-DD",
        )
    return text[:7]


def _normalize_expected_period(
    value: Optional[str], *, has_month: bool
) -> Optional[str]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    text = value.strip() if isinstance(value, str) else value
    if text not in _VALID_PERIODS:
        raise HTTPException(
            status_code=400,
            detail="expected_ship_period must be early, mid, or late",
        )
    if not has_month:
        raise HTTPException(
            status_code=400,
            detail="expected_ship_period requires expected_ship_at",
        )
    return text


def _attach_line_shipments(conn, item: dict[str, Any]) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT s.id AS shipment_id, s.direction, s.tracking_no, s.carrier, s.box_no
        FROM shipment_items si
        JOIN shipments s ON s.id = si.shipment_id
        WHERE si.item_id = ?
        ORDER BY s.id DESC
        """,
        (item["id"],),
    ).fetchall()
    for direction in ("inbound", "outbound"):
        item[f"{direction}_shipment_id"] = None
        item[f"{direction}_tracking_no"] = None
        item[f"{direction}_carrier"] = None
        item[f"{direction}_tracking_url"] = None
    item["outbound_box_no"] = None
    for row in rows:
        direction = row["direction"]
        if direction not in ("inbound", "outbound"):
            continue
        prefix = f"{direction}_"
        tracking_no = row["tracking_no"] or ""
        if tracking_no.startswith("__none__"):
            tracking_no = ""
        item[f"{prefix}shipment_id"] = row["shipment_id"]
        item[f"{prefix}tracking_no"] = tracking_no or None
        item[f"{prefix}carrier"] = row["carrier"]
        item[f"{prefix}tracking_url"] = tracking_url(row["carrier"], tracking_no)
        if direction == "outbound" and row["box_no"] is not None:
            item["outbound_box_no"] = row["box_no"]
    return item


def _order_out(conn, order_id: int) -> dict[str, Any]:
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        raise HTTPException(status_code=404, detail="order not found")
    lines = conn.execute(
        "SELECT * FROM items WHERE order_id = ? ORDER BY id",
        (order_id,),
    ).fetchall()
    line_dicts = [_attach_line_shipments(conn, dict(r)) for r in lines]
    result = dict(order)
    result["lines"] = line_dicts
    result["line_count"] = len(line_dicts)
    result["total_qty"] = sum(int(x["qty"]) for x in line_dicts)
    priced = [
        float(x["unit_cost"]) * int(x["qty"])
        for x in line_dicts
        if x.get("unit_cost") is not None
    ]
    goods_total = round(sum(priced), 2) if priced else None
    shipping = result.get("shipping_fee")
    if shipping is not None:
        try:
            shipping = float(shipping)
        except (TypeError, ValueError):
            shipping = None
    result["shipping_fee"] = shipping
    result["goods_total"] = goods_total
    if goods_total is not None or shipping is not None:
        result["order_total"] = round((goods_total or 0) + (shipping or 0), 2)
    else:
        result["order_total"] = None
    return result


def list_orders(
    status: Optional[str] = None,
    shop: Optional[str] = None,
    q: Optional[str] = None,
    expected_ship_month: Optional[str] = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("o.status = ?")
        params.append(status)
    if shop:
        clauses.append("o.shop = ?")
        params.append(shop)
    if q:
        clauses.append(
            "(o.order_ref LIKE ? OR o.shop LIKE ? OR o.note LIKE ?"
            " OR EXISTS (SELECT 1 FROM items i WHERE i.order_id = o.id"
            " AND (i.name LIKE ? OR i.ip LIKE ? OR i.barcode LIKE ?"
            " OR i.source_url LIKE ?)))"
        )
        like = f"%{q}%"
        params.extend([like, like, like, like, like, like, like])
    if expected_ship_month:
        month = _normalize_expected_ship(expected_ship_month)
        if not month:
            raise HTTPException(
                status_code=400,
                detail="expected_ship_month must be YYYY-MM",
            )
        clauses.append(
            "(o.expected_ship_at = ? OR EXISTS ("
            "SELECT 1 FROM items i WHERE i.order_id = o.id AND i.expected_ship_at = ?))"
        )
        params.extend([month, month])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT o.id FROM orders o
            {where}
            ORDER BY
                (o.order_ref = ''),
                o.order_ref ASC,
                o.id DESC
            """,
            params,
        ).fetchall()
        return [_order_out(conn, r["id"]) for r in rows]


def get_order(order_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        return _order_out(conn, order_id)


def create_order(payload: OrderCreate) -> dict[str, Any]:
    expected_ship_at = _normalize_expected_ship(payload.expected_ship_at)
    expected_ship_period = _normalize_expected_period(
        payload.expected_ship_period, has_month=bool(expected_ship_at)
    )
    shipping_fee = 0.0 if payload.shipping_fee is None else float(payload.shipping_fee)
    if shipping_fee < 0:
        shipping_fee = 0.0
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO orders (
                order_ref, shop, status, ordered_at, order_qty, shipping_fee,
                order_image_url, note, expected_ship_at, expected_ship_period
            ) VALUES (?, ?, 'ordered', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.order_ref.strip(),
                payload.shop.strip(),
                _now(),
                payload.order_qty,
                shipping_fee,
                (payload.order_image_url or "").strip(),
                payload.note.strip(),
                expected_ship_at,
                expected_ship_period,
            ),
        )
        order_id = int(cur.lastrowid)
        for line in payload.lines:
            _insert_line(conn, order_id, payload.order_ref.strip(), line)
        action_log.record(
            conn,
            "create_order",
            f"新建订单 {payload.order_ref or f'#{order_id}'}（{len(payload.lines)} 行）",
            {"order_id": order_id},
        )
        return _order_out(conn, order_id)


def _insert_line(
    conn,
    order_id: int,
    order_ref: str,
    line: LineCreate,
    *,
    shop_fallback: str = "",
) -> int:
    expected_ship_at = _normalize_expected_ship(line.expected_ship_at)
    expected_ship_period = _normalize_expected_period(
        line.expected_ship_period, has_month=bool(expected_ship_at)
    )
    shop = (line.shop or shop_fallback or "").strip()
    cur = conn.execute(
        """
        INSERT INTO items (
            order_id, name, shop, order_ref, qty, unit_cost, status,
            ordered_at, expected_ship_at, expected_ship_period, barcode, note,
            animegood_product_id, ip, image_url, source_url
        ) VALUES (?, ?, ?, ?, ?, ?, 'ordered', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            order_id,
            line.name.strip(),
            shop,
            order_ref,
            line.qty,
            line.unit_cost,
            _now(),
            expected_ship_at,
            expected_ship_period,
            line.barcode.strip(),
            line.note.strip(),
            line.animegood_product_id,
            line.ip.strip(),
            line.image_url.strip(),
            line.source_url.strip(),
        ),
    )
    return int(cur.lastrowid)


def add_lines(order_id: int, lines: list[LineCreate]) -> dict[str, Any]:
    if not lines:
        raise HTTPException(status_code=400, detail="lines required")
    with get_conn() as conn:
        order = conn.execute(
            "SELECT id, status, order_ref, shop FROM orders WHERE id = ?",
            (order_id,),
        ).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="order not found")
        if order["status"] == "cancelled":
            raise HTTPException(
                status_code=400, detail="cannot add lines to cancelled order"
            )
        new_ids = [
            _insert_line(
                conn,
                order_id,
                order["order_ref"] or "",
                line,
                shop_fallback=order["shop"] or "",
            )
            for line in lines
        ]
        sync_order_status(conn, order_id)
        action_log.record(
            conn,
            "add_lines",
            f"订单 #{order_id} 追加 {len(lines)} 行",
            {"order_id": order_id, "item_ids": new_ids},
        )
        return _order_out(conn, order_id)


def update_order(order_id: int, payload: OrderUpdate) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return get_order(order_id)

    if "status" in data and data["status"] not in ("cancelled",):
        current = get_order(order_id)
        if data["status"] != current["status"]:
            raise HTTPException(
                status_code=400,
                detail="status changes other than cancelled must go through inbound/outbound",
            )

    if "shipping_fee" in data:
        fee = data["shipping_fee"]
        data["shipping_fee"] = 0.0 if fee is None else max(0.0, float(fee))

    if "expected_ship_at" in data:
        data["expected_ship_at"] = _normalize_expected_ship(data["expected_ship_at"])
        if data["expected_ship_at"] is None:
            data["expected_ship_period"] = None

    if "expected_ship_period" in data or "expected_ship_at" in data:
        current = get_order(order_id)
        month = (
            data["expected_ship_at"]
            if "expected_ship_at" in data
            else current.get("expected_ship_at")
        )
        period_raw = (
            data["expected_ship_period"]
            if "expected_ship_period" in data
            else current.get("expected_ship_period")
        )
        data["expected_ship_period"] = _normalize_expected_period(
            period_raw, has_month=bool(month)
        )

    with get_conn() as conn:
        exists = conn.execute(
            "SELECT id, status, order_ref FROM orders WHERE id = ?",
            (order_id,),
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="order not found")

        prev_status = exists["status"]
        fields = []
        params: list[Any] = []
        for key, value in data.items():
            if isinstance(value, str) and key != "status":
                value = value.strip()
            fields.append(f"{key} = ?")
            params.append(value)
        params.append(order_id)
        conn.execute(
            f"UPDATE orders SET {', '.join(fields)} WHERE id = ?",
            params,
        )

        if "order_ref" in data:
            conn.execute(
                "UPDATE items SET order_ref = ? WHERE order_id = ?",
                (data["order_ref"], order_id),
            )
        if "shop" in data:
            # only fill blank line shops? keep order shop as header; don't overwrite lines
            pass

        if data.get("status") == "cancelled" and prev_status != "cancelled":
            line_rows = conn.execute(
                "SELECT id, status FROM items WHERE order_id = ?",
                (order_id,),
            ).fetchall()
            restores = [{"id": r["id"], "status": r["status"]} for r in line_rows]
            conn.execute(
                "UPDATE items SET status = 'cancelled' WHERE order_id = ? AND status != 'cancelled'",
                (order_id,),
            )
            action_log.record(
                conn,
                "cancel_order",
                f"取消订单 {exists['order_ref'] or f'#{order_id}'}",
                {
                    "order_id": order_id,
                    "prev_status": prev_status,
                    "item_restores": restores,
                },
            )
        return _order_out(conn, order_id)


def get_stats() -> dict[str, int]:
    with get_conn() as conn:
        order_counts = {
            r["status"]: r["cnt"]
            for r in conn.execute(
                "SELECT status, COUNT(*) AS cnt FROM orders GROUP BY status"
            ).fetchall()
        }
        ship_counts = {
            r["status"]: r["cnt"]
            for r in conn.execute(
                "SELECT status, COUNT(*) AS cnt FROM shipments GROUP BY status"
            ).fetchall()
        }
        inbound_shipments_shipped = conn.execute(
            """
            SELECT COUNT(*) FROM shipments
            WHERE status = 'shipped' AND direction = 'inbound'
            """
        ).fetchone()[0]
        outbound_shipments_shipped = conn.execute(
            """
            SELECT COUNT(*) FROM shipments
            WHERE status = 'shipped' AND direction = 'outbound'
            """
        ).fetchone()[0]
        orders_total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    return {
        "ordered": order_counts.get("ordered", 0),
        "inbound_shipped": order_counts.get("inbound_shipped", 0),
        "in_stock": order_counts.get("in_stock", 0),
        "outbound_shipped": order_counts.get("outbound_shipped", 0),
        "delivered": order_counts.get("delivered", 0),
        "cancelled": order_counts.get("cancelled", 0),
        "inbound_shipments_shipped": inbound_shipments_shipped,
        "outbound_shipments_shipped": outbound_shipments_shipped,
        "shipments_delivered": ship_counts.get("delivered", 0),
        "orders_total": orders_total,
    }


def list_shops() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT shop FROM orders
            WHERE shop != ''
            ORDER BY shop COLLATE NOCASE
            """
        ).fetchall()
        return [r["shop"] for r in rows]
