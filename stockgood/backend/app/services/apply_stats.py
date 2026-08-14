"""Customer apply / order-request analytics for staff reports."""

# ============================================================
# FEATURE: APPLY_STATS
#
# [接口] GET /api/reports/apply
# [数据库] order_requests（按创建时间）
# [代码索引] docs/CODE_INDEX.md#feature-apply_stats
# ============================================================

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from fastapi import HTTPException

from app.database import get_conn

_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

Period = Literal["day", "month"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _period_bounds(
    period: Period, day: Optional[str], month: Optional[str]
) -> tuple[str, str, str]:
    """Return (label, start_iso_prefix_or_start, end_exclusive_iso) filter style."""
    if period == "day":
        if day and str(day).strip():
            text = str(day).strip()
            if not _DAY_RE.match(text):
                raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")
            label = text
        else:
            label = _utcnow().strftime("%Y-%m-%d")
        start = f"{label}T00:00:00+00:00"
        end_dt = datetime.fromisoformat(label).replace(tzinfo=timezone.utc) + timedelta(
            days=1
        )
        end = end_dt.replace(microsecond=0).isoformat()
        return label, start, end

    if month and str(month).strip():
        text = str(month).strip()
        if not _MONTH_RE.match(text):
            raise HTTPException(status_code=400, detail="month must be YYYY-MM")
        label = text
    else:
        label = _utcnow().strftime("%Y-%m")
    y, m = map(int, label.split("-"))
    start = f"{label}-01T00:00:00+00:00"
    if m == 12:
        end_dt = datetime(y + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end_dt = datetime(y, m + 1, 1, tzinfo=timezone.utc)
    end = end_dt.replace(microsecond=0).isoformat()
    return label, start, end


def _goods_amount(unit_cost: Any, qty: Any) -> float:
    if unit_cost is None:
        return 0.0
    try:
        return float(unit_cost) * max(1, int(qty or 1))
    except (TypeError, ValueError):
        return 0.0


def apply_summary(
    *,
    period: Period = "month",
    day: Optional[str] = None,
    month: Optional[str] = None,
    limit: int = 10,
) -> dict[str, Any]:
    """日/月申请单统计：单量、热门链接、花费用户、商品 IP。"""
    if period not in ("day", "month"):
        raise HTTPException(status_code=400, detail="period must be day or month")
    limit = max(1, min(int(limit or 10), 50))
    label, start, end = _period_bounds(period, day, month)

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                r.request_code, r.status, r.name, r.shop, r.unit_cost, r.qty,
                r.source_url, r.ip, r.user_id, r.created_at, r.deposit_amount,
                u.email AS user_email, u.display_name AS user_display_name
            FROM order_requests r
            LEFT JOIN users u ON u.id = r.user_id
            WHERE r.created_at >= ? AND r.created_at < ?
            ORDER BY r.id ASC
            """,
            (start, end),
        ).fetchall()

    by_status: dict[str, int] = {}
    total_goods = 0.0
    total_deposit = 0.0
    link_map: dict[str, dict[str, Any]] = {}
    user_map: dict[str, dict[str, Any]] = {}
    ip_map: dict[str, dict[str, Any]] = {}

    for row in rows:
        status = row["status"] or "unknown"
        by_status[status] = by_status.get(status, 0) + 1
        goods = _goods_amount(row["unit_cost"], row["qty"])
        total_goods += goods
        if row["deposit_amount"] is not None:
            try:
                total_deposit += float(row["deposit_amount"])
            except (TypeError, ValueError):
                pass

        url = (row["source_url"] or "").strip() or "(无链接)"
        link = link_map.setdefault(
            url, {"source_url": url, "count": 0, "goods_jpy": 0.0, "name": row["name"] or ""}
        )
        link["count"] += 1
        link["goods_jpy"] += goods
        if not link["name"] and row["name"]:
            link["name"] = row["name"]

        uid = row["user_id"]
        ukey = str(uid) if uid is not None else "anonymous"
        user = user_map.setdefault(
            ukey,
            {
                "user_id": uid,
                "email": row["user_email"] or "",
                "display_name": row["user_display_name"] or "",
                "count": 0,
                "goods_jpy": 0.0,
            },
        )
        user["count"] += 1
        user["goods_jpy"] += goods

        ip = (row["ip"] or "").strip() or "(未标注)"
        ip_row = ip_map.setdefault(
            ip, {"ip": ip, "count": 0, "goods_jpy": 0.0}
        )
        ip_row["count"] += 1
        ip_row["goods_jpy"] += goods

    def _top(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        ranked = sorted(items, key=lambda x: (x.get(key) or 0, x.get("count") or 0), reverse=True)
        out = []
        for item in ranked[:limit]:
            copy = dict(item)
            if "goods_jpy" in copy:
                copy["goods_jpy"] = round(float(copy["goods_jpy"]), 2)
            out.append(copy)
        return out

    return {
        "period": period,
        "label": label,
        "start": start,
        "end": end,
        "order_count": len(rows),
        "by_status": by_status,
        "goods_jpy": round(total_goods, 2),
        "deposit_jpy": round(total_deposit, 2),
        "top_links": _top(list(link_map.values()), "count"),
        "top_users": _top(list(user_map.values()), "goods_jpy"),
        "top_ips": _top(list(ip_map.values()), "goods_jpy"),
    }
