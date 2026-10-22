"""Fill SF Express declaration Excel from the fixed single-sheet template."""

from __future__ import annotations

from copy import copy
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException
from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.database import DATA_DIR

# ============================================================
# FEATURE: SF_EXPORT
#
# [用途] 填充顺丰申报单列模板
#       表头「运单号*」在本系统填发货箱号（FIT{批次}-{箱号}），不是快递单号
# [模板] backend/data/templates/sf_export.xlsx（只读；表头来自业务样表）
# [调用] outbound_batches.export_sf_xlsx / export_sf_preview_xlsx
# [代码索引] docs/CODE_INDEX.md#feature-sf_export
# ============================================================

TEMPLATE_PATH = DATA_DIR / "templates" / "sf_export.xlsx"
SF_SHEET = "Sheet1"

# 与 INV 收件人一致（样表：张超 / 天津武清腾越云仓；省栏可空）
CONSIGNEE = {
    "name": "张超",
    "phone": 15033057065,
    "country": "中国",
    "postcode": 301702,
    "province": "",
    "city": "天津市",
    "district": "武清区",
    "address": "崔黄口镇开发区宏发道8号腾越云仓",
}

ORIGIN = "日本"
SPEC = "个"


def _copy_row_style(ws: Worksheet, src_row: int, dst_row: int, max_col: int) -> None:
    for col in range(1, max_col + 1):
        src = ws.cell(src_row, col)
        dst = ws.cell(dst_row, col)
        if src.has_style:
            dst.font = copy(src.font)
            dst.border = copy(src.border)
            dst.fill = copy(src.fill)
            dst.number_format = src.number_format
            dst.protection = copy(src.protection)
            dst.alignment = copy(src.alignment)
    if src_row in ws.row_dimensions:
        ws.row_dimensions[dst_row].height = ws.row_dimensions[src_row].height


def parse_ship_date(value: Optional[str]) -> date:
    raw = (value or "").strip()
    if not raw:
        return date.today()
    cleaned = raw[:10].replace("/", "-")
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").date()
    except ValueError:
        return date.today()


def format_filename(ship_date: date, batch_id: int, total_qty: int) -> str:
    return (
        f"SF_{ship_date.year:04d}{ship_date.month:02d}{ship_date.day:02d}"
        f"_FIT{batch_id}_{total_qty}.xlsx"
    )


def format_ship_box_no(batch_id: int, box_no: int) -> str:
    """发货箱号：与 INV packing_no 同口径。"""
    n = int(box_no)
    if int(batch_id) <= 0:
        return f"DRAFT-{n:02d}"
    return f"FIT{int(batch_id)}-{n:02d}"


def _price_text(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value).strip()


def _ensure_template() -> Path:
    if not TEMPLATE_PATH.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"SF template missing: {TEMPLATE_PATH}",
        )
    return TEMPLATE_PATH


def aggregate_sf_lines(raw_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Per ship_box_no: same barcode (+ unit price) merge qty.
    Empty barcode kept as separate rows within that box.
    Output order follows first appearance of each box, then items.
    """
    box_order: list[str] = []
    by_box: dict[str, dict[str, Any]] = {}

    for line in raw_lines:
        ship_box = (line.get("ship_box_no") or "").strip()
        if not ship_box:
            raise HTTPException(status_code=400, detail="SF 需要发货箱号")
        qty = int(line.get("qty") or 0)
        if qty < 1:
            continue
        if ship_box not in by_box:
            by_box[ship_box] = {"merged": {}, "order": [], "singles": []}
            box_order.append(ship_box)
        bucket = by_box[ship_box]
        barcode = (line.get("barcode") or "").strip()
        price_key = _price_text(line.get("unit_price"))
        base = {
            "ship_box_no": ship_box,
            "barcode": barcode,
            "name_cn": (line.get("name_cn") or "").strip(),
            "brand": (line.get("brand") or "").strip(),
            "unit_price": line.get("unit_price"),
        }
        if not barcode:
            bucket["singles"].append({**base, "qty": qty})
            continue
        key = (barcode, price_key)
        if key not in bucket["merged"]:
            bucket["merged"][key] = {**base, "qty": 0}
            bucket["order"].append(key)
        bucket["merged"][key]["qty"] += qty

    out: list[dict[str, Any]] = []
    for ship_box in box_order:
        bucket = by_box[ship_box]
        out.extend(bucket["merged"][k] for k in bucket["order"])
        out.extend(bucket["singles"])
    return out


# ============================================================
# FEATURE: SF_EXPORT
# [业务逻辑] build_sf_workbook — 填充模板 Sheet1
# ============================================================
def build_sf_workbook(
    *,
    batch_id: int,
    ship_date: date,
    product_lines: list[dict[str, Any]],
) -> tuple[bytes, str]:
    """
    product_lines: ship_box_no, barcode, name_cn, brand, qty, unit_price
    A 列「运单号*」填发货箱号：每箱首行写箱号，同箱后续行空。
    整表首行写收件人（与样表一致）。
    """
    lines = aggregate_sf_lines(product_lines)
    total_qty = sum(int(p.get("qty") or 0) for p in lines)
    if total_qty < 1:
        raise HTTPException(status_code=400, detail="SF 需要至少 1 件商品")

    filename = format_filename(ship_date, batch_id, total_qty)
    wb = load_workbook(_ensure_template())
    if SF_SHEET not in wb.sheetnames:
        raise HTTPException(
            status_code=500,
            detail=f"SF template sheet missing: {wb.sheetnames}",
        )
    ws = wb[SF_SHEET]
    data_start = 2
    style_row = 2
    n = len(lines)
    while ws.max_row < data_start + n - 1:
        new_r = ws.max_row + 1
        _copy_row_style(ws, style_row, new_r, 16)

    prev_box = ""
    for i, line in enumerate(lines):
        r = data_start + i
        if i > 0 and r != style_row:
            _copy_row_style(ws, style_row, r, 16)
        ship_box = (line.get("ship_box_no") or "").strip()
        # A 发货箱号 — first row of each box only
        ws.cell(r, 1, ship_box if ship_box != prev_box else None)
        prev_box = ship_box
        ws.cell(r, 2, (line.get("barcode") or "").strip())
        ws.cell(r, 3, (line.get("name_cn") or "").strip())
        ws.cell(r, 4, (line.get("brand") or "").strip())
        ws.cell(r, 5, ORIGIN)
        ws.cell(r, 6, SPEC)
        ws.cell(r, 7, int(line.get("qty") or 0))
        ws.cell(r, 8, _price_text(line.get("unit_price")))
        if i == 0:
            ws.cell(r, 9, CONSIGNEE["name"])
            ws.cell(r, 10, CONSIGNEE["phone"])
            ws.cell(r, 11, CONSIGNEE["country"])
            ws.cell(r, 12, CONSIGNEE["postcode"])
            ws.cell(r, 13, CONSIGNEE["province"] or None)
            ws.cell(r, 14, CONSIGNEE["city"])
            ws.cell(r, 15, CONSIGNEE["district"])
            ws.cell(r, 16, CONSIGNEE["address"])
        else:
            for c in range(9, 17):
                ws.cell(r, c, None)

    for r in range(data_start + n, max(ws.max_row, data_start + n) + 1):
        for c in range(1, 17):
            ws.cell(r, c, None)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue(), filename
