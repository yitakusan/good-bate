"""eeo.today（eeo Store）ご注文履歴詳細 HTML order scrape tests."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from app.scrapers.eeo import (
    is_eeo_order_detail_html,
    parse_eeo_order_detail_html,
    parse_eeo_order_detail_lines,
)
from app.scrapers.preview import scrape_html_document

FIXTURE = (
    Path(__file__).resolve().parent
    / "app"
    / "scrapers"
    / "templates"
    / "eeo.today.order-history-detail.fixture.html"
)


class EeoOrderDetailParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = FIXTURE.read_text(encoding="utf-8")

    def test_detect(self) -> None:
        self.assertTrue(is_eeo_order_detail_html(self.html))
        self.assertFalse(
            is_eeo_order_detail_html("<html><body>eeo Store 商品一覧</body></html>")
        )

    def test_parse_lines_and_meta(self) -> None:
        lines = parse_eeo_order_detail_lines(self.html)
        self.assertEqual(len(lines), 3)
        parsed = parse_eeo_order_detail_html(self.html)
        products = parsed["products"]
        self.assertEqual(len(products), 3)
        self.assertEqual(parsed["order_ref"], "101001323494")
        self.assertEqual(parsed["shipping_fee"], 770.0)
        self.assertEqual(parsed["order_total"], 42460.0)
        by_sku = {p["product_id"]: p for p in products}
        self.assertEqual(by_sku["319404"]["qty"], 5)
        self.assertEqual(by_sku["319404"]["unit_cost"], 7150.0)
        self.assertEqual(by_sku["319404"]["barcode"], "4570215793197")
        self.assertIn("缶バッジ", by_sku["319404"]["name"])
        self.assertEqual(by_sku["319400"]["qty"], 1)
        self.assertEqual(by_sku["319400"]["unit_cost"], 1980.0)
        self.assertEqual(by_sku["319400"]["barcode"], "4570215793234")
        self.assertEqual(by_sku["319399"]["qty"], 2)
        self.assertEqual(by_sku["319399"]["unit_cost"], 1980.0)
        self.assertEqual(by_sku["319399"]["barcode"], "4570215793241")
        self.assertIn("/products/detail/319404", by_sku["319404"]["source_url"])
        self.assertEqual(sum(int(p["qty"]) for p in products), 8)

    def test_scrape_html_document(self) -> None:
        result = asyncio.run(scrape_html_document(self.html))
        self.assertEqual(len(result["products"]), 3)
        self.assertEqual(result["order_ref"], "101001323494")
        self.assertEqual(result["shipping_fee"], 770.0)
        self.assertEqual(result["order_total"], 42460.0)
        self.assertIn("eeo", result["message"].lower())
        self.assertTrue(any(p.get("barcode") for p in result["products"]))


if __name__ == "__main__":
    unittest.main()
