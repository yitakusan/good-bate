"""Customer order-request (C-end apply) service.

Lifecycle: pending_payment -> submitted -> ordered | rejected
Login required; 30% deposit must be confirmed before status becomes submitted.
"""

# ============================================================
# FEATURE: ORDER_REQUEST
#
# [用途] 顾客申请生命周期：pending_payment → submitted → ordered | rejected
# [接口] /api/public/order-requests*  /api/order-requests*  /api/me/order-requests*
# [数据库] order_requests
# [代码索引] docs/CODE_INDEX.md#feature-order_request
# ============================================================

from __future__ import annotations

import re
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
from app.notifications import notify_order_request_status
from app.services import action_log
from app.services import orders as orders_svc
from app.settings import get_settings

STATUS_LABEL = {
    "pending_payment": "待付定金",
    "submitted": "已提交",
    "ordered": "已下单",
    "rejected": "已拒绝",
}

# Global site-wide: SG-0001 ; per-account: SG{user_id}-0001
_GLOBAL_CODE_RE = re.compile(r"^SG-(\d+)$", re.IGNORECASE)
_ACCOUNT_CODE_RE = re.compile(r"^SG(\d+)-(\d+)$", re.IGNORECASE)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _gen_global_code(conn) -> str:
    """Site ledger: SG-0001, SG-0002, …"""
    rows = conn.execute("SELECT request_code FROM order_requests").fetchall()
    max_seq = 0
    for row in rows:
        code = (row["request_code"] or "").strip()
        m = _GLOBAL_CODE_RE.match(code)
        if not m:
            continue
        try:
            max_seq = max(max_seq, int(m.group(1)))
        except ValueError:
            continue
    for _ in range(50):
        max_seq += 1
        code = f"SG-{max_seq:04d}"
        exists = conn.execute(
            "SELECT 1 FROM order_requests WHERE request_code = ?", (code,)
        ).fetchone()
        if not exists:
            return code
    raise HTTPException(status_code=500, detail="could not allocate request code")


def _gen_account_order_no(conn, user_id: int) -> str:
    """Per-account ledger: SG{user_id}-0001, …"""
    uid = int(user_id)
    prefix = f"SG{uid}-"
    rows = conn.execute(
        """
        SELECT account_order_no, request_code FROM order_requests
        WHERE user_id = ?
        """,
        (uid,),
    ).fetchall()
    max_seq = 0
    for row in rows:
        for raw in (row["account_order_no"], row["request_code"]):
            code = (raw or "").strip()
            m = _ACCOUNT_CODE_RE.match(code)
            if not m:
                continue
            if int(m.group(1)) != uid:
                continue
            try:
                max_seq = max(max_seq, int(m.group(2)))
            except ValueError:
                continue
    for _ in range(50):
        max_seq += 1
        code = f"{prefix}{max_seq:04d}"
        exists = conn.execute(
            """
            SELECT 1 FROM order_requests
            WHERE account_order_no = ? OR request_code = ?
            """,
            (code, code),
        ).fetchone()
        if not exists:
            return code
    raise HTTPException(status_code=500, detail="could not allocate account order no")


def _deposit_rate() -> float:
    rate = float(get_settings().deposit_rate or 0.3)
    if rate <= 0 or rate > 1:
        return 0.3
    return rate


def _calc_deposit(unit_cost: Optional[float], qty: int) -> tuple[float, Optional[float]]:
    rate = _deposit_rate()
    if unit_cost is None:
        return rate, None
    try:
        goods = float(unit_cost) * max(1, int(qty))
    except (TypeError, ValueError):
        return rate, None
    return rate, round(goods * rate, 2)


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
        "account_order_no": (data.get("account_order_no") or "").strip()
        or (data.get("request_code") or ""),
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
        "deposit_rate": data.get("deposit_rate"),
        "deposit_amount": data.get("deposit_amount"),
        "deposit_paid_at": data.get("deposit_paid_at"),
        "payment_ref": data.get("payment_ref") or "",
    }


def create_request(payload: OrderRequestCreate, user_id: Optional[int] = None) -> dict[str, Any]:
    if not user_id:
        raise HTTPException(status_code=401, detail="login required to submit order")
    if payload.unit_cost is None:
        raise HTTPException(status_code=400, detail="unit_cost required for deposit")
    try:
        if float(payload.unit_cost) < 0:
            raise HTTPException(status_code=400, detail="invalid unit_cost")
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="invalid unit_cost") from exc

    now = _now()
    rate, deposit_amount = _calc_deposit(payload.unit_cost, payload.qty)
    if deposit_amount is None:
        raise HTTPException(status_code=400, detail="cannot calculate deposit")

    with get_conn() as conn:
        code = _gen_global_code(conn)
        account_no = _gen_account_order_no(conn, int(user_id))
        cur = conn.execute(
            """
            INSERT INTO order_requests (
                request_code, account_order_no, status, name, shop, unit_cost, image_url, source_url,
                ip, barcode, qty, contact, note, user_id,
                deposit_rate, deposit_amount, deposit_paid_at, payment_ref,
                created_at, updated_at
            ) VALUES (?, ?, 'pending_payment', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, '', ?, ?)
            """,
            (
                code,
                account_no,
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
                int(user_id),
                rate,
                deposit_amount,
                now,
                now,
            ),
        )
        request_id = int(cur.lastrowid)
        action_log.record(
            conn,
            "create_order_request",
            f"待付定金 {account_no}（全站 {code}）· {payload.name.strip()[:40]} ×{payload.qty} · 定金 {deposit_amount}",
            {
                "order_request_id": request_id,
                "request_code": code,
                "account_order_no": account_no,
                "deposit_amount": deposit_amount,
            },
        )
        row = conn.execute(
            "SELECT * FROM order_requests WHERE id = ?", (request_id,)
        ).fetchone()
        out = _public_out(row)
        full = _row_out(row)
    notify_order_request_status(full, "pending_payment")
    return out


def confirm_deposit(
    *,
    code: Optional[str] = None,
    request_id: Optional[int] = None,
    user_id: Optional[int] = None,
    payment_ref: str = "",
    staff: bool = False,
) -> dict[str, Any]:
    """Confirm 30% deposit paid → status submitted. Finance webhook can call this later."""
    now = _now()
    with get_conn() as conn:
        if request_id is not None:
            row = conn.execute(
                "SELECT * FROM order_requests WHERE id = ?", (request_id,)
            ).fetchone()
        else:
            code_n = (code or "").strip().upper()
            if not code_n:
                raise HTTPException(status_code=404, detail="request not found")
            row = conn.execute(
                "SELECT * FROM order_requests WHERE upper(request_code) = ?",
                (code_n,),
            ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="request not found")
        if not staff:
            if not user_id or int(row["user_id"] or 0) != int(user_id):
                raise HTTPException(status_code=403, detail="not your request")
        if row["status"] == "submitted":
            return _public_out(row) if not staff else _row_out(row)
        if row["status"] != "pending_payment":
            raise HTTPException(
                status_code=400,
                detail=f"cannot confirm deposit in status {row['status']}",
            )
        conn.execute(
            """
            UPDATE order_requests SET
                status = 'submitted',
                deposit_paid_at = ?,
                payment_ref = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (now, (payment_ref or "").strip(), now, row["id"]),
        )
        action_log.record(
            conn,
            "confirm_deposit",
            f"定金已确认 {row['request_code']} · {row['deposit_amount']}",
            {
                "order_request_id": row["id"],
                "request_code": row["request_code"],
                "payment_ref": (payment_ref or "").strip(),
            },
        )
        out = conn.execute(
            "SELECT * FROM order_requests WHERE id = ?", (row["id"],)
        ).fetchone()
        result = _row_out(out) if staff else _public_out(out)
    notify_order_request_status(_row_out(out), "submitted")
    return result


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
    """Public board: hide unpaid drafts."""
    clauses: list[str] = ["status != 'pending_payment'"]
    params: list[Any] = []
    if status:
        if status not in STATUS_LABEL:
            raise HTTPException(status_code=400, detail="invalid status")
        if status == "pending_payment":
            return []
        clauses.append("status = ?")
        params.append(status)
    where = "WHERE " + " AND ".join(clauses)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM order_requests {where} ORDER BY id DESC",
            params,
        ).fetchall()
        return [_public_out(r) for r in rows]


def list_for_user(user_id: int, status: Optional[str] = None) -> list[dict[str, Any]]:
    clauses = ["user_id = ?"]
    params: list[Any] = [user_id]
    if status:
        if status not in STATUS_LABEL:
            raise HTTPException(status_code=400, detail="invalid status")
        clauses.append("status = ?")
        params.append(status)
    where = "WHERE " + " AND ".join(clauses)
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
    if current["status"] == "pending_payment":
        raise HTTPException(status_code=400, detail="deposit not paid yet")
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
        result = _row_out(out)
    notify_order_request_status(result, "ordered")
    return result


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
        result = _row_out(out)
    notify_order_request_status(result, "rejected")
    return result
