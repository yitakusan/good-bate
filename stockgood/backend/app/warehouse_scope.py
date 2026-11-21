"""Current warehouse for one request.

Unset means no filter, so existing unit tests keep seeing the whole temp database.
Staff API sets this from X-Warehouse-Id, or the first warehouse when the header is absent.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator, Optional

from fastapi import HTTPException

_current: ContextVar[Optional[int]] = ContextVar("stockgood_warehouse_id", default=None)


def current_warehouse_id() -> Optional[int]:
    return _current.get()


def set_current_warehouse_id(warehouse_id: Optional[int]) -> Token:
    return _current.set(warehouse_id)


def reset_current_warehouse_id(token: Token) -> None:
    _current.reset(token)


@contextmanager
def use_warehouse(warehouse_id: Optional[int]) -> Iterator[None]:
    token = set_current_warehouse_id(warehouse_id)
    try:
        yield
    finally:
        reset_current_warehouse_id(token)


def warehouse_and(column: str) -> tuple[str, list]:
    warehouse_id = current_warehouse_id()
    if warehouse_id is None:
        return "", []
    return f" AND {column} = ?", [int(warehouse_id)]


def stamp_warehouse_id(conn) -> int:
    warehouse_id = current_warehouse_id()
    if warehouse_id is not None:
        return int(warehouse_id)
    row = conn.execute("SELECT MIN(id) AS id FROM warehouses").fetchone()
    if row and row["id"] is not None:
        return int(row["id"])
    return 1


def ensure_visible(row, detail: str = "not found") -> None:
    if row is None:
        raise HTTPException(status_code=404, detail=detail)
    warehouse_id = current_warehouse_id()
    if warehouse_id is None:
        return
    keys = row.keys() if hasattr(row, "keys") else []
    if "warehouse_id" not in keys or row["warehouse_id"] is None:
        return
    if int(row["warehouse_id"]) != int(warehouse_id):
        raise HTTPException(status_code=404, detail=detail)


def shipment_scope_sql(alias: str = "") -> tuple[str, list]:
    warehouse_id = current_warehouse_id()
    if warehouse_id is None:
        return "", []
    prefix = f"{alias}." if alias else ""
    sql = (
        f"(({prefix}order_id IS NOT NULL AND {prefix}order_id IN "
        "(SELECT id FROM orders WHERE warehouse_id = ?))"
        f" OR ({prefix}batch_id IS NOT NULL AND {prefix}batch_id IN "
        "(SELECT id FROM outbound_batches WHERE warehouse_id = ?)))"
    )
    return sql, [int(warehouse_id), int(warehouse_id)]
