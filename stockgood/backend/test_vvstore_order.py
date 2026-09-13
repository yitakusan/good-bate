"""vvstore.jp order-history detail HTML paste scrape tests."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from app.scrapers.preview import scrape_html_document
from app.scrapers.vvstore import (
    is_vvstore_order_detail_html,
    merge_vvstore_products,
    parse_vvstore_order_detail_html,
    parse_vvstore_order_detail_lines,
)

FIXTURE = (
    Path(__file__).resolve().parent
    / "app"
    / "scrapers"
    / "templates"
    / "vvstore.jp.order-history.fixture.html"
)


class VvstoreOrderDetailParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = FIXTURE.read_text(encoding="utf-8")

    def test_detect(self) -> None:
        self.assertTrue(is_vvstore_order_detail_html(self.html))
        self.assertFalse(is_vvstore_order_detail_html("<html><body>注文履歴</body></html>"))

    def test_parse_lines_and_merge(self) -> None:
        lines = parse_vvstore_order_detail_lines(self.html)
        self.assertEqual(len(lines), 4)
        products = merge_vvstore_products(lines)
        self.assertEqual(len(products), 3)
        by_id = {p["product_id"]: p for p in products}
        self.assertEqual(by_id["5065660"]["qty"], 3)  # 1+2 merged
        self.assertEqual(by_id["5065660"]["unit_cost"], 2500.0)
        self.assertEqual(by_id["5065667"]["qty"], 3)
        self.assertEqual(by_id["5065667"]["unit_cost"], 1200.0)
        self.assertEqual(by_id["5065715"]["qty"], 4)
        self.assertEqual(by_id["5065715"]["unit_cost"], 500.0)
        self.assertEqual(
            by_id["5065660"]["source_url"],
            "https://vvstore.jp/products/detail/5065660",
        )
        self.assertEqual(by_id["5065660"]["shop"], "vvstore.jp")
        self.assertIn("ビッグキャラクタースタンド", by_id["5065660"]["name"])

    def test_parse_html_entry(self) -> None:
        parsed = parse_vvstore_order_detail_html(self.html)
        self.assertEqual(len(parsed["products"]), 3)
        self.assertEqual(parsed["order_ref"], "50313680")
        self.assertEqual(parsed["shipping_fee"], 880.0)
        self.assertEqual(parsed["order_total"], 63180.0)
        self.assertEqual(sum(int(p["qty"]) for p in parsed["products"]), 10)

    def test_scrape_html_document(self) -> None:
        result = asyncio.run(scrape_html_document(self.html))
        self.assertEqual(len(result["products"]), 3)
        self.assertEqual(result["order_ref"], "50313680")
        self.assertEqual(result["shipping_fee"], 880.0)
        self.assertEqual(result["order_total"], 63180.0)
        self.assertIn("合并为 3 种", result["message"])
        self.assertIn("50313680", result["message"])
        self.assertIn("运费 ¥880", result["message"])
        self.assertEqual(result["products"][0]["qty"], 3)


if __name__ == "__main__":
    unittest.main()
