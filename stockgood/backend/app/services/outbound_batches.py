from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Optional

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter

from app.database import get_conn
from app.services import action_log
from app.services.order_status import sync_order_status
from app.services.shipments import _shipment_with_items
from app.services.stock_boxes import release_orders as release_stock_box_orders


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _payment_status(receivable: Optional[float], received: float) -> str:
    if receivable is None:
        return "unpaid" if received <= 0 else "partial"
    if received <= 0:
        return "unpaid"
    if received + 1e-9 >= receivable:
        return "paid"
    return "partial"


def _compute_freight_cny(
    unit_price: Optional[float],
    weight: Optional[float],
    rate: Optional[float],
) -> Optional[float]:
    if unit_price is None or weight is None or rate is None:
        return None
    if rate <= 0:
        return None
    return round(float(unit_price) * float(weight) * float(rate), 2)


def _recompute_batch_totals(
    goods_receivable_cny: Optional[float],
    freight_cny: Optional[float],
    amount_received_cny: float,
) -> tuple[Optional[float], str, Optional[float]]:
    parts = [v for v in (goods_receivable_cny, freight_cny) if v is not None]
    receivable = round(sum(parts), 2) if parts else None
    status = _payment_status(receivable, amount_received_cny)
    unreceived = (
        round(receivable - amount_received_cny, 2) if receivable is not None else None
    )
    return receivable, status, unreceived


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
    received = _as_float(batch["amount_received_cny"]) or 0.0
    goods_cny = _as_float(batch["goods_receivable_cny"])
    freight_cny = _as_float(batch["freight_cny"])
    receivable = _as_float(batch["amount_receivable_cny"])
    if receivable is None:
        receivable, _, unreceived = _recompute_batch_totals(
            goods_cny, freight_cny, received
        )
    else:
        unreceived = round(receivable - received, 2)
    status = batch["payment_status"] or _payment_status(receivable, received)
    return {
        "id": batch["id"],
        "note": batch["note"],
        "created_at": batch["created_at"],
        "boxes": box_outs,
        "box_count": len(box_outs),
        "item_count": sum(len(b["items"]) for b in box_outs),
        "goods_jpy": _as_float(batch["goods_jpy"]),
        "order_shipping_jpy": _as_float(batch["order_shipping_jpy"]),
        "goods_receivable_cny": goods_cny,
        "freight_exchange_rate": _as_float(batch["freight_exchange_rate"]),
        "freight_unit_price_jpy": _as_float(batch["freight_unit_price_jpy"]),
        "chargeable_weight": _as_float(batch["chargeable_weight"]),
        "freight_cny": freight_cny,
        "amount_receivable_cny": receivable,
        "amount_received_cny": received,
        "amount_unreceived_cny": unreceived,
        "payment_status": status,
        "payment_note": batch["payment_note"] or "",
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


def _lock_receivables(
    conn,
    item_ids: set[int],
    order_ids: set[int],
) -> dict[str, Optional[float]]:
    """Lock goods JPY/CNY at outbound create time using each order's rate."""
    goods_jpy = 0.0
    goods_cny = 0.0
    order_shipping_jpy = 0.0
    order_shipping_cny = 0.0
    has_goods_priced = False
    has_goods_cny = False
    has_ship_cny = False

    placeholders = ",".join("?" * len(item_ids))
    lines = conn.execute(
        f"""
        SELECT i.id, i.order_id, i.unit_cost, i.qty, o.exchange_rate
        FROM items i
        JOIN orders o ON o.id = i.order_id
        WHERE i.id IN ({placeholders})
        """,
        list(item_ids),
    ).fetchall()
    for line in lines:
        if line["unit_cost"] is None:
            continue
        line_jpy = float(line["unit_cost"]) * int(line["qty"])
        goods_jpy += line_jpy
        has_goods_priced = True
        rate = _as_float(line["exchange_rate"])
        if rate is not None and rate > 0:
            goods_cny += line_jpy * rate
            has_goods_cny = True

    for oid in order_ids:
        order = conn.execute(
            "SELECT shipping_fee, exchange_rate FROM orders WHERE id = ?",
            (oid,),
        ).fetchone()
        if not order:
            continue
        ship = _as_float(order["shipping_fee"]) or 0.0
        order_shipping_jpy += ship
        rate = _as_float(order["exchange_rate"])
        if rate is not None and rate > 0:
            order_shipping_cny += ship * rate
            has_ship_cny = True

    goods_receivable = None
    if has_goods_cny or has_ship_cny:
        goods_receivable = round(
            (goods_cny if has_goods_cny else 0.0)
            + (order_shipping_cny if has_ship_cny else 0.0),
            2,
        )

    return {
        "goods_jpy": round(goods_jpy, 2) if has_goods_priced else None,
        "order_shipping_jpy": round(order_shipping_jpy, 2),
        "goods_receivable_cny": goods_receivable,
    }


def create_batch(
    boxes: list[dict[str, Any]],
    note: str = "",
    *,
    allow_missing_barcode: bool = False,
    missing_barcode_note: str = "",
    freight_exchange_rate: Optional[float] = None,
    freight_unit_price_jpy: Optional[float] = None,
    chargeable_weight: Optional[float] = None,
) -> dict[str, Any]:
    """
    Outbound batch: multiple boxes, each with independent box_no + tracking.
    A box may contain lines from multiple orders (secondary group by order).
    No partial outbound: if any line of an order is included, all in_stock
    lines of that order must be in this batch (any boxes).
    Barcode required on every line unless allow_missing_barcode + note.
    Locks goods receivable CNY at create time; international freight uses
    an independent rate.
    """
    if not boxes:
        raise HTTPException(status_code=400, detail="boxes required")
    special_note = (missing_barcode_note or "").strip()
    if allow_missing_barcode and not special_note:
        raise HTTPException(
            status_code=400,
            detail="勾选特殊情况时必须填写无条形码备注",
        )

    for label, value in (
        ("freight_exchange_rate", freight_exchange_rate),
        ("freight_unit_price_jpy", freight_unit_price_jpy),
        ("chargeable_weight", chargeable_weight),
    ):
        if value is not None and float(value) < 0:
            raise HTTPException(status_code=400, detail=f"{label} invalid")
    if freight_exchange_rate is not None and float(freight_exchange_rate) <= 0:
        raise HTTPException(status_code=400, detail="freight_exchange_rate must be > 0")

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
            SELECT id, order_id, order_ref, status, qty, name, barcode
            FROM items WHERE id IN ({placeholders})
            """,
            list(seen_items),
        ).fetchall()
        by_id = {r["id"]: r for r in rows}
        if len(by_id) != len(seen_items):
            missing = [iid for iid in seen_items if iid not in by_id]
            raise HTTPException(status_code=404, detail=f"items not found: {missing}")

        no_barcode = [
            r
            for r in by_id.values()
            if not (r["barcode"] or "").strip()
        ]
        if no_barcode and not allow_missing_barcode:
            names = "、".join(f"「{r['name']}」" for r in no_barcode[:5])
            more = f" 等 {len(no_barcode)} 行" if len(no_barcode) > 5 else ""
            raise HTTPException(
                status_code=400,
                detail=(
                    f"出库必须登记条形码，以下货品尚未填写：{names}{more}。"
                    "请补条码，或勾选特殊情况并备注。"
                ),
            )

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

        batch_note = note.strip()
        if allow_missing_barcode and no_barcode:
            tag = f"【无条码特批】{special_note}"
            batch_note = f"{batch_note} | {tag}".strip(" |") if batch_note else tag

        locked = _lock_receivables(conn, seen_items, order_ids)
        freight_rate = (
            float(freight_exchange_rate) if freight_exchange_rate is not None else None
        )
        freight_unit = (
            float(freight_unit_price_jpy)
            if freight_unit_price_jpy is not None
            else None
        )
        freight_weight = (
            float(chargeable_weight) if chargeable_weight is not None else None
        )
        freight_cny = _compute_freight_cny(freight_unit, freight_weight, freight_rate)
        receivable, pay_status, _ = _recompute_batch_totals(
            locked["goods_receivable_cny"], freight_cny, 0.0
        )

        cur = conn.execute(
            """
            INSERT INTO outbound_batches (
                note, created_at,
                goods_jpy, order_shipping_jpy, goods_receivable_cny,
                freight_exchange_rate, freight_unit_price_jpy, chargeable_weight,
                freight_cny, amount_receivable_cny, amount_received_cny,
                payment_status, payment_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, '')
            """,
            (
                batch_note,
                _now(),
                locked["goods_jpy"],
                locked["order_shipping_jpy"],
                locked["goods_receivable_cny"],
                freight_rate,
                freight_unit,
                freight_weight,
                freight_cny,
                receivable,
                pay_status,
            ),
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

        # Warehouse stock boxes are independent of outbound packing;
        # once orders leave stock, drop them from any stock box.
        release_stock_box_orders(conn, order_ids)

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


def update_finance(batch_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Update international freight fields and/or amount_received_cny."""
    data = {k: v for k, v in payload.items() if v is not None or k in ("payment_note",)}
    if not data:
        return get_batch(batch_id)

    with get_conn() as conn:
        batch = conn.execute(
            "SELECT * FROM outbound_batches WHERE id = ?", (batch_id,)
        ).fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="outbound batch not found")

        freight_rate = (
            float(data["freight_exchange_rate"])
            if "freight_exchange_rate" in data
            else _as_float(batch["freight_exchange_rate"])
        )
        freight_unit = (
            float(data["freight_unit_price_jpy"])
            if "freight_unit_price_jpy" in data
            else _as_float(batch["freight_unit_price_jpy"])
        )
        freight_weight = (
            float(data["chargeable_weight"])
            if "chargeable_weight" in data
            else _as_float(batch["chargeable_weight"])
        )
        if freight_rate is not None and freight_rate <= 0:
            raise HTTPException(
                status_code=400, detail="freight_exchange_rate must be > 0"
            )
        for label, value in (
            ("freight_unit_price_jpy", freight_unit),
            ("chargeable_weight", freight_weight),
        ):
            if value is not None and value < 0:
                raise HTTPException(status_code=400, detail=f"{label} invalid")

        freight_cny = _compute_freight_cny(freight_unit, freight_weight, freight_rate)
        goods_cny = _as_float(batch["goods_receivable_cny"])
        received = (
            float(data["amount_received_cny"])
            if "amount_received_cny" in data
            else (_as_float(batch["amount_received_cny"]) or 0.0)
        )
        if received < 0:
            raise HTTPException(status_code=400, detail="amount_received_cny invalid")
        receivable, pay_status, _ = _recompute_batch_totals(
            goods_cny, freight_cny, received
        )
        payment_note = (
            str(data["payment_note"]).strip()
            if "payment_note" in data
            else (batch["payment_note"] or "")
        )

        conn.execute(
            """
            UPDATE outbound_batches SET
                freight_exchange_rate = ?,
                freight_unit_price_jpy = ?,
                chargeable_weight = ?,
                freight_cny = ?,
                amount_receivable_cny = ?,
                amount_received_cny = ?,
                payment_status = ?,
                payment_note = ?
            WHERE id = ?
            """,
            (
                freight_rate,
                freight_unit,
                freight_weight,
                freight_cny,
                receivable,
                received,
                pay_status,
                payment_note,
                batch_id,
            ),
        )
        action_log.record(
            conn,
            "update_outbound_finance",
            f"更新出库批次 #{batch_id} 财务（{pay_status}）",
            {
                "batch_id": batch_id,
                "before": {
                    "freight_exchange_rate": batch["freight_exchange_rate"],
                    "freight_unit_price_jpy": batch["freight_unit_price_jpy"],
                    "chargeable_weight": batch["chargeable_weight"],
                    "freight_cny": batch["freight_cny"],
                    "amount_receivable_cny": batch["amount_receivable_cny"],
                    "amount_received_cny": batch["amount_received_cny"],
                    "payment_status": batch["payment_status"],
                    "payment_note": batch["payment_note"],
                },
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


def export_fee_detail_xlsx(batch_id: int) -> bytes:
    """Export 发货费用明细 Excel for a batch (订单号 between 箱号 and 品名)."""
    with get_conn() as conn:
        batch = _batch_out(conn, batch_id)
        lines: list[dict[str, Any]] = []
        for box in batch["boxes"]:
            for item in box["items"]:
                item_row = conn.execute(
                    """
                    SELECT i.id, i.name, i.barcode, i.qty, i.unit_cost,
                           i.order_ref, o.order_ref AS order_order_ref,
                           o.exchange_rate
                    FROM items i
                    JOIN orders o ON o.id = i.order_id
                    WHERE i.id = ?
                    """,
                    (item["id"],),
                ).fetchone()
                if not item_row:
                    continue
                unit = _as_float(item_row["unit_cost"])
                qty = int(item_row["qty"])
                amount_jpy = round(unit * qty, 2) if unit is not None else None
                rate = _as_float(item_row["exchange_rate"])
                if rate is not None and rate <= 0:
                    rate = None
                amount_cny = (
                    round(amount_jpy * rate, 2)
                    if amount_jpy is not None and rate is not None
                    else None
                )
                order_ref = (
                    (item_row["order_order_ref"] or item_row["order_ref"] or "").strip()
                    or f"#{item.get('order_id') or ''}"
                )
                lines.append(
                    {
                        "box_no": box["box_no"],
                        "order_ref": order_ref,
                        "name": item_row["name"],
                        "barcode": item_row["barcode"] or "",
                        "qty": qty,
                        "amount_jpy": amount_jpy,
                        "exchange_rate": rate,
                        "amount_cny": amount_cny,
                    }
                )

    wb = Workbook()
    ws = wb.active
    ws.title = "发货费用明细"
    thin = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )
    header_font = Font(bold=True)
    headers = [
        "单号",
        "箱号",
        "订单号",
        "品名",
        "条形码",
        "数量",
        "合计JPY",
        "下单汇率",
        "合计CNY",
        "净重",
        "毛重",
        "体积",
    ]
    for c, h in enumerate(headers, 1):
        cell = ws.cell(1, c, h)
        cell.font = header_font
        cell.border = thin

    invoice_no = f"OB-{batch_id}"
    for i, line in enumerate(lines, start=1):
        r = i + 1
        values = [
            invoice_no if i == 1 else None,
            line["box_no"],
            line["order_ref"],
            line["name"],
            line["barcode"],
            line["qty"],
            line["amount_jpy"],
            line["exchange_rate"],
            line["amount_cny"],
            None,
            None,
            None,
        ]
        for c, v in enumerate(values, 1):
            cell = ws.cell(r, c, v)
            cell.border = thin
            cell.alignment = Alignment(wrap_text=True, vertical="center")

    last_data_row = 1 + len(lines)
    if len(lines) > 1:
        ws.merge_cells(start_row=2, start_column=1, end_row=last_data_row, end_column=1)
        ws.cell(2, 1).alignment = Alignment(vertical="center", wrap_text=True)

    total_row = last_data_row + 1
    total_qty = sum(int(x["qty"]) for x in lines)
    total_jpy = sum(float(x["amount_jpy"] or 0) for x in lines)
    total_cny = sum(float(x["amount_cny"] or 0) for x in lines)
    ws.cell(total_row, 6, total_qty).border = thin
    ws.cell(total_row, 7, round(total_jpy, 2)).border = thin
    ws.cell(total_row, 9, round(total_cny, 2) if any(x["amount_cny"] is not None for x in lines) else None).border = thin
    ws.cell(total_row, 6).font = header_font
    ws.cell(total_row, 7).font = header_font
    ws.cell(total_row, 9).font = header_font

    rates = {x["exchange_rate"] for x in lines if x["exchange_rate"] is not None}
    goods_rate_summary: Any
    if len(rates) == 1:
        goods_rate_summary = next(iter(rates))
    elif len(rates) > 1:
        goods_rate_summary = "分订单见各行"
    else:
        goods_rate_summary = None

    summary_rows = [
        ("商品汇率", goods_rate_summary),
        ("运费汇率", batch.get("freight_exchange_rate")),
        ("计费重量", batch.get("chargeable_weight")),
        ("运费单价（JPY）", batch.get("freight_unit_price_jpy")),
        ("需支付运费（CNY）", batch.get("freight_cny")),
        ("需支付货款（CNY）", batch.get("goods_receivable_cny")),
        ("总支付金额（CNY）", batch.get("amount_receivable_cny")),
    ]
    for i, (label, value) in enumerate(summary_rows):
        r = total_row + 1 + i
        ws.cell(r, 6, label)
        ws.cell(r, 7, value)

    for c, w in enumerate([14, 8, 16, 28, 16, 8, 12, 10, 12, 8, 8, 12], 1):
        ws.column_dimensions[get_column_letter(c)].width = w

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
