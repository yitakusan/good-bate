"""animate-onlineshop.jp（アニメイト通販）注文履歴 HTML order scrape tests."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from app.scrapers.animate import (
    is_animate_order_history_html,
    parse_animate_order_history_html,
    parse_animate_order_history_lines,
)
from app.scrapers.preview import scrape_html_document

FIXTURE = (
    Path(__file__).resolve().parent
    / "app"
    / "scrapers"
    / "templates"
    / "animate-onlineshop.jp.order-history.fixture.html"
)


class AnimateOrderHistoryParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = FIXTURE.read_text(encoding="utf-8")

    def test_detect(self) -> None:
        self.assertTrue(is_animate_order_history_html(self.html))
        self.assertFalse(
            is_animate_order_history_html(
                "<html><body>アニメイト 商品一覧</body></html>"
            )
        )

    def test_parse_lines_and_meta(self) -> None:
        lines = parse_animate_order_history_lines(self.html)
        self.assertEqual(len(lines), 3)
        parsed = parse_animate_order_history_html(self.html)
        products = parsed["products"]
        self.assertEqual(len(products), 3)
        self.assertEqual(parsed["order_ref"], "52898468")
        self.assertEqual(parsed["shipping_fee"], 0.0)
        self.assertEqual(parsed["order_total"], 128700.0)
        by_sku = {p["product_id"]: p for p in products}
        self.assertEqual(by_sku["3459202"]["qty"], 140)
        self.assertEqual(by_sku["3459202"]["unit_cost"], 605.0)
        self.assertIn("缶バッジ", by_sku["3459202"]["name"])
        self.assertEqual(by_sku["3459221"]["qty"], 80)
        self.assertEqual(by_sku["3459221"]["unit_cost"], 275.0)
        self.assertEqual(by_sku["3459222"]["qty"], 80)
        self.assertEqual(by_sku["3459222"]["unit_cost"], 275.0)
        self.assertIn("/pd/3459202/", by_sku["3459202"]["source_url"])
        self.assertEqual(sum(int(p["qty"]) for p in products), 300)

    def test_skips_privilege(self) -> None:
        lines = parse_animate_order_history_lines(self.html)
        names = " ".join(p["name"] for p in lines)
        self.assertNotIn("BOX特典", names)
        self.assertNotIn("この受注に付与される特典", names)

    def test_scrape_html_document(self) -> None:
        result = asyncio.run(scrape_html_document(self.html))
        self.assertEqual(len(result["products"]), 3)
        self.assertEqual(result["order_ref"], "52898468")
        self.assertEqual(result["shipping_fee"], 0.0)
        self.assertEqual(result["order_total"], 128700.0)
        self.assertIn("アニメイト", result["message"])


if __name__ == "__main__":
    unittest.main()
