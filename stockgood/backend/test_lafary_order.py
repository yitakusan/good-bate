"""lafary.shop（LAFARY ONLINE）customers/order HTML scrape tests."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from app.scrapers.lafary import (
    is_lafary_order_html,
    parse_lafary_order_html,
    parse_lafary_order_lines,
)
from app.scrapers.preview import scrape_html_document

FIXTURE = (
    Path(__file__).resolve().parent
    / "app"
    / "scrapers"
    / "templates"
    / "lafary.shop.customers-order.fixture.html"
)


class LafaryOrderParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = FIXTURE.read_text(encoding="utf-8")

    def test_detect(self) -> None:
        self.assertTrue(is_lafary_order_html(self.html))
        self.assertFalse(
            is_lafary_order_html("<html><body>LAFARY ONLINE 商品一覧</body></html>")
        )

    def test_parse_lines_and_meta(self) -> None:
        lines = parse_lafary_order_lines(self.html)
        self.assertEqual(len(lines), 2)
        parsed = parse_lafary_order_html(self.html)
        products = parsed["products"]
        self.assertEqual(len(products), 2)
        self.assertEqual(parsed["order_ref"], "66321")
        self.assertEqual(parsed["shipping_fee"], 0.0)
        self.assertEqual(parsed["order_total"], 23200.0)
        by_name = {p["name"]: p for p in products}
        card = by_name["《リコリス・リコイル×LAFARY》クリアカードセット(10枚入り)"]
        badge = by_name["《リコリス・リコイル×LAFARY》缶バッジセット(8個入り)"]
        self.assertEqual(card["qty"], 2)
        self.assertEqual(card["unit_cost"], 5000.0)
        self.assertEqual(badge["qty"], 3)
        self.assertEqual(badge["unit_cost"], 4400.0)
        self.assertEqual(sum(int(p["qty"]) for p in products), 5)
        self.assertFalse(any((p.get("barcode") or "").strip() for p in products))

    def test_scrape_html_document(self) -> None:
        result = asyncio.run(scrape_html_document(self.html))
        self.assertEqual(len(result["products"]), 2)
        self.assertEqual(result["order_ref"], "66321")
        self.assertEqual(result["shipping_fee"], 0.0)
        self.assertEqual(result["order_total"], 23200.0)
        self.assertIn("lafary", result["message"].lower())


if __name__ == "__main__":
    unittest.main()
