from __future__ import annotations

import re
from typing import Any, Optional

from fastapi import HTTPException

from app.database import get_conn


_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _normalize_month(month: Optional[str]) -> str:
    from datetime import datetime, timezone

    if not month or not str(month).strip():
        return datetime.now(timezone.utc).strftime("%Y-%m")
    text = str(month).strip()
    if not _MONTH_RE.match(text):
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    return text


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def month_summary(month: Optional[str] = None) -> dict[str, Any]:
    """本月下单金额（ordered_at）+ 本月出库应收/已收（batch.created_at）。"""
    month_key = _normalize_month(month)
    prefix = f"{month_key}%"

    with get_conn() as conn:
        orders = conn.execute(
            """
            SELECT id, shipping_fee, exchange_rate
            FROM orders
            WHERE ordered_at LIKE ?
              AND status != 'cancelled'
            """,
            (prefix,),
        ).fetchall()

        goods_jpy = 0.0
        shipping_jpy = 0.0
        goods_cny_sum = 0.0
        shipping_cny_sum = 0.0
        has_any_cny = False
        missing_rate = 0

        for order in orders:
            oid = int(order["id"])
            rate = _as_float(order["exchange_rate"])
            if rate is not None and rate <= 0:
                rate = None
            ship = _as_float(order["shipping_fee"]) or 0.0
            shipping_jpy += ship

            line_rows = conn.execute(
                """
                SELECT unit_cost, qty FROM items
                WHERE order_id = ? AND status != 'cancelled'
                """,
                (oid,),
            ).fetchall()
            order_goods = 0.0
            priced = False
            for line in line_rows:
                if line["unit_cost"] is None:
                    continue
                priced = True
                order_goods += float(line["unit_cost"]) * int(line["qty"])
            if priced:
                goods_jpy += order_goods

            if rate is None:
                missing_rate += 1
            else:
                has_any_cny = True
                if priced:
                    goods_cny_sum += order_goods * rate
                shipping_cny_sum += ship * rate

        batches = conn.execute(
            """
            SELECT
                goods_jpy, goods_receivable_cny, freight_cny,
                amount_receivable_cny, amount_received_cny
            FROM outbound_batches
            WHERE created_at LIKE ?
            """,
            (prefix,),
        ).fetchall()

        out_goods_jpy = 0.0
        out_goods_cny = 0.0
        out_freight_cny = 0.0
        out_receivable = 0.0
        out_received = 0.0
        has_goods_cny = False
        has_freight = False
        has_receivable = False

        for batch in batches:
            gj = _as_float(batch["goods_jpy"])
            if gj is not None:
                out_goods_jpy += gj
            gc = _as_float(batch["goods_receivable_cny"])
            if gc is not None:
                has_goods_cny = True
                out_goods_cny += gc
            fc = _as_float(batch["freight_cny"])
            if fc is not None:
                has_freight = True
                out_freight_cny += fc
            ar = _as_float(batch["amount_receivable_cny"])
            if ar is not None:
                has_receivable = True
                out_receivable += ar
            out_received += _as_float(batch["amount_received_cny"]) or 0.0

    ordered_total_jpy = round(goods_jpy + shipping_jpy, 2)
    return {
        "month": month_key,
        "ordered": {
            "goods_jpy": round(goods_jpy, 2),
            "shipping_jpy": round(shipping_jpy, 2),
            "total_jpy": ordered_total_jpy,
            "goods_cny": round(goods_cny_sum, 2) if has_any_cny else None,
            "shipping_cny": round(shipping_cny_sum, 2) if has_any_cny else None,
            "total_cny": (
                round(goods_cny_sum + shipping_cny_sum, 2) if has_any_cny else None
            ),
            "order_count": len(orders),
            "missing_rate_count": missing_rate,
        },
        "outbound": {
            "goods_jpy": round(out_goods_jpy, 2),
            "goods_receivable_cny": round(out_goods_cny, 2) if has_goods_cny else None,
            "freight_cny": round(out_freight_cny, 2) if has_freight else None,
            "amount_receivable_cny": (
                round(out_receivable, 2) if has_receivable else None
            ),
            "amount_received_cny": round(out_received, 2),
            "amount_unreceived_cny": (
                round(out_receivable - out_received, 2) if has_receivable else None
            ),
            "batch_count": len(batches),
        },
    }
