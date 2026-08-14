from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from app.database import get_conn
from app.models import ItemCreate, ItemUpdate, LineCreate, OrderCreate
from app.services import action_log
from app.services import orders as orders_svc
from app.services.order_status import sync_order_status
from app.services.orders import (
    _attach_line_shipments,
    _insert_line,
    _normalize_expected_period,
    _normalize_expected_ship,
    _resolve_product_kind,
)

# ============================================================
# FEATURE: ORDER
#
# [用途] 货品列表/更新；批量导入见 FEATURE: ORDER_IMPORT
# [接口] /api/items*
# [代码索引] docs/CODE_INDEX.md#feature-order
# ============================================================


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def list_items(
    status: Optional[str] = None,
    shop: Optional[str] = None,
    q: Optional[str] = None,
    expected_ship_month: Optional[str] = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("i.status = ?")
        params.append(status)
    if shop:
        clauses.append("i.shop = ?")
        params.append(shop)
    if q:
        clauses.append(
            "(i.name LIKE ? OR i.shop LIKE ? OR i.order_ref LIKE ? OR i.note LIKE ?"
            " OR i.ip LIKE ? OR i.product_kind LIKE ? OR i.source_url LIKE ?"
            " OR i.barcode LIKE ?)"
        )
        like = f"%{q}%"
        params.extend([like, like, like, like, like, like, like, like])
    if expected_ship_month:
        month = _normalize_expected_ship(expected_ship_month)
        if not month:
            raise HTTPException(
                status_code=400,
                detail="expected_ship_month must be YYYY-MM",
            )
        clauses.append("i.expected_ship_at = ?")
        params.append(month)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT i.*, o.order_qty AS order_qty, o.order_image_url AS order_image_url
        FROM items i
        LEFT JOIN orders o ON o.id = i.order_id
        {where}
        ORDER BY
            (i.order_ref = ''),
            i.order_ref ASC,
            i.id ASC
    """
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [_attach_line_shipments(conn, dict(r)) for r in rows]


def get_item(item_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT i.*, o.order_qty AS order_qty, o.order_image_url AS order_image_url
            FROM items i
            LEFT JOIN orders o ON o.id = i.order_id
            WHERE i.id = ?
            """,
            (item_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="item not found")
        return _attach_line_shipments(conn, dict(row))


def create_item(payload: ItemCreate) -> dict[str, Any]:
    order = orders_svc.create_order(
        OrderCreate(
            order_ref=payload.order_ref,
            shop=payload.shop,
            order_qty=payload.order_qty,
            order_image_url=payload.order_image_url or "",
            note=payload.note,
            expected_ship_at=payload.expected_ship_at,
            expected_ship_period=payload.expected_ship_period,
            lines=[
                LineCreate(
                    name=payload.name,
                    shop=payload.shop,
                    qty=payload.qty,
                    unit_cost=payload.unit_cost,
                    note=payload.note,
                    animegood_product_id=payload.animegood_product_id,
                    ip=payload.ip,
                    image_url=payload.image_url,
                    source_url=payload.source_url,
                    expected_ship_at=payload.expected_ship_at,
                    expected_ship_period=payload.expected_ship_period,
                    barcode=payload.barcode,
                )
            ],
        )
    )
    return order["lines"][0]


# ============================================================
# FEATURE: ORDER_IMPORT
# [业务逻辑] create_items_batch — 抓取导入写入订单/货品
# [接口] POST /api/items/batch
# ============================================================
def create_items_batch(payloads: list[ItemCreate]) -> list[dict[str, Any]]:
    """Group by order_ref into orders; empty ref → one order each."""
    if not payloads:
        return []
    groups: dict[str, list[ItemCreate]] = {}
    solo: list[ItemCreate] = []
    for p in payloads:
        ref = (p.order_ref or "").strip()
        if ref:
            groups.setdefault(ref, []).append(p)
        else:
            solo.append(p)

    created_lines: list[dict[str, Any]] = []
    order_ids: list[int] = []
    with get_conn() as conn:
        for ref, items in groups.items():
            first = items[0]
            expected_ship_at = _normalize_expected_ship(first.expected_ship_at)
            expected_ship_period = _normalize_expected_period(
                first.expected_ship_period, has_month=bool(expected_ship_at)
            )
            cur = conn.execute(
                """
                INSERT INTO orders (
                    order_ref, shop, status, ordered_at, order_qty, order_image_url,
                    note, expected_ship_at, expected_ship_period
                ) VALUES (?, ?, 'ordered', ?, ?, ?, ?, ?, ?)
                """,
                (
                    ref,
                    first.shop.strip(),
                    _now(),
                    first.order_qty,
                    (first.order_image_url or "").strip(),
                    first.note.strip(),
                    expected_ship_at,
                    expected_ship_period,
                ),
            )
            order_id = int(cur.lastrowid)
            order_ids.append(order_id)
            for item in items:
                _insert_line(
                    conn,
                    order_id,
                    ref,
                    LineCreate(
                        name=item.name,
                        shop=item.shop or first.shop,
                        qty=item.qty,
                        unit_cost=item.unit_cost,
                        note=item.note,
                        animegood_product_id=item.animegood_product_id,
                        ip=item.ip,
                        image_url=item.image_url,
                        source_url=item.source_url,
                        expected_ship_at=item.expected_ship_at,
                        expected_ship_period=item.expected_ship_period,
                        barcode=item.barcode,
                    ),
                )

        for item in solo:
            expected_ship_at = _normalize_expected_ship(item.expected_ship_at)
            expected_ship_period = _normalize_expected_period(
                item.expected_ship_period, has_month=bool(expected_ship_at)
            )
            cur = conn.execute(
                """
                INSERT INTO orders (
                    order_ref, shop, status, ordered_at, order_qty, order_image_url,
                    note, expected_ship_at, expected_ship_period
                ) VALUES ('', ?, 'ordered', ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.shop.strip(),
                    _now(),
                    item.order_qty,
                    (item.order_image_url or "").strip(),
                    item.note.strip(),
                    expected_ship_at,
                    expected_ship_period,
                ),
            )
            order_id = int(cur.lastrowid)
            order_ids.append(order_id)
            _insert_line(
                conn,
                order_id,
                "",
                LineCreate(
                    name=item.name,
                    shop=item.shop,
                    qty=item.qty,
                    unit_cost=item.unit_cost,
                    note=item.note,
                    animegood_product_id=item.animegood_product_id,
                    ip=item.ip,
                    image_url=item.image_url,
                    source_url=item.source_url,
                    expected_ship_at=item.expected_ship_at,
                    expected_ship_period=item.expected_ship_period,
                    barcode=item.barcode,
                ),
            )

        action_log.record(
            conn,
            "create_order_batch",
            f"批量导入 {len(order_ids)} 笔订单",
            {"order_ids": order_ids},
        )
        for oid in order_ids:
            out = orders_svc._order_out(conn, oid)
            created_lines.extend(out["lines"])
    return created_lines


def update_item(item_id: int, payload: ItemUpdate) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return get_item(item_id)

    if "status" in data and data["status"] not in ("cancelled",):
        current = get_item(item_id)
        if data["status"] != current["status"]:
            raise HTTPException(
                status_code=400,
                detail="status changes other than cancelled must go through shipments",
            )

    if "expected_ship_at" in data:
        data["expected_ship_at"] = _normalize_expected_ship(data["expected_ship_at"])
        if data["expected_ship_at"] is None:
            data["expected_ship_period"] = None

    if "expected_ship_period" in data or "expected_ship_at" in data:
        current = get_item(item_id)
        month = data["expected_ship_at"] if "expected_ship_at" in data else current.get(
            "expected_ship_at"
        )
        period_raw = (
            data["expected_ship_period"]
            if "expected_ship_period" in data
            else current.get("expected_ship_period")
        )
        data["expected_ship_period"] = _normalize_expected_period(
            period_raw, has_month=bool(month)
        )

    data.pop("order_ref", None)

    # If name changes and kind not explicitly set, re-detect from new name
    if "name" in data and "product_kind" not in data:
        data["product_kind"] = _resolve_product_kind(str(data["name"]), "")
    elif "product_kind" in data and data["product_kind"] is not None:
        data["product_kind"] = str(data["product_kind"]).strip()

    fields = []
    params: list[Any] = []
    for key, value in data.items():
        if isinstance(value, str):
            value = value.strip()
        fields.append(f"{key} = ?")
        params.append(value)

    params.append(item_id)
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT id, status, name, order_id FROM items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="item not found")
        prev_status = exists["status"]
        conn.execute(f"UPDATE items SET {', '.join(fields)} WHERE id = ?", params)
        if data.get("status") == "cancelled" and prev_status != "cancelled":
            action_log.record(
                conn,
                "cancel_item",
                f"取消明细「{exists['name']}」",
                {
                    "item_id": item_id,
                    "prev_status": prev_status,
                    "order_id": exists["order_id"],
                },
            )
        if exists["order_id"] is not None:
            sync_order_status(conn, int(exists["order_id"]))
        row = conn.execute(
            """
            SELECT i.*, o.order_qty AS order_qty, o.order_image_url AS order_image_url
            FROM items i
            LEFT JOIN orders o ON o.id = i.order_id
            WHERE i.id = ?
            """,
            (item_id,),
        ).fetchone()
        return _attach_line_shipments(conn, dict(row))


def list_shops() -> list[str]:
    return orders_svc.list_shops()


def get_stats() -> dict[str, int]:
    return orders_svc.get_stats()
