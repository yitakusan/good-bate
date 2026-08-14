from __future__ import annotations

from app.database import get_conn
from app.models import LineCreate, OrderCreate
from app.services import orders as orders_svc
from app.services import outbound_batches as outbound_svc

BOX_PACKING = {
    "net_weight": 1.0,
    "gross_weight": 1.2,
    "length_cm": 10.0,
    "width_cm": 8.0,
    "height_cm": 6.0,
}


def make_priced_in_stock_order(
    *,
    order_ref: str = "T-001",
    shop: str = "test-shop",
    shipping_fee: float = 500,
    exchange_rate: float = 0.05,
) -> dict:
    order = orders_svc.create_order(
        OrderCreate(
            order_ref=order_ref,
            shop=shop,
            shipping_fee=shipping_fee,
            exchange_rate=exchange_rate,
            lines=[
                LineCreate(
                    name="Item A", qty=2, unit_cost=1000, barcode="111"
                ),
                LineCreate(
                    name="Item B", qty=1, unit_cost=2000, barcode="222"
                ),
            ],
        )
    )
    with get_conn() as conn:
        conn.execute(
            "UPDATE items SET status = 'in_stock' WHERE order_id = ?",
            (order["id"],),
        )
        conn.execute(
            "UPDATE orders SET status = 'in_stock' WHERE id = ?",
            (order["id"],),
        )
    return orders_svc.get_order(order["id"])


def make_packed_outbound_batch(
    order: dict,
    *,
    tracking_no: str = "OUT-TRK-001",
    note: str = "test batch",
    invoice_ship_date: str = "2026-08-14",
    freight_exchange_rate: float = 0.048,
    freight_unit_price_jpy: float = 1000,
    chargeable_weight: float = 2.5,
) -> dict:
    item_ids = [line["id"] for line in order["lines"]]
    return outbound_svc.create_batch(
        boxes=[
            {
                "box_no": 1,
                "carrier": "yamato",
                "tracking_no": tracking_no,
                "item_ids": item_ids,
                **BOX_PACKING,
            }
        ],
        note=note,
        freight_exchange_rate=freight_exchange_rate,
        freight_unit_price_jpy=freight_unit_price_jpy,
        chargeable_weight=chargeable_weight,
        invoice_ship_date=invoice_ship_date,
    )
