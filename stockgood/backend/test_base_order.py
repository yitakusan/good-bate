"""BASE dynamic_receipts scrape tests.

Fixture keeps item rows and order totals only. No buyer, address, phone, or tracking.
"""

from __future__ import annotations

import asyncio
import unittest

from app.scrapers.preview import scrape_html_document
from app.scrapers.thebase import is_thebase_receipt_html, parse_thebase_receipt_html

FIXTURE = """
<html lang="ja" data-scope-controller="dynamicreceipts">
<body>
<input type="hidden" id="x_shop_id" value="twice2022-base-shop">
<input type="hidden" id="x_uniqueKey" value="28F3DDF68B36208F">
<table class="orderInfoTable">
  <tr><th>注文ID</th><td>28F3DDF68B36208F</td></tr>
  <tr><th>氏名</th><td>テスト 購入者</td></tr>
  <tr class="noborder"><th>合計金額</th><td>¥16,550</td></tr>
  <tr><td colspan="2">
    <ul class="c-box chargeBreakdown">
      <li class="chargeBreakdown__item">
        <div class="chargeBreakdown__name">商品小計</div><div>¥16,040</div>
      </li>
      <li class="chargeBreakdown__item">
        <div class="chargeBreakdown__name">送料</div><div>¥510</div>
      </li>
    </ul>
  </td></tr>
</table>
<table class="itemList">
  <thead><tr><td>商品</td><td>商品単価</td><td>個数</td></tr></thead>
  <tbody>
    <tr>
      <td class="itemList__item">
        <a class="itemList__imgContainer" href="http://shop.chara-pic.com/items/152245833">
          <img class="itemList__img" src="https://baseec-img-mng.akamaized.net/images/item/origin/stand.png">
        </a>
        <a class="itemList__title" href="http://shop.chara-pic.com/items/152245833">
          <span class="itemList__titleClamp">アクリルスタンド</span>
        </a>
        <p class="itemList__additionalInfo">九條 都</p>
      </td>
      <td>¥1,970</td>
      <td>1点</td>
      <td class="itemList__shippingFee">宅急便</td>
    </tr>
    <tr>
      <td class="itemList__item">
        <a class="itemList__title" href="http://shop.chara-pic.com/items/152245833">
          <span class="itemList__titleClamp">アクリルスタンド</span>
        </a>
        <p class="itemList__additionalInfo">新海 天</p>
      </td>
      <td>¥1,970</td>
      <td>1点</td>
    </tr>
    <tr>
      <td class="itemList__item">
        <a class="itemList__title" href="http://shop.chara-pic.com/items/152268197">
          <span class="itemList__titleClamp">アクリルスタンド 九條都 2025年イラストver</span>
        </a>
      </td>
      <td>¥1,970</td>
      <td>2点</td>
    </tr>
    <tr>
      <td class="itemList__item">
        <a class="itemList__title" href="http://shop.chara-pic.com/items/152246975">
          <span class="itemList__titleClamp">和泉つばすVer.絵馬　如月結那</span>
        </a>
      </td>
      <td>¥2,280</td>
      <td>2点</td>
    </tr>
    <tr>
      <td class="itemList__item">
        <a class="itemList__title" href="http://shop.chara-pic.com/items/152247194">
          <span class="itemList__titleClamp">御朱印帳</span>
        </a>
      </td>
      <td>¥3,600</td>
      <td>1点</td>
    </tr>
  </tbody>
</table>
</body>
</html>
"""

EN_FIXTURE = """
<html data-scope-controller="dynamicreceipts">
<input id="x_uniqueKey" value="28F0EB8F6D842EA0">
<table class="orderInfoTable">
  <tr><th>Order ID</th><td>28F0EB8F6D842EA0</td></tr>
  <tr><th>Total</th><td>¥1,100</td></tr>
  <tr><td>
    <ul class="chargeBreakdown">
      <li class="chargeBreakdown__item">
        <div class="chargeBreakdown__name">Shipping fee</div><div>¥550</div>
      </li>
    </ul>
  </td></tr>
</table>
<table class="itemList"><tbody>
  <tr>
    <td class="itemList__item">
      <a class="itemList__title" href="https://example-shop.example/items/100001">
        <span class="itemList__titleClamp">Sample badge</span>
      </a>
    </td>
    <td>¥550</td>
    <td>2qty</td>
  </tr>
</tbody></table>
</html>
"""


class BaseOrderParseTests(unittest.TestCase):
    def test_variations_stay_separate(self) -> None:
        self.assertTrue(is_thebase_receipt_html(FIXTURE))
        self.assertFalse(is_thebase_receipt_html("<html><title>shop</title></html>"))
        parsed = parse_thebase_receipt_html(FIXTURE)
        self.assertEqual(parsed["order_ref"], "28F3DDF68B36208F")
        self.assertEqual(parsed["shipping_fee"], 510.0)
        self.assertEqual(parsed["order_total"], 16550.0)
        self.assertEqual(parsed["shop"], "shop.chara-pic.com")
        self.assertEqual(len(parsed["products"]), 5)
        names = [row["name"] for row in parsed["products"]]
        self.assertEqual(
            names[:2],
            ["アクリルスタンド (九條 都)", "アクリルスタンド (新海 天)"],
        )
        self.assertEqual(
            [row["qty"] for row in parsed["products"]],
            [1, 1, 2, 2, 1],
        )
        self.assertEqual(
            [row["unit_cost"] for row in parsed["products"]],
            [1970.0, 1970.0, 1970.0, 2280.0, 3600.0],
        )
        self.assertEqual(
            parsed["products"][0]["source_url"],
            parsed["products"][1]["source_url"],
        )
        self.assertNotIn("テスト", names[0])
        goods = sum(row["unit_cost"] * row["qty"] for row in parsed["products"])
        self.assertEqual(goods, 16040.0)
        self.assertEqual(goods + parsed["shipping_fee"], parsed["order_total"])
        self.assertEqual(parsed["products"][0]["barcode"], "")
        self.assertTrue(parsed["products"][0]["image_url"].endswith("stand.png"))

    def test_english_qty_label(self) -> None:
        parsed = parse_thebase_receipt_html(EN_FIXTURE)
        self.assertEqual(parsed["order_ref"], "28F0EB8F6D842EA0")
        self.assertEqual(parsed["shipping_fee"], 550.0)
        self.assertEqual(parsed["order_total"], 1100.0)
        self.assertEqual(len(parsed["products"]), 1)
        self.assertEqual(parsed["products"][0]["qty"], 2)
        self.assertEqual(parsed["products"][0]["unit_cost"], 550.0)
        self.assertEqual(parsed["products"][0]["shop"], "example-shop.example")

    def test_scrape_html_document(self) -> None:
        result = asyncio.run(scrape_html_document(FIXTURE))
        self.assertEqual(result["order_ref"], "28F3DDF68B36208F")
        self.assertEqual(result["shipping_fee"], 510.0)
        self.assertEqual(result["order_total"], 16550.0)
        self.assertEqual(len(result["products"]), 5)
        self.assertEqual(sum(int(row["qty"]) for row in result["products"]), 7)
        self.assertIn("BASE", result["message"])
        self.assertIn("28F3DDF68B36208F", result["message"])
        self.assertNotIn("テスト", result["message"])


if __name__ == "__main__":
    unittest.main()
