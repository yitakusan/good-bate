"""online.aniplex.co.jp Order-Details scrape tests.

Fixture keeps product lines only. No address, phone, or account name.
"""

from __future__ import annotations

import asyncio
import unittest

from app.scrapers.aniplex import is_aniplex_order_html, parse_aniplex_order_html
from app.scrapers.preview import scrape_html_document

FIXTURE = """
<div class="page" data-action="Order-Details" data-querystring="orderID=A-06564650">
  <h1 class="page-title">注文番号:A-06564650</h1>
  <div class="deliveryDate">2026-10-30</div>
  <p class="shipping-discount-total">&yen; 660</p>
  <div class="total-summary__row order-total">
    <span class="grand-total-sum">&yen; 33,660</span>
  </div>
  <div class="product-summary__item">
    <div class="product-summary__item-image">
      <img src="/on/demandware.static/-/Sites-all-master-catalog/ja_JP/dwde2bdd4a/items/event/C102/bocchi-rocks/85_BTRC102_acms01.jpg" alt="goto">
    </div>
    <div class="product-summary__item-attributes">
      <div class="product-summary__item-title">【C108】アクリルマスコット（後藤ひとり）(再販) / ぼっち・ざ・ろっく！</div>
      <p class="attribute">MD23-0440001</p>
      <p class="attribute">アクリル雑貨</p>
      <p class="attribute">2026年10月より順次お届け予定</p>
    </div>
    <div class="product-summary__item-unit-price"><div class="price">&yen; 1,500</div></div>
    <div class="product-summary__item-quantity"><span class="value">5</span></div>
    <div class="pricing line-item-total-price-amount">&yen; 7,500</iselse></div>
  </div>
  <div class="product-summary__item">
    <div class="product-summary__item-image">
      <img src="/on/demandware.static/-/Sites-ANX-Site/ja_JP/x/85_BTRC102_acms02.jpg" alt="nijika">
    </div>
    <div class="product-summary__item-attributes">
      <div class="product-summary__item-title">【C108】アクリルマスコット（伊地知虹夏）(再販) / ぼっち・ざ・ろっく！</div>
      <p class="attribute">MD23-0440002</p>
      <p class="attribute">アクリル雑貨</p>
      <p class="attribute">2026年10月より順次お届け予定</p>
    </div>
    <div class="product-summary__item-unit-price"><div class="price">&yen; 1,500</div></div>
    <div class="product-summary__item-quantity"><span class="value">7</span></div>
  </div>
  <div class="product-summary__item">
    <div class="product-summary__item-attributes">
      <div class="product-summary__item-title">【C108】アクリルマスコット（山田リョウ）(再販) / ぼっち・ざ・ろっく！</div>
      <p class="attribute">MD23-0440003</p>
      <p class="attribute">2026年10月より順次お届け予定</p>
    </div>
    <div class="product-summary__item-unit-price"><div class="price">&yen; 1,500</div></div>
    <div class="product-summary__item-quantity"><span class="value">7</span></div>
  </div>
  <div class="product-summary__item">
    <div class="product-summary__item-attributes">
      <div class="product-summary__item-title">【C108】アクリルマスコット（喜多郁代）(再販) / ぼっち・ざ・ろっく！</div>
      <p class="attribute">MD23-0440004</p>
      <p class="attribute">2026年10月より順次お届け予定</p>
    </div>
    <div class="product-summary__item-unit-price"><div class="price">&yen; 1,500</div></div>
    <div class="product-summary__item-quantity"><span class="value">3</span></div>
  </div>
</div>
"""

TWO_ORDERS = FIXTURE + """
<div class="page" data-action="Order-Details" data-querystring="orderID=A-00000001">
  <h1 class="page-title">注文番号:A-00000001</h1>
</div>
"""


class AniplexOrderParseTests(unittest.TestCase):
    def test_unit_price_not_line_total(self) -> None:
        self.assertTrue(is_aniplex_order_html(FIXTURE))
        self.assertFalse(
            is_aniplex_order_html("<html><title>アニプレックス オンライン</title></html>")
        )
        parsed = parse_aniplex_order_html(FIXTURE)
        self.assertFalse(parsed["multi"])
        self.assertEqual(parsed["order_ref"], "A-06564650")
        self.assertEqual(parsed["shipping_fee"], 660.0)
        self.assertEqual(parsed["order_total"], 33660.0)
        self.assertEqual(len(parsed["products"]), 4)
        first = parsed["products"][0]
        self.assertEqual(first["qty"], 5)
        self.assertEqual(first["unit_cost"], 1500.0)
        self.assertEqual(first["product_id"], "MD23-0440001")
        self.assertEqual(first["barcode"], "")
        self.assertEqual(first["shop"], "online.aniplex.co.jp")
        self.assertEqual(first["ip"], "ぼっち・ざ・ろっく！")
        self.assertEqual(first["expected_ship_at"], "2026-10")
        self.assertIsNone(first["expected_ship_period"])
        self.assertTrue(first["image_url"].startswith("https://online.aniplex.co.jp/on/"))
        self.assertEqual(
            [row["qty"] for row in parsed["products"]],
            [5, 7, 7, 3],
        )
        self.assertEqual(
            [row["product_id"] for row in parsed["products"]],
            ["MD23-0440001", "MD23-0440002", "MD23-0440003", "MD23-0440004"],
        )

    def test_two_order_ids_are_not_merged(self) -> None:
        parsed = parse_aniplex_order_html(TWO_ORDERS)
        self.assertTrue(parsed["multi"])
        self.assertEqual(parsed["products"], [])
        self.assertEqual(parsed["order_ref"], "")

    def test_scrape_html_document(self) -> None:
        result = asyncio.run(scrape_html_document(FIXTURE))
        self.assertEqual(result["order_ref"], "A-06564650")
        self.assertEqual(result["shipping_fee"], 660.0)
        self.assertEqual(result["order_total"], 33660.0)
        self.assertEqual(len(result["products"]), 4)
        self.assertEqual(result["products"][0]["unit_cost"], 1500.0)
        self.assertEqual(result["products"][0]["qty"], 5)
        self.assertEqual(sum(int(row["qty"]) for row in result["products"]), 22)
        self.assertIn("aniplex", result["message"])
        self.assertIn("A-06564650", result["message"])


if __name__ == "__main__":
    unittest.main()
