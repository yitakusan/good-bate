"""cystore.com（CyStore）購入履歴詳細 HTML order scrape tests."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from app.scrapers.cystore import (
    is_cystore_order_detail_html,
    parse_cystore_order_detail_html,
    parse_cystore_order_detail_lines,
)
from app.scrapers.preview import scrape_html_document

FIXTURE = (
    Path(__file__).resolve().parent
    / "app"
    / "scrapers"
    / "templates"
    / "cystore.order-detail.fixture.html"
)


class CystoreOrderDetailParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = FIXTURE.read_text(encoding="utf-8")

    def test_detect(self) -> None:
        self.assertTrue(is_cystore_order_detail_html(self.html))
        self.assertFalse(
            is_cystore_order_detail_html("<html><body>cystore 商品一覧</body></html>")
        )

    def test_parse_lines_and_meta(self) -> None:
        lines = parse_cystore_order_detail_lines(self.html)
        self.assertEqual(len(lines), 2)
        parsed = parse_cystore_order_detail_html(self.html)
        products = parsed["products"]
        self.assertEqual(len(products), 2)
        self.assertEqual(parsed["order_ref"], "CS3000495054")
        self.assertEqual(parsed["shipping_fee"], 671.0)
        self.assertEqual(parsed["order_total"], 60671.0)
        by_sku = {p["product_id"]: p for p in products}
        self.assertEqual(by_sku["2020220214016"]["qty"], 2)
        self.assertEqual(by_sku["2020220214016"]["unit_cost"], 2500.0)
        self.assertIn("ゴールドシップ", by_sku["2020220214016"]["name"])
        self.assertEqual(by_sku["2020220214030"]["qty"], 2)
        self.assertEqual(by_sku["2020220214030"]["unit_cost"], 2500.0)
        self.assertTrue(
            by_sku["2020220214016"]["source_url"].endswith("pid=2020220214016")
        )
        self.assertEqual(sum(int(p["qty"]) for p in products), 4)

    def test_scrape_html_document(self) -> None:
        result = asyncio.run(scrape_html_document(self.html))
        self.assertEqual(len(result["products"]), 2)
        self.assertEqual(result["order_ref"], "CS3000495054")
        self.assertEqual(result["shipping_fee"], 671.0)
        self.assertEqual(result["order_total"], 60671.0)
        self.assertIn("cystore", result["message"].lower() + "cystore")
        self.assertIn("CyStore", result["message"])


if __name__ == "__main__":
    unittest.main()
