"""STORES（*.stores.jp）ORDER_IMPORT tests."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from app.scrapers.preview import scrape_html_document
from app.scrapers.storesjp import (
    is_stores_mypage_order_shell_html,
    is_stores_order_detail_html,
    is_stores_product_html,
    is_stores_url,
    item_id_from_url,
    looks_like_stores_order_json,
    parse_stores_order_detail_html,
    parse_stores_order_json,
    parse_stores_product_html,
    scrape_stores_product,
)

TEMPLATES = Path(__file__).resolve().parent / "app" / "scrapers" / "templates"
PRODUCT_FIXTURE = TEMPLATES / "storesjp.item.fixture.html"
ORDER_JSON_FIXTURE = TEMPLATES / "storesjp.order-detail.fixture.json"
ORDER_HTML_FIXTURE = TEMPLATES / "storesjp.order-detail.fixture.html"
SHELL_FIXTURE = TEMPLATES / "storesjp.mypage-order-shell.fixture.html"


class StoresJpScraperTests(unittest.TestCase):
    def test_url_helpers(self) -> None:
        url = "https://shibuyatsutaya.stores.jp/items/6a22862e9d5f2b0605ba1eca"
        self.assertTrue(is_stores_url(url))
        self.assertEqual(item_id_from_url(url), "6a22862e9d5f2b0605ba1eca")

    def test_live_curl_product_url(self) -> None:
        """Live: curl should bypass Cloudflare where httpx cannot."""
        url = "https://shibuyatsutaya.stores.jp/items/6a22862e9d5f2b0605ba1eca"
        product = asyncio.run(scrape_stores_product(url))
        if product is None:
            self.skipTest("STORES curl fetch blocked in this environment")
        self.assertIn("缶バッジ", product["name"])
        self.assertEqual(product["unit_cost"], 2750.0)
        self.assertEqual(product["product_id"], "6a22862e9d5f2b0605ba1eca")

    def test_product_html(self) -> None:
        html = PRODUCT_FIXTURE.read_text(encoding="utf-8")
        self.assertTrue(is_stores_product_html(html))
        product = parse_stores_product_html(
            html, "https://shibuyatsutaya.stores.jp/items/6a22862e9d5f2b0605ba1eca"
        )
        assert product is not None
        self.assertIn("トレーディング缶バッジ", product["name"])
        self.assertEqual(product["unit_cost"], 2750.0)
        self.assertEqual(product["product_id"], "6a22862e9d5f2b0605ba1eca")
        self.assertEqual(product["release_date"], "2026-08-下旬")
        self.assertTrue(product["image_url"].startswith("http"))

    def test_order_json(self) -> None:
        raw = ORDER_JSON_FIXTURE.read_text(encoding="utf-8")
        self.assertTrue(looks_like_stores_order_json(raw))
        parsed = parse_stores_order_json(raw)
        self.assertEqual(parsed["order_ref"], "250913001")
        self.assertEqual(parsed["shipping_fee"], 800.0)
        self.assertEqual(parsed["order_total"], 18050.0)
        products = parsed["products"]
        self.assertEqual(len(products), 3)
        by_id = {p["product_id"]: p for p in products}
        self.assertEqual(by_id["6a22862e9d5f2b0605ba1eca"]["qty"], 1)
        self.assertEqual(by_id["6a22862e9d5f2b0605ba1eca"]["unit_cost"], 2750.0)
        self.assertEqual(by_id["6a2290a7130f3413bd9f42f2"]["qty"], 2)
        self.assertEqual(by_id["6a2290a7130f3413bd9f42f2"]["unit_cost"], 2200.0)
        self.assertIn("亜玖璃", by_id["6a2290a7130f3413bd9f42f2"]["name"])
        self.assertEqual(by_id["6a22917f9d5f2b13510d4d89"]["unit_cost"], 550.0)

    def test_order_detail_html(self) -> None:
        html = ORDER_HTML_FIXTURE.read_text(encoding="utf-8")
        self.assertTrue(is_stores_order_detail_html(html))
        self.assertFalse(is_stores_product_html(html))
        self.assertFalse(is_stores_mypage_order_shell_html(html))
        parsed = parse_stores_order_detail_html(html)
        self.assertEqual(parsed["order_ref"], "0151248181")
        self.assertEqual(parsed["shipping_fee"], 990.0)
        self.assertEqual(parsed["order_total"], 173250.0)
        products = parsed["products"]
        self.assertEqual(len(products), 6)
        by_id = {p["product_id"]: p for p in products}
        self.assertEqual(by_id["6a22862e9d5f2b0605ba1eca"]["qty"], 30)
        self.assertEqual(by_id["6a22862e9d5f2b0605ba1eca"]["unit_cost"], 2750.0)
        self.assertEqual(by_id["6a2290a7130f3413bd9f42f2"]["qty"], 13)
        self.assertEqual(by_id["6a2290a7130f3413bd9f42f2"]["unit_cost"], 3300.0)
        self.assertEqual(by_id["6a22917f9d5f2b13510d4d89"]["unit_cost"], 1650.0)
        self.assertEqual(by_id["6a22913bb2c71d143f2a9b5e"]["qty"], 5)
        self.assertEqual(by_id["6a2290f8e37c5b14273886a0"]["qty"], 20)
        self.assertEqual(by_id["6a229233e37c5b1427388747"]["qty"], 1)
        self.assertEqual(by_id["6a229233e37c5b1427388747"]["unit_cost"], 660.0)

    def test_shell(self) -> None:
        html = SHELL_FIXTURE.read_text(encoding="utf-8")
        self.assertTrue(is_stores_mypage_order_shell_html(html))
        self.assertFalse(is_stores_order_detail_html(html))

    def test_scrape_html_document_product(self) -> None:
        html = PRODUCT_FIXTURE.read_text(encoding="utf-8")
        result = asyncio.run(scrape_html_document(html))
        self.assertEqual(len(result["products"]), 1)
        self.assertEqual(result["products"][0]["unit_cost"], 2750.0)
        self.assertIn("STORES", result["message"])

    def test_scrape_html_document_order_json(self) -> None:
        raw = ORDER_JSON_FIXTURE.read_text(encoding="utf-8")
        result = asyncio.run(scrape_html_document(raw))
        self.assertEqual(len(result["products"]), 3)
        self.assertEqual(result["shipping_fee"], 800.0)
        self.assertEqual(result["order_ref"], "250913001")

    def test_scrape_html_document_order_html(self) -> None:
        html = ORDER_HTML_FIXTURE.read_text(encoding="utf-8")
        result = asyncio.run(scrape_html_document(html))
        self.assertEqual(len(result["products"]), 6)
        self.assertEqual(result["order_ref"], "0151248181")
        self.assertEqual(result["shipping_fee"], 990.0)
        self.assertEqual(result["order_total"], 173250.0)
        self.assertIn("購入詳細", result["message"])

    def test_scrape_html_document_shell(self) -> None:
        html = SHELL_FIXTURE.read_text(encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(scrape_html_document(html))
        self.assertIn("SPA", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
