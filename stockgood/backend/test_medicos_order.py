"""medicos-e-shop.net（MEDICOS ONLINE SHOP）購入履歴詳細 HTML order scrape tests."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from app.scrapers.medicos import (
    is_medicos_order_detail_html,
    parse_medicos_order_detail_html,
    parse_medicos_order_detail_lines,
)
from app.scrapers.preview import scrape_html_document

FIXTURE = (
    Path(__file__).resolve().parent
    / "app"
    / "scrapers"
    / "templates"
    / "medicos-e-shop.mypage-history.fixture.html"
)


class MedicosOrderDetailParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = FIXTURE.read_text(encoding="utf-8")

    def test_detect(self) -> None:
        self.assertTrue(is_medicos_order_detail_html(self.html))
        self.assertFalse(
            is_medicos_order_detail_html(
                "<html><body>MEDICOS ONLINE SHOP 商品一覧</body></html>"
            )
        )

    def test_parse_lines_and_meta(self) -> None:
        lines = parse_medicos_order_detail_lines(self.html)
        self.assertEqual(len(lines), 2)
        parsed = parse_medicos_order_detail_html(self.html)
        products = parsed["products"]
        self.assertEqual(len(products), 2)
        self.assertEqual(parsed["order_ref"], "959428")
        self.assertEqual(parsed["shipping_fee"], 650.0)
        self.assertEqual(parsed["order_total"], 36840.0)
        by_pid = {p["product_id"]: p for p in products}
        badge = by_pid["0509185651_69ff04e38d4af"]
        card = by_pid["0509185908_69ff056c8404a"]
        self.assertEqual(badge["qty"], 5)
        self.assertEqual(badge["unit_cost"], 4950.0)
        self.assertEqual(badge["barcode"], "4573699566776")
        self.assertIn("缶バッジ", badge["name"])
        self.assertEqual(card["qty"], 2)
        self.assertEqual(card["unit_cost"], 5720.0)
        self.assertEqual(card["barcode"], "4573699566790")
        self.assertIn("クリアカード", card["name"])
        self.assertEqual(sum(int(p["qty"]) for p in products), 7)

    def test_scrape_html_document(self) -> None:
        result = asyncio.run(scrape_html_document(self.html))
        self.assertEqual(len(result["products"]), 2)
        self.assertEqual(result["order_ref"], "959428")
        self.assertEqual(result["shipping_fee"], 650.0)
        self.assertEqual(result["order_total"], 36840.0)
        self.assertIn("medicos", result["message"].lower())
        self.assertTrue(all(p.get("barcode") for p in result["products"]))


if __name__ == "__main__":
    unittest.main()
