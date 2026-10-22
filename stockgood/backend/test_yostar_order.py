"""shop.yostar.co.jp（Yostar OFFICIAL SHOP）ORDER_IMPORT tests."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from app.scrapers.preview import scrape_html_document
from app.scrapers.yostar import (
    is_yostar_spa_shell_html,
    is_yostar_url,
    looks_like_yostar_order_json,
    looks_like_yostar_product_json,
    parse_yostar_order_json,
    parse_yostar_product_json,
    product_id_from_url,
    product_from_api_data,
)

TEMPLATES = Path(__file__).resolve().parent / "app" / "scrapers" / "templates"
PRODUCT_FIXTURE = TEMPLATES / "yostar.product-5232.fixture.json"
ORDER_FIXTURE = TEMPLATES / "yostar.order-detail.fixture.json"
SHELL_FIXTURE = TEMPLATES / "yostar.spa-shell.fixture.html"


class YostarScraperTests(unittest.TestCase):
    def test_url_helpers(self) -> None:
        url = "https://shop.yostar.co.jp/products/detail/5232"
        self.assertTrue(is_yostar_url(url))
        self.assertEqual(product_id_from_url(url), 5232)
        self.assertFalse(is_yostar_url("https://example.com/products/detail/1"))

    def test_product_fixture(self) -> None:
        raw = PRODUCT_FIXTURE.read_text(encoding="utf-8")
        self.assertTrue(looks_like_yostar_product_json(raw))
        products = parse_yostar_product_json(
            raw, page_url="https://shop.yostar.co.jp/products/detail/5232"
        )
        self.assertEqual(len(products), 1)
        p = products[0]
        self.assertIn("アクリルスタンド", p["name"])
        self.assertEqual(p["unit_cost"], 1980.0)
        self.assertEqual(p["product_id"], "5232")
        self.assertEqual(p["release_date"], "2026-08")
        self.assertTrue(p["image_url"].startswith("http"))

        data = __import__("json").loads(raw)["data"]
        again = product_from_api_data(
            data, page_url="https://shop.yostar.co.jp/products/detail/5232"
        )
        self.assertEqual(again[0]["unit_cost"], 1980.0)

    def test_order_fixture(self) -> None:
        raw = ORDER_FIXTURE.read_text(encoding="utf-8")
        self.assertTrue(looks_like_yostar_order_json(raw))
        parsed = parse_yostar_order_json(raw)
        self.assertEqual(parsed["order_ref"], "YO20260913001")
        self.assertEqual(parsed["shipping_fee"], 700.0)
        self.assertEqual(parsed["order_total"], 6640.0)
        products = parsed["products"]
        self.assertEqual(len(products), 3)
        self.assertEqual(sum(int(p["qty"]) for p in products), 4)
        by_id = {p["product_id"]: p for p in products}
        self.assertEqual(by_id["5232"]["qty"], 2)
        self.assertEqual(by_id["5232"]["unit_cost"], 1980.0)

    def test_spa_shell(self) -> None:
        html = SHELL_FIXTURE.read_text(encoding="utf-8")
        self.assertTrue(is_yostar_spa_shell_html(html))

    def test_scrape_html_document_order(self) -> None:
        raw = ORDER_FIXTURE.read_text(encoding="utf-8")
        result = asyncio.run(scrape_html_document(raw))
        self.assertEqual(len(result["products"]), 3)
        self.assertEqual(result["order_ref"], "YO20260913001")
        self.assertEqual(result["shipping_fee"], 700.0)
        self.assertIn("yostar", result["message"].lower())

    def test_scrape_html_document_shell(self) -> None:
        html = SHELL_FIXTURE.read_text(encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(scrape_html_document(html))
        self.assertIn("SPA", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
