"""FEATURE: RETAILER_CART — parse preview then create inventory order (isolated sqlite)."""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _TESTS_DIR.parent
for _path in (_BACKEND_DIR, _TESTS_DIR):
    text = str(_path)
    if text not in sys.path:
        sys.path.insert(0, text)

from app.models import OrderCreate
from app.services import orders as orders_svc
from app.services.retailer_cart import TEMPLATE_CSV, build_order_payload, parse_template
from harness import IsolatedDbTestCase

FAKE_PRODUCT = {
    "handle": "2000326637643",
    "title": "Roselia keyholder",
    "images": [{"src": "https://cdn.example/roselia.jpg"}],
    "variants": [
        {
            "id": 46137068159183,
            "available": True,
            "title": "Default Title",
            "price": "1500",
        }
    ],
}


class RetailerCartOrderTests(IsolatedDbTestCase):
    def test_parse_then_create_inventory_order(self) -> None:
        parsed = parse_template(
            TEMPLATE_CSV.encode("utf-8"),
            "sample.csv",
            fetch_product=lambda _u: FAKE_PRODUCT,
        )
        payload = build_order_payload(parsed["eligible"], "BR-2002", 2000)
        order = orders_svc.create_order(OrderCreate(**payload))
        self.assertEqual(order["shop"], "bushiroad-store.com")
        self.assertEqual(order["order_ref"], "BR-2002")
        self.assertEqual(order["line_count"], 1)
        self.assertEqual(order["total_qty"], 1)
        line = order["lines"][0]
        self.assertEqual(line["name"], "Roselia keyholder")
        self.assertEqual(line["qty"], 1)
        self.assertEqual(line["unit_cost"], 1650.0)
        self.assertEqual(line["shop"], "bushiroad-store.com")
        self.assertEqual(order["order_total"], 2000.0)
        self.assertIn("对方总价 JPY 2000", order["note"])

    def test_create_order_uses_line_shop(self) -> None:
        raw = (
            "链接,数量\n"
            "https://lafary.shop/products/1000000200652,1\n"
        ).encode("utf-8")
        parsed = parse_template(
            raw,
            "lafary.csv",
            fetch_product=lambda _u: FAKE_PRODUCT,
        )
        payload = build_order_payload(parsed["eligible"], "LF-9", 1500)
        order = orders_svc.create_order(OrderCreate(**payload))
        self.assertEqual(order["shop"], "lafary.shop")
        self.assertEqual(order["lines"][0]["shop"], "lafary.shop")
        self.assertEqual(order["lines"][0]["unit_cost"], 1500.0)
        self.assertEqual(order["order_total"], 1500.0)

    def test_duplicate_order_ref_is_allowed(self) -> None:
        parsed = parse_template(
            TEMPLATE_CSV.encode("utf-8"),
            "sample.csv",
            fetch_product=lambda _u: FAKE_PRODUCT,
        )
        first = orders_svc.create_order(
            OrderCreate(**build_order_payload(parsed["eligible"], "BR-DUP", 1800))
        )
        second = orders_svc.create_order(
            OrderCreate(**build_order_payload(parsed["eligible"], "BR-DUP", 1900))
        )
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["order_ref"], "BR-DUP")
        self.assertEqual(second["order_ref"], "BR-DUP")
