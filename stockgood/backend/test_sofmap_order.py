"""sofmap.com お取引の詳細 HTML order scrape tests."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from app.scrapers.preview import scrape_html_document
from app.scrapers.sofmap import (
    is_sofmap_order_detail_html,
    parse_sofmap_order_detail_html,
    parse_sofmap_order_detail_lines,
)

FIXTURE = (
    Path(__file__).resolve().parent
    / "app"
    / "scrapers"
    / "templates"
    / "sofmap.order-detail.fixture.html"
)


class SofmapOrderDetailParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = FIXTURE.read_text(encoding="utf-8")

    def test_detect(self) -> None:
        self.assertTrue(is_sofmap_order_detail_html(self.html))
        self.assertFalse(
            is_sofmap_order_detail_html("<html><body>sofmap 商品一覧</body></html>")
        )

    def test_parse_lines_and_meta(self) -> None:
        lines = parse_sofmap_order_detail_lines(self.html)
        self.assertEqual(len(lines), 5)
        parsed = parse_sofmap_order_detail_html(self.html)
        products = parsed["products"]
        self.assertEqual(len(products), 5)
        self.assertEqual(parsed["order_ref"], "055414990")
        self.assertEqual(parsed["shipping_fee"], 0.0)
        self.assertEqual(parsed["order_total"], 71500.0)
        by_sku = {p["product_id"]: p for p in products}
        self.assertEqual(by_sku["102018410"]["qty"], 30)
        self.assertEqual(by_sku["102018410"]["unit_cost"], 1650.0)
        self.assertEqual(by_sku["102018410"]["barcode"], "4580814642369")
        self.assertEqual(by_sku["102018397"]["qty"], 10)
        self.assertEqual(by_sku["102018397"]["barcode"], "4580814642321")
        self.assertEqual(
            by_sku["102018397"]["source_url"],
            "https://a.sofmap.com/product_detail.aspx?sku=102018397",
        )
        self.assertEqual(sum(int(p["qty"]) for p in products), 70)

    def test_scrape_html_document(self) -> None:
        result = asyncio.run(scrape_html_document(self.html))
        self.assertEqual(len(result["products"]), 5)
        self.assertEqual(result["order_ref"], "055414990")
        self.assertEqual(result["shipping_fee"], 0.0)
        self.assertEqual(result["order_total"], 71500.0)
        self.assertIn("sofmap", result["message"].lower())
        self.assertIn("JAN", result["message"])


if __name__ == "__main__":
    unittest.main()
