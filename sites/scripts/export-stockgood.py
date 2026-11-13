"""Export a Stockgood SQLite database to a JSON file for the Sites import screen."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys


def export_orders(database, warehouse):
    uri = database.resolve(strict=True).as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        columns = {column["name"] for column in connection.execute("PRAGMA table_info(orders)")}
        if warehouse is not None and "warehouse_id" not in columns:
            raise ValueError("当前 Stockgood 数据库没有仓库列")
        where = "WHERE warehouse_id = ?" if warehouse is not None else ""
        args = (warehouse,) if warehouse is not None else ()
        orders = {
            order["id"]: {**dict(order), "lines": []}
            for order in connection.execute(f"SELECT * FROM orders {where} ORDER BY id", args)
        }
        boxes = {
            row["order_id"]: row["box_no"]
            for row in connection.execute(
                "SELECT sbo.order_id, sb.box_no FROM stock_box_orders sbo JOIN stock_boxes sb ON sb.id = sbo.box_id"
            )
        }
        shipments = {}
        for row in connection.execute(
            """
            SELECT si.item_id, s.*
            FROM shipment_items si JOIN shipments s ON s.id = si.shipment_id
            ORDER BY s.id
            """
        ):
            shipments.setdefault(row["item_id"], {})[row["direction"]] = row
        for row in connection.execute("SELECT * FROM items ORDER BY id"):
            line = dict(row)
            order = orders.get(row["order_id"])
            if row["order_id"] in boxes:
                line["stock_box_no"] = boxes[row["order_id"]]
            if order is None and (warehouse is not None or row["order_id"] is not None):
                continue
            for direction, shipment in shipments.get(row["id"], {}).items():
                if direction not in ("inbound", "outbound"):
                    continue
                tracking = shipment["tracking_no"]
                line[f"{direction}_tracking_no"] = "" if (tracking or "").startswith("__none__") else tracking
                line[f"{direction}_carrier"] = shipment["carrier"]
                line[f"{direction}_shipment_id"] = shipment["id"]
                if direction == "outbound":
                    line["outbound_box_no"] = shipment["box_no"]
            if order is None:
                orders[f"legacy-{row['id']}"] = {"lines": [line]}
            else:
                order["lines"].append(line)
        return [order for order in orders.values() if order["lines"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("output", type=Path, help="A new .json file")
    parser.add_argument("--warehouse", type=int, help="Optional Stockgood warehouse ID")
    args = parser.parse_args()
    try:
        if args.output.suffix.lower() != ".json":
            raise ValueError("输出文件须使用 .json 扩展名")
        orders = export_orders(args.database, args.warehouse)
        if not orders:
            raise ValueError("没有找到可导出的订单明细")
        payload = json.dumps({"orders": orders}, ensure_ascii=False, indent=2)
        with args.output.open("x", encoding="utf-8", newline="\n") as output:
            output.write(payload + "\n")
        print(f"已导出 {len(orders)} 笔订单，共 {sum(len(o['lines']) for o in orders)} 条明细")
    except (ValueError, OSError, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
