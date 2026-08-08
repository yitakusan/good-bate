"""Customer order-request (C-end apply) service.

Lifecycle (v1): submitted -> ordered | rejected
Decoupled from inventory until staff confirms ordered (optional stock order).
"""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from app.database import get_conn, row_to_dict
from app.models import (
    LineCreate,
    OrderCreate,
    OrderRequestConfirm,
    OrderRequestCreate,
    OrderRequestReject,
)
from app.services import action_log
from app.services import orders as orders_svc

STATUS_LABEL = {
    "submitted": "已提交",
    "ordered": "已下单",
    "rejected": "已拒绝",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _gen_code(conn) -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(20):
        code = "SG-" + "".join(secrets.choice(alphabet) for _ in range(6))
        exists = conn.execute(
            "SELECT 1 FROM order_requests WHERE request_code = ?", (code,)
        ).fetchone()
        if not exists:
            return code
    raise HTTPException(status_code=500, detail="could not allocate request code")


def _row_out(row) -> dict[str, Any]:
    data = row_to_dict(row) or {}
    return data


def _public_out(row) -> dict[str, Any]:
    data = _row_out(row)
    status = data.get("status") or "submitted"
    unit_cost = data.get("unit_cost")
    qty = int(data.get("qty") or 1)
    amount = None
    if unit_cost is not None:
        try:
            amount = float(unit_cost) * qty
        except (TypeError, ValueError):
            amount = None
    return {
        "request_code": data.get("request_code") or "",
        "status": status,
        "status_label": STATUS_LABEL.get(status, status),
        "name": data.get("name") or "",
        "shop": data.get("shop") or "",
        "unit_cost": unit_cost,
        "amount": amount,
        "image_url": data.get("image_url") or "",
        "source_url": data.get("source_url") or "",
        "qty": qty,
        "shop_order_ref": data.get("shop_order_ref") or "",
        "ordered_at": data.get("ordered_at"),
        "staff_note": data.get("staff_note") or "",
        "reject_reason": data.get("reject_reason") or "",
        "created_at": data.get("created_at") or "",
        "updated_at": data.get("updated_at") or "",
    }


def create_request(payload: OrderRequestCreate) -> dict[str, Any]:
    now = _now()
    with get_conn() as conn:
        code = _gen_code(conn)
        cur = conn.execute(
            """
            INSERT INTO order_requests (
                request_code, status, name, shop, unit_cost, image_url, source_url,
                ip, barcode, qty, contact, note, created_at, updated_at
            ) VALUES (?, 'submitted', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                payload.name.strip(),
                (payload.shop or "").strip(),
                payload.unit_cost,
                (payload.image_url or "").strip(),
                payload.source_url.strip(),
                (payload.ip or "").strip(),
                (payload.barcode or "").strip(),
                max(1, int(payload.qty)),
                (payload.contact or "").strip(),
                (payload.note or "").strip(),
                now,
                now,
            ),
        )
        request_id = int(cur.lastrowid)
        action_log.record(
            conn,
            "create_order_request",
            f"顾客申请 {code} · {payload.name.strip()[:40]} ×{payload.qty}",
            {"order_request_id": request_id, "request_code": code},
        )
        row = conn.execute(
            "SELECT * FROM order_requests WHERE id = ?", (request_id,)
        ).fetchone()
        return _public_out(row)


def get_by_code(code: str) -> dict[str, Any]:
    code = (code or "").strip().upper()
    if not code:
        raise HTTPException(status_code=404, detail="request not found")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM order_requests WHERE upper(request_code) = ?",
            (code,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="request not found")
        return _public_out(row)


def list_requests(status: Optional[str] = None) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        if status not in STATUS_LABEL:
            raise HTTPException(status_code=400, detail="invalid status")
        clauses.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM order_requests {where} ORDER BY id DESC",
            params,
        ).fetchall()
        return [_row_out(r) for r in rows]


def list_public_requests(status: Optional[str] = None) -> list[dict[str, Any]]:
    """Customer-facing list (single-tenant: all requests)."""
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        if status not in STATUS_LABEL:
            raise HTTPException(status_code=400, detail="invalid status")
        clauses.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM order_requests {where} ORDER BY id DESC",
            params,
        ).fetchall()
        return [_public_out(r) for r in rows]


def get_request(request_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM order_requests WHERE id = ?", (request_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="request not found")
        return _row_out(row)


def confirm_ordered(
    request_id: int, payload: OrderRequestConfirm
) -> dict[str, Any]:
    shop_ref = payload.shop_order_ref.strip()
    if not shop_ref:
        raise HTTPException(status_code=400, detail="shop_order_ref required")
    now = _now()

    current = get_request(request_id)
    if current["status"] == "rejected":
        raise HTTPException(status_code=400, detail="request already rejected")
    if current["status"] == "ordered" and current.get("stock_order_id"):
        raise HTTPException(status_code=400, detail="already confirmed")

    stock_order_id_out: Optional[int] = current.get("stock_order_id")
    if payload.create_stock_order and not stock_order_id_out:
        order = orders_svc.create_order(
            OrderCreate(
                order_ref=shop_ref,
                shop=current.get("shop") or "",
                order_qty=int(current.get("qty") or 1),
                shipping_fee=payload.shipping_fee if payload.shipping_fee is not None else 0,
                exchange_rate=payload.exchange_rate,
                note=f"来自申请 {current.get('request_code')}"
                + (f"；{payload.staff_note}" if payload.staff_note.strip() else ""),
                lines=[
                    LineCreate(
                        name=current["name"],
                        shop=current.get("shop") or "",
                        qty=int(current.get("qty") or 1),
                        unit_cost=current.get("unit_cost"),
                        ip=current.get("ip") or "",
                        image_url=current.get("image_url") or "",
                        source_url=current.get("source_url") or "",
                        barcode=current.get("barcode") or "",
                        note=current.get("note") or "",
                    )
                ],
            )
        )
        stock_order_id_out = int(order["id"])

    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM order_requests WHERE id = ?", (request_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="request not found")
        conn.execute(
            """
            UPDATE order_requests SET
                status = 'ordered',
                shop_order_ref = ?,
                ordered_at = ?,
                staff_note = ?,
                stock_order_id = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                shop_ref,
                now,
                payload.staff_note.strip(),
                stock_order_id_out,
                now,
                request_id,
            ),
        )
        action_log.record(
            conn,
            "confirm_order_request",
            f"申请 {row['request_code']} 已下单 · {shop_ref}",
            {
                "order_request_id": request_id,
                "shop_order_ref": shop_ref,
                "stock_order_id": stock_order_id_out,
            },
        )
        out = conn.execute(
            "SELECT * FROM order_requests WHERE id = ?", (request_id,)
        ).fetchone()
        return _row_out(out)


def reject_request(request_id: int, payload: OrderRequestReject) -> dict[str, Any]:
    reason = payload.reject_reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="reject_reason required")
    now = _now()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM order_requests WHERE id = ?", (request_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="request not found")
        if row["status"] == "ordered":
            raise HTTPException(status_code=400, detail="cannot reject ordered request")
        conn.execute(
            """
            UPDATE order_requests SET
                status = 'rejected',
                reject_reason = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (reason, now, request_id),
        )
        action_log.record(
            conn,
            "reject_order_request",
            f"申请 {row['request_code']} 已拒绝",
            {"order_request_id": request_id, "reject_reason": reason},
        )
        out = conn.execute(
            "SELECT * FROM order_requests WHERE id = ?", (request_id,)
        ).fetchone()
        return _row_out(out)
