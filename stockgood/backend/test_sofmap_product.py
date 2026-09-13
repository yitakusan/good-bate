"""sofmap.com product-detail scrape tests."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from app.scrapers.preview import scrape_html_document, scrape_url
from app.scrapers.sofmap import (
    canonicalize_sofmap_product_url,
    is_sofmap_product_url,
    looks_like_sofmap_html,
    parse_sofmap_product_html,
)

FIXTURE = (
    Path(__file__).resolve().parent
    / "app"
    / "scrapers"
    / "templates"
    / "sofmap.product.fixture.html"
)
SAMPLE_URL = "https://a.sofmap.com/product_detail.aspx?sku=102018397"


class SofmapProductParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = FIXTURE.read_text(encoding="utf-8")

    def test_detect_url_and_html(self) -> None:
        self.assertTrue(is_sofmap_product_url(SAMPLE_URL))
        self.assertTrue(
            is_sofmap_product_url(
                "https://a.sofmap.com/product_detail_sp.aspx?sku=102018397"
            )
        )
        self.assertFalse(
            is_sofmap_product_url("https://a.sofmap.com/category.aspx?gid=1")
        )
        self.assertTrue(looks_like_sofmap_html(self.html))

    def test_canonicalize_keeps_sku(self) -> None:
        self.assertEqual(
            canonicalize_sofmap_product_url(
                "https://a.sofmap.com/product_detail.aspx?sku=102018397&ref=x#frag"
            ),
            SAMPLE_URL,
        )

    def test_parse_fixture(self) -> None:
        product = parse_sofmap_product_html(self.html, SAMPLE_URL)
        assert product is not None
        self.assertIn("メタリック缶バッジ", product["name"])
        self.assertEqual(product["shop"], "sofmap.com")
        self.assertEqual(product["unit_cost"], 550.0)
        self.assertEqual(product["barcode"], "4580814642321")
        self.assertIn("image.sofmap.com", product["image_url"])
        self.assertNotIn("ogp", product["image_url"].lower())
        self.assertEqual(product["source_url"], SAMPLE_URL)
        self.assertEqual(product["expected_ship_at"], "2026-09")
        self.assertEqual(product["expected_ship_period"], "early")

    def test_scrape_html_document(self) -> None:
        result = asyncio.run(scrape_html_document(self.html, SAMPLE_URL))
        self.assertEqual(len(result["products"]), 1)
        self.assertEqual(result["products"][0]["barcode"], "4580814642321")
        self.assertIn("sofmap", result["message"].lower())


class SofmapLiveFetchTests(unittest.TestCase):
    def test_scrape_url_live(self) -> None:
        try:
            result = asyncio.run(scrape_url(SAMPLE_URL))
        except Exception as exc:  # network / block blocks
            self.skipTest(f"live sofmap fetch unavailable: {exc}")
        self.assertEqual(len(result["products"]), 1)
        product = result["products"][0]
        self.assertEqual(product["barcode"], "4580814642321")
        self.assertEqual(product["unit_cost"], 550.0)
        self.assertIn("image.sofmap.com", product["image_url"])


if __name__ == "__main__":
    unittest.main()
