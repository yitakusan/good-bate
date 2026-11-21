"""shop.yostar.co.jp（Yostar OFFICIAL SHOP）ORDER_IMPORT tests."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from app.scrapers.preview import scrape_html_document
from app.scrapers.yostar import (
    is_yostar_order_detail_html,
    is_yostar_spa_shell_html,
    is_yostar_url,
    looks_like_yostar_order_json,
    looks_like_yostar_product_json,
    parse_yostar_order_html,
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

    def test_rendered_order_detail_html(self) -> None:
        html = """
        <html><head><title>Yostar OFFICIAL SHOP</title></head><body>
        <div class="order-detail-container">
          <div class="info-base-item"><label>ご注文番号</label><span>YOHTML9001</span></div>
          <div class="delivery-item">
            <img class="delivery-item-img" src="https://webusstatic.yo-star.com/pubplat/a.jpg" alt="">
            <a href="/products/detail/9001">アクリルスタンド アーミヤ</a>
            <div class="price-single"><span class="price-number">￥2,200</span><i class="icon-multiply">x</i>16</div>
            <p class="price-total">小計：<span>￥35,200</span></p>
            <div class="dilivery-hint">お届け予定日：2026年10月頃より順次発送開始（予定）</div>
          </div>
          <div class="delivery-item">
            <img class="delivery-item-img" src="https://webusstatic.yo-star.com/pubplat/b.jpg" alt="">
            <a href="/products/detail/9002">アクリルスタンド レイ</a>
            <div class="price-single"><span class="price-number">￥2,200</span>x5</div>
            <p class="price-total">小計：￥11,000</p>
          </div>
          <div class="delivery-item">
            <a href="/products/detail/9003">アクリルスタンド ハルカ</a>
            <div class="price-single"><span>￥2,200</span>x15</div>
            <p class="price-total">小計：￥33,000</p>
          </div>
          <div class="delivery-item">
            <a href="/products/detail/9004">缶バッジセット</a>
            <div class="price-single"><span>￥1,650</span>x11</div>
            <p class="price-total">小計：￥18,150</p>
          </div>
          <div class="mail-content">伝票番号：988800000001 商品名：邮件里的重复商品 単価：￥1 数量：99 送料：￥500 合計：￥1</div>
        </div>
        <div class="order-summary">
          <div class="summary-item"><span>小計</span><span>￥97,350</span></div>
          <div class="summary-item"><span>手数料</span><span>￥0</span></div>
          <div class="summary-item"><span>送料</span><span>￥0</span></div>
          <div class="summary-total"></div>
          <div class="summary-total">合計 ￥97,350 税込</div>
        </div>
        </body></html>
        """
        self.assertTrue(is_yostar_order_detail_html(html))
        self.assertFalse(is_yostar_spa_shell_html(html))
        parsed = parse_yostar_order_html(html)
        self.assertEqual(parsed["order_ref"], "YOHTML9001")
        self.assertEqual(parsed["shipping_fee"], 0.0)
        self.assertEqual(parsed["order_total"], 97350.0)
        products = parsed["products"]
        self.assertEqual(len(products), 4)
        self.assertEqual(sum(int(p["qty"]) for p in products), 47)
        by_id = {p["product_id"]: p for p in products}
        self.assertEqual(by_id["9001"]["unit_cost"], 2200.0)
        self.assertEqual(by_id["9001"]["qty"], 16)
        self.assertNotEqual(by_id["9001"]["unit_cost"], 35200.0)
        self.assertEqual(by_id["9001"]["expected_ship_at"], "2026-10")
        self.assertEqual(by_id["9001"]["barcode"], "")
        self.assertIn("/pubplat/a.jpg", by_id["9001"]["image_url"])
        self.assertEqual(by_id["9004"]["unit_cost"], 1650.0)
        self.assertEqual(by_id["9004"]["qty"], 11)
        self.assertTrue(by_id["9001"]["source_url"].endswith("/products/detail/9001"))
        names = " ".join(p["name"] for p in products)
        self.assertNotIn("邮件", names)
        self.assertNotIn("988800000001", parsed["order_ref"])

        result = asyncio.run(scrape_html_document(html))
        self.assertEqual(result["order_ref"], "YOHTML9001")
        self.assertEqual(result["shipping_fee"], 0.0)
        self.assertEqual(result["order_total"], 97350.0)
        self.assertEqual(len(result["products"]), 4)

    def test_scrape_html_document_shell(self) -> None:
        html = SHELL_FIXTURE.read_text(encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(scrape_html_document(html))
        self.assertIn("SPA", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
