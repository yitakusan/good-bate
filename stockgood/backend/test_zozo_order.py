"""ZOZO order-detail HTML paste scrape tests."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from app.scrapers.preview import scrape_html_document
from app.scrapers.zozo import (
    is_zozo_order_detail_html,
    is_zozo_order_list_html,
    parse_zozo_order_detail_html,
)

FIXTURE = (
    Path(__file__).resolve().parent
    / "app"
    / "scrapers"
    / "templates"
    / "zozo.jp.order-detail.snippet.html"
)


class ZozoOrderDetailParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = FIXTURE.read_text(encoding="utf-8")

    def test_detect_detail_not_list(self) -> None:
        self.assertTrue(is_zozo_order_detail_html(self.html))
        self.assertFalse(is_zozo_order_list_html(self.html))

    def test_detect_list_page(self) -> None:
        list_html = (
            '<div id="orderListWrapper"><div class="orderList">'
            "注文履歴</div></div>"
            '<link href="/assets/style/Pages-member-orderhistory-index.css">'
        )
        self.assertTrue(is_zozo_order_list_html(list_html))
        self.assertFalse(is_zozo_order_detail_html(list_html))

    def test_parse_order_340142752(self) -> None:
        orders = parse_zozo_order_detail_html(self.html)
        self.assertEqual(len(orders), 1)
        order = orders[0]
        self.assertEqual(order["order_ref"], "340142752")
        self.assertEqual(order["shipping_fee"], 330.0)
        self.assertEqual(order["order_total"], 20130.0)
        self.assertEqual(order["goods_total"], 19800.0)
        self.assertEqual(order["ordered_at"], "2026.06.11 17:15:32")
        self.assertEqual(order["tracking_no"], "293148004925")
        self.assertEqual(order["status_text"], "配達完了")
        self.assertEqual(len(order["lines"]), 2)

        line0, line1 = order["lines"]
        self.assertEqual(line0["qty"], 3)
        self.assertEqual(line0["unit_cost"], 4950.0)
        self.assertIn("ブラック系その他 / FREE", line0["name"])
        self.assertEqual(
            line0["source_url"],
            "https://zozo.jp/shop/zozospot/goods/107113570/?did=171303491",
        )
        self.assertEqual(line0["shop"], "zozo.jp/zozospot")

        self.assertEqual(line1["qty"], 1)
        self.assertIn("ブラック系その他3 / FREE", line1["name"])
        self.assertIn("did=171544933", line1["source_url"])

    def test_scrape_html_document_returns_order_meta(self) -> None:
        result = asyncio.run(scrape_html_document(self.html))
        self.assertEqual(result["order_ref"], "340142752")
        self.assertEqual(result["shipping_fee"], 330.0)
        self.assertEqual(result["order_total"], 20130.0)
        self.assertEqual(len(result["products"]), 2)
        self.assertEqual(result["products"][0]["qty"], 3)
        self.assertEqual(result["products"][1]["qty"], 1)
        self.assertIn("注文番号 340142752", result["message"])

    def test_product_page_with_header_orderhistory_not_list(self) -> None:
        """Global nav links must not trip list-page detector (parallel-merge bug)."""
        pdp = (
            Path(__file__).resolve().parent
            / "app"
            / "scrapers"
            / "templates"
            / "zozo.jp.snippet.html"
        ).read_text(encoding="utf-8")
        with_nav = pdp.replace(
            "</body>",
            '<a href="/_member/orderhistory/default.html">注文履歴・発送状況</a></body>',
        )
        self.assertFalse(is_zozo_order_list_html(with_nav))
        result = asyncio.run(scrape_html_document(with_nav))
        self.assertEqual(len(result["products"]), 1)
        self.assertIn("オーバーサイズ", result["products"][0]["name"])

    def test_list_page_rejected_with_hint(self) -> None:
        list_html = (
            '<title>注文履歴 - ZOZOTOWN</title>'
            '<div id="orderListWrapper"></div>'
            '<link href="/assets/style/Pages-member-orderhistory-index.css">'
        )
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(scrape_html_document(list_html))
        self.assertIn("注文詳細", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
