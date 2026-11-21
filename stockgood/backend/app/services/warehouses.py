"""Warehouse list and create. Data isolation is applied by warehouse_scope."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.database import get_conn


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def list_warehouses() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, created_at FROM warehouses ORDER BY id"
        ).fetchall()
    return [
        {"id": int(row["id"]), "name": row["name"], "created_at": row["created_at"]}
        for row in rows
    ]


def create_warehouse(name: str) -> dict[str, Any]:
    cleaned = (name or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="仓库名称不能为空")
    if len(cleaned) > 40:
        raise HTTPException(status_code=400, detail="仓库名称请控制在 40 字以内")
    with get_conn() as conn:
        taken = conn.execute(
            "SELECT id FROM warehouses WHERE name = ?", (cleaned,)
        ).fetchone()
        if taken:
            raise HTTPException(status_code=409, detail="已有同名仓库")
        cur = conn.execute(
            "INSERT INTO warehouses (name, created_at) VALUES (?, ?)",
            (cleaned, _now()),
        )
        row = conn.execute(
            "SELECT id, name, created_at FROM warehouses WHERE id = ?",
            (int(cur.lastrowid),),
        ).fetchone()
    return {"id": int(row["id"]), "name": row["name"], "created_at": row["created_at"]}
