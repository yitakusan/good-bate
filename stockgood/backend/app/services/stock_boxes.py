from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.database import get_conn

# ============================================================
# FEATURE: INVENTORY
#
# [用途] 在库合箱（不改货品状态）
# [接口] /api/stock-boxes*
# [数据库] stock_boxes, stock_box_orders
# [代码索引] docs/CODE_INDEX.md#feature-inventory
# ============================================================


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _order_in_stock_lines(conn, order_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, order_id, name, shop, order_ref, qty, status, image_url,
               barcode, ip, product_kind, note, source_url
        FROM items
        WHERE order_id = ? AND status = 'in_stock'
        ORDER BY id
        """,
        (order_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _box_counts(conn, box_id: int) -> tuple[int, int]:
    row = conn.execute(
        """
        SELECT
            COUNT(DISTINCT sbo.order_id) AS order_count,
            COALESCE(SUM(
                (SELECT COUNT(*) FROM items i
                 WHERE i.order_id = sbo.order_id AND i.status = 'in_stock')
            ), 0) AS item_count
        FROM stock_box_orders sbo
        WHERE sbo.box_id = ?
        """,
        (box_id,),
    ).fetchone()
    return int(row["order_count"] or 0), int(row["item_count"] or 0)


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

    parent_id = box["parent_id"]
    parent_box_no = None
    if parent_id is not None:
        parent = conn.execute(
            "SELECT box_no FROM stock_boxes WHERE id = ?", (int(parent_id),)
        ).fetchone()
        if parent:
            parent_box_no = int(parent["box_no"])
        else:
            parent_id = None

    children_rows = conn.execute(
        """
        SELECT id, box_no, note FROM stock_boxes
        WHERE parent_id = ?
        ORDER BY box_no, id
        """,
        (box_id,),
    ).fetchall()
    child_boxes: list[dict[str, Any]] = []
    for child in children_rows:
        oc, ic = _box_counts(conn, int(child["id"]))
        child_boxes.append(
            {
                "id": int(child["id"]),
                "box_no": int(child["box_no"]),
                "note": child["note"] or "",
                "order_count": oc,
                "item_count": ic,
            }
        )

    return {
        "id": box["id"],
        "box_no": box["box_no"],
        "note": box["note"] or "",
        "created_at": box["created_at"],
        "parent_id": int(parent_id) if parent_id is not None else None,
        "parent_box_no": parent_box_no,
        "child_boxes": child_boxes,
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
        # Detach children so they become independent main boxes
        conn.execute(
            "UPDATE stock_boxes SET parent_id = NULL WHERE parent_id = ?",
            (box_id,),
        )
        conn.execute("DELETE FROM stock_boxes WHERE id = ?", (box_id,))


def merge_child(parent_id: int, child_id: int) -> dict[str, Any]:
    """Attach box B as a sub-box under main box A. Orders stay in B."""
    if int(parent_id) == int(child_id):
        raise HTTPException(status_code=400, detail="主箱与子箱不能是同一箱")

    with get_conn() as conn:
        parent = conn.execute(
            "SELECT id, box_no, parent_id FROM stock_boxes WHERE id = ?",
            (parent_id,),
        ).fetchone()
        if not parent:
            raise HTTPException(status_code=404, detail="主箱不存在")
        child = conn.execute(
            "SELECT id, box_no, parent_id FROM stock_boxes WHERE id = ?",
            (child_id,),
        ).fetchone()
        if not child:
            raise HTTPException(status_code=404, detail="子箱不存在")

        if parent["parent_id"] is not None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"箱 #{parent['box_no']} 已是子箱，不能再作为主箱。"
                    "请选择无上级的主箱。"
                ),
            )

        # One level only: child must not already have its own children
        has_kids = conn.execute(
            "SELECT id FROM stock_boxes WHERE parent_id = ? LIMIT 1",
            (child_id,),
        ).fetchone()
        if has_kids:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"箱 #{child['box_no']} 下还有子箱，请先拆开后再并入主箱"
                ),
            )

        # Prevent cycle if somehow deeper links exist later
        walk_id: int | None = int(parent_id)
        seen: set[int] = set()
        while walk_id is not None:
            if walk_id == int(child_id):
                raise HTTPException(
                    status_code=400, detail="不能将上级箱并入其下级"
                )
            if walk_id in seen:
                break
            seen.add(walk_id)
            row = conn.execute(
                "SELECT parent_id FROM stock_boxes WHERE id = ?", (walk_id,)
            ).fetchone()
            walk_id = int(row["parent_id"]) if row and row["parent_id"] else None

        conn.execute(
            "UPDATE stock_boxes SET parent_id = ? WHERE id = ?",
            (parent_id, child_id),
        )
        return _box_out(conn, parent_id)


def detach_child(child_id: int) -> dict[str, Any]:
    """Detach sub-box B from its main box; B becomes an independent box."""
    with get_conn() as conn:
        child = conn.execute(
            "SELECT id, box_no, parent_id FROM stock_boxes WHERE id = ?",
            (child_id,),
        ).fetchone()
        if not child:
            raise HTTPException(status_code=404, detail="库存箱不存在")
        if child["parent_id"] is None:
            raise HTTPException(
                status_code=400,
                detail=f"箱 #{child['box_no']} 不是子箱，无需拆出",
            )
        conn.execute(
            "UPDATE stock_boxes SET parent_id = NULL WHERE id = ?",
            (child_id,),
        )
        return _box_out(conn, child_id)


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

        note_text = (note or "").strip()
        if box_ids:
            target_id = min(box_ids)
        else:
            use_no = _next_box_no(conn)
            cur = conn.execute(
                """
                INSERT INTO stock_boxes (box_no, note, created_at)
                VALUES (?, ?, ?)
                """,
                (use_no, note_text, _now()),
            )
            target_id = int(cur.lastrowid)

        # Always persist note on combine (UI saves draft together with 合箱)
        conn.execute(
            "UPDATE stock_boxes SET note = ? WHERE id = ?",
            (note_text, target_id),
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
        SELECT sbo.order_id, sb.id AS box_id, sb.box_no, sb.parent_id,
               parent.box_no AS parent_box_no
        FROM stock_box_orders sbo
        JOIN stock_boxes sb ON sb.id = sbo.box_id
        LEFT JOIN stock_boxes parent ON parent.id = sb.parent_id
        """
    ).fetchall()
    return {
        int(r["order_id"]): {
            "stock_box_id": int(r["box_id"]),
            "stock_box_no": int(r["box_no"]),
            "parent_box_id": int(r["parent_id"]) if r["parent_id"] is not None else None,
            "parent_box_no": int(r["parent_box_no"])
            if r["parent_box_no"] is not None
            else None,
        }
        for r in rows
    }
