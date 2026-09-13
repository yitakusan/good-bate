"""&mall (mitsui-shopping-park) order-history HTML paste scrape tests."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from app.scrapers.andmall import (
    is_andmall_order_history_html,
    looks_like_andmall_order_json,
    merge_andmall_products,
    parse_andmall_order_history_html,
    parse_andmall_order_history_lines,
    parse_andmall_order_payload,
    parse_andmall_order_skus_json,
)
from app.scrapers.preview import scrape_html_document

FIXTURE = (
    Path(__file__).resolve().parent
    / "app"
    / "scrapers"
    / "templates"
    / "mitsui-shopping-park.com.order-history.fixture.html"
)
SNIPPET = (
    Path(__file__).resolve().parent
    / "app"
    / "scrapers"
    / "templates"
    / "mitsui-shopping-park.com.order-history.snippet.html"
)

SAMPLE_JSON = """
{
  "shopOrderSkus": [
    {
      "itemName": "アクリルスタンド（ライスシャワー）【2026年9月以降発送予定】",
      "quantity": 10,
      "mallSkuId": 62607000001710001,
      "mallProductCodeId": "6260700000171",
      "imageUrl": "https://mitsui-shopping-park.com/ec/ecstatic/product/color/6260700000171_9503.jpg",
      "shopName": "ウマ娘"
    },
    {
      "itemName": "アクリルスタンド（カレンチャン）【2026年9月以降発送予定】",
      "quantity": 5,
      "mallSkuId": 62607000001750001,
      "mallProductCodeId": "6260700000175",
      "imageUrl": "https://mitsui-shopping-park.com/ec/ecstatic/product/color/6260700000175_9503.jpg",
      "shopName": "ウマ娘"
    }
  ]
}
{
  "shopOrderSkus": [
    {
      "itemName": "アクリルスタンド（ライスシャワー）【2026年9月以降発送予定】",
      "quantity": 15,
      "mallSkuId": 62607000001710001,
      "mallProductCodeId": "6260700000171",
      "imageUrl": "https://mitsui-shopping-park.com/ec/ecstatic/product/color/6260700000171_9503.jpg",
      "shopName": "ウマ娘"
    }
  ]
}
"""


class AndmallOrderHistoryParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = FIXTURE.read_text(encoding="utf-8")

    def test_detect(self) -> None:
        self.assertTrue(is_andmall_order_history_html(self.html))
        self.assertFalse(is_andmall_order_history_html("<html><body>注文履歴</body></html>"))

    def test_detect_elements_fragment(self) -> None:
        snippet = SNIPPET.read_text(encoding="utf-8")
        self.assertTrue(is_andmall_order_history_html(snippet))
        products = parse_andmall_order_history_html(snippet)
        self.assertGreaterEqual(len(products), 1)

    def test_parse_lines_and_merge(self) -> None:
        lines = parse_andmall_order_history_lines(self.html)
        self.assertEqual(len(lines), 10)
        products = merge_andmall_products(lines)
        self.assertEqual(len(products), 4)

        by_code = {p["product_code"]: p for p in products}
        self.assertEqual(by_code["6260700000171"]["qty"], 25)
        self.assertEqual(by_code["6260700000175"]["qty"], 15)
        self.assertEqual(by_code["6260700000174"]["qty"], 5)
        self.assertEqual(by_code["6260700000173"]["qty"], 1)
        self.assertIn("ライスシャワー", by_code["6260700000171"]["name"])
        self.assertEqual(by_code["6260700000171"]["expected_ship_at"], "2026-09")
        self.assertEqual(
            by_code["6260700000171"]["source_url"],
            "https://mitsui-shopping-park.com/ec/product/6260700000171",
        )
        self.assertEqual(by_code["6260700000171"]["shop"], "mitsui-shopping-park.com")

    def test_parse_html_entry(self) -> None:
        products = parse_andmall_order_history_html(self.html)
        self.assertEqual(len(products), 4)
        self.assertEqual(sum(int(p["qty"]) for p in products), 46)

    def test_json_paste_merge_pages(self) -> None:
        self.assertTrue(looks_like_andmall_order_json(SAMPLE_JSON))
        lines = parse_andmall_order_skus_json(SAMPLE_JSON)
        self.assertEqual(len(lines), 3)
        products, kind = parse_andmall_order_payload(SAMPLE_JSON)
        self.assertEqual(kind, "json")
        self.assertEqual(len(products), 2)
        by_code = {p["product_code"]: p for p in products}
        self.assertEqual(by_code["6260700000171"]["qty"], 25)
        self.assertEqual(by_code["6260700000175"]["qty"], 5)

    def test_scrape_html_document(self) -> None:
        result = asyncio.run(scrape_html_document(self.html))
        self.assertEqual(len(result["products"]), 4)
        self.assertIn("合并为 4 种", result["message"])
        self.assertIn("合计数量 46", result["message"])
        self.assertIn("10/29", result["message"])
        self.assertIn("Elements", result["message"])
        self.assertEqual(result["products"][0]["qty"], 25)
        self.assertEqual(result.get("order_ref"), "")

    def test_scrape_json_document(self) -> None:
        result = asyncio.run(scrape_html_document(SAMPLE_JSON))
        self.assertEqual(len(result["products"]), 2)
        self.assertIn("JSON", result["message"])
        self.assertNotIn("Elements", result["message"])
        self.assertEqual(sum(int(p["qty"]) for p in result["products"]), 30)


if __name__ == "__main__":
    unittest.main()
