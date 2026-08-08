from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.database import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _order_in_stock_lines(conn, order_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, order_id, name, shop, order_ref, qty, status, image_url, barcode
        FROM items
        WHERE order_id = ? AND status = 'in_stock'
        ORDER BY id
        """,
        (order_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _box_out(conn, box_id: int) -> dict[str, Any]:
    box = conn.execute(
        "SELECT * FROM stock_boxes WHERE id = ?", (box_id,)
    ).fetchone()
    if not box:
        raise HTTPException(status_code=404, detail="stock box not found")
    members = conn.execute(
        """
        SELECT o.id, o.order_ref, o.shop, o.status
        FROM stock_box_orders sbo
        JOIN orders o ON o.id = sbo.order_id
        WHERE sbo.box_id = ?
        ORDER BY o.id
        """,
        (box_id,),
    ).fetchall()
    orders: list[dict[str, Any]] = []
    for m in members:
        lines = _order_in_stock_lines(conn, int(m["id"]))
        orders.append(
            {
                "id": m["id"],
                "order_ref": m["order_ref"] or "",
                "shop": m["shop"] or "",
                "status": m["status"],
                "line_count": len(lines),
                "total_qty": sum(int(line["qty"]) for line in lines),
                "lines": lines,
            }
        )
    return {
        "id": box["id"],
        "box_no": box["box_no"],
        "note": box["note"] or "",
        "created_at": box["created_at"],
        "order_ids": [o["id"] for o in orders],
        "order_count": len(orders),
        "item_count": sum(o["line_count"] for o in orders),
        "orders": orders,
    }


def list_boxes() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id FROM stock_boxes ORDER BY box_no, id"
        ).fetchall()
        return [_box_out(conn, int(r["id"])) for r in rows]


def get_box(box_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        return _box_out(conn, box_id)


def _next_box_no(conn) -> int:
    row = conn.execute("SELECT COALESCE(MAX(box_no), 0) AS n FROM stock_boxes").fetchone()
    return int(row["n"]) + 1


def _validate_order_ids(conn, order_ids: list[int]) -> list[int]:
    unique: list[int] = []
    seen: set[int] = set()
    for oid in order_ids:
        oid = int(oid)
        if oid in seen:
            continue
        seen.add(oid)
        unique.append(oid)
    if not unique:
        raise HTTPException(status_code=400, detail="order_ids required")

    for oid in unique:
        order = conn.execute(
            "SELECT id, order_ref FROM orders WHERE id = ?", (oid,)
        ).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail=f"order not found: {oid}")
        stock = conn.execute(
            """
            SELECT COUNT(*) AS c FROM items
            WHERE order_id = ? AND status = 'in_stock'
            """,
            (oid,),
        ).fetchone()
        if not stock or int(stock["c"]) < 1:
            label = (order["order_ref"] or "").strip() or f"#{oid}"
            raise HTTPException(
                status_code=400,
                detail=f"订单 {label} 没有在库明细，不能合箱",
            )
    return unique


def _assert_orders_free(conn, order_ids: list[int], *, allow_box_id: int | None = None) -> None:
    for oid in order_ids:
        row = conn.execute(
            "SELECT box_id FROM stock_box_orders WHERE order_id = ?",
            (oid,),
        ).fetchone()
        if row and (allow_box_id is None or int(row["box_id"]) != allow_box_id):
            raise HTTPException(
                status_code=400,
                detail=f"订单 #{oid} 已在库存箱 #{row['box_id']} 中",
            )


def create_box(
    order_ids: list[int],
    note: str = "",
    box_no: int | None = None,
) -> dict[str, Any]:
    with get_conn() as conn:
        ids = _validate_order_ids(conn, order_ids)
        _assert_orders_free(conn, ids)
        next_no = _next_box_no(conn)
        use_no = int(box_no) if box_no is not None else next_no
        if use_no < 1:
            raise HTTPException(status_code=400, detail="box_no invalid")
        exists = conn.execute(
            "SELECT id FROM stock_boxes WHERE box_no = ?", (use_no,)
        ).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail=f"库存箱号已存在: {use_no}")
        cur = conn.execute(
            """
            INSERT INTO stock_boxes (box_no, note, created_at)
            VALUES (?, ?, ?)
            """,
            (use_no, (note or "").strip(), _now()),
        )
        box_id = int(cur.lastrowid)
        for oid in ids:
            conn.execute(
                "INSERT INTO stock_box_orders (box_id, order_id) VALUES (?, ?)",
                (box_id, oid),
            )
        return _box_out(conn, box_id)


def add_orders(box_id: int, order_ids: list[int]) -> dict[str, Any]:
    with get_conn() as conn:
        box = conn.execute(
            "SELECT id FROM stock_boxes WHERE id = ?", (box_id,)
        ).fetchone()
        if not box:
            raise HTTPException(status_code=404, detail="stock box not found")
        ids = _validate_order_ids(conn, order_ids)
        _assert_orders_free(conn, ids, allow_box_id=box_id)
        for oid in ids:
            exists = conn.execute(
                "SELECT 1 FROM stock_box_orders WHERE box_id = ? AND order_id = ?",
                (box_id, oid),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                "INSERT INTO stock_box_orders (box_id, order_id) VALUES (?, ?)",
                (box_id, oid),
            )
        return _box_out(conn, box_id)


def remove_orders(box_id: int, order_ids: list[int]) -> dict[str, Any] | None:
    """Remove orders from box. Deletes empty box and returns None."""
    with get_conn() as conn:
        box = conn.execute(
            "SELECT id FROM stock_boxes WHERE id = ?", (box_id,)
        ).fetchone()
        if not box:
            raise HTTPException(status_code=404, detail="stock box not found")
        for oid in order_ids:
            conn.execute(
                "DELETE FROM stock_box_orders WHERE box_id = ? AND order_id = ?",
                (box_id, int(oid)),
            )
        left = conn.execute(
            "SELECT COUNT(*) AS c FROM stock_box_orders WHERE box_id = ?",
            (box_id,),
        ).fetchone()
        if not left or int(left["c"]) == 0:
            conn.execute("DELETE FROM stock_boxes WHERE id = ?", (box_id,))
            return None
        return _box_out(conn, box_id)


def update_box(
    box_id: int,
    *,
    note: str | None = None,
    box_no: int | None = None,
) -> dict[str, Any]:
    with get_conn() as conn:
        box = conn.execute(
            "SELECT id FROM stock_boxes WHERE id = ?", (box_id,)
        ).fetchone()
        if not box:
            raise HTTPException(status_code=404, detail="stock box not found")
        if box_no is not None:
            use_no = int(box_no)
            if use_no < 1:
                raise HTTPException(status_code=400, detail="box_no invalid")
            clash = conn.execute(
                "SELECT id FROM stock_boxes WHERE box_no = ? AND id != ?",
                (use_no, box_id),
            ).fetchone()
            if clash:
                raise HTTPException(status_code=409, detail=f"库存箱号已存在: {use_no}")
            conn.execute(
                "UPDATE stock_boxes SET box_no = ? WHERE id = ?",
                (use_no, box_id),
            )
        if note is not None:
            conn.execute(
                "UPDATE stock_boxes SET note = ? WHERE id = ?",
                (note.strip(), box_id),
            )
        return _box_out(conn, box_id)


def delete_box(box_id: int) -> None:
    with get_conn() as conn:
        box = conn.execute(
            "SELECT id FROM stock_boxes WHERE id = ?", (box_id,)
        ).fetchone()
        if not box:
            raise HTTPException(status_code=404, detail="stock box not found")
        conn.execute("DELETE FROM stock_boxes WHERE id = ?", (box_id,))


def combine_orders(order_ids: list[int], note: str = "") -> dict[str, Any]:
    """
    Put selected in-stock orders into one stock box.
    Reuses an existing box when any selected order already belongs to one;
    otherwise creates a new box. Moves members out of other boxes as needed.
    """
    with get_conn() as conn:
        ids = _validate_order_ids(conn, order_ids)
        box_ids: list[int] = []
        for oid in ids:
            row = conn.execute(
                "SELECT box_id FROM stock_box_orders WHERE order_id = ?",
                (oid,),
            ).fetchone()
            if row:
                bid = int(row["box_id"])
                if bid not in box_ids:
                    box_ids.append(bid)

        if box_ids:
            target_id = min(box_ids)
        else:
            use_no = _next_box_no(conn)
            cur = conn.execute(
                """
                INSERT INTO stock_boxes (box_no, note, created_at)
                VALUES (?, ?, ?)
                """,
                (use_no, (note or "").strip(), _now()),
            )
            target_id = int(cur.lastrowid)

        if note.strip():
            conn.execute(
                "UPDATE stock_boxes SET note = ? WHERE id = ?",
                (note.strip(), target_id),
            )

        for oid in ids:
            conn.execute(
                "DELETE FROM stock_box_orders WHERE order_id = ?", (oid,)
            )
            conn.execute(
                "INSERT INTO stock_box_orders (box_id, order_id) VALUES (?, ?)",
                (target_id, oid),
            )

        for bid in box_ids:
            if bid == target_id:
                continue
            left = conn.execute(
                "SELECT COUNT(*) AS c FROM stock_box_orders WHERE box_id = ?",
                (bid,),
            ).fetchone()
            if not left or int(left["c"]) == 0:
                conn.execute("DELETE FROM stock_boxes WHERE id = ?", (bid,))

        return _box_out(conn, target_id)


def release_orders(conn, order_ids: set[int] | list[int]) -> None:
    """Drop orders from stock boxes after outbound; prune empty boxes."""
    ids = [int(oid) for oid in order_ids]
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    box_rows = conn.execute(
        f"""
        SELECT DISTINCT box_id FROM stock_box_orders
        WHERE order_id IN ({placeholders})
        """,
        ids,
    ).fetchall()
    conn.execute(
        f"DELETE FROM stock_box_orders WHERE order_id IN ({placeholders})",
        ids,
    )
    for row in box_rows:
        bid = int(row["box_id"])
        left = conn.execute(
            "SELECT COUNT(*) AS c FROM stock_box_orders WHERE box_id = ?",
            (bid,),
        ).fetchone()
        if not left or int(left["c"]) == 0:
            conn.execute("DELETE FROM stock_boxes WHERE id = ?", (bid,))


def order_box_map(conn) -> dict[int, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT sbo.order_id, sb.id AS box_id, sb.box_no
        FROM stock_box_orders sbo
        JOIN stock_boxes sb ON sb.id = sbo.box_id
        """
    ).fetchall()
    return {
        int(r["order_id"]): {"stock_box_id": int(r["box_id"]), "stock_box_no": int(r["box_no"])}
        for r in rows
    }
