"""movic.jp 購入履歴詳細 HTML order scrape tests."""

from __future__ import annotations

import asyncio
import unittest

from app.scrapers.movic import (
    image_url_from_goods_page,
    is_movic_order_detail_html,
    parse_movic_order_detail_html,
)
from app.scrapers.preview import scrape_html_document

FIXTURE = """
<html><head>
<title>購入履歴詳細｜ムービック（movic）</title>
<meta name="rooturl" content="https://www.movic.jp" />
<meta property="metatag:cart_item" content='[{&quot;goods&quot;:&quot;other-sku&quot;,&quot;qty&quot;:&quot;4&quot;,&quot;name&quot;:&quot;別商品&quot;,&quot;price&quot;:&quot;100&quot;,&quot;goods_photo_url&quot;:&quot;https://www.movic.jp/img/goods/S/4550621684388_1.jpg&quot;}]' />
</head>
<body class="page-historydetail">
<div class="block-purchase-history-detail">
  <h1>購入履歴詳細</h1>
  <table>
    <tr class="block-purchase-history-detail--order-id"><th>オーダーＩＤ</th><td>MV260902-033300193</td></tr>
  </table>
  <table class="block-purchase-history-detail--order-detail-items">
    <tr class="block-purchase-history-detail--order-detail-item">
      <td>
        <div class="block-purchase-history-detail--goods-name">ペルソナ P25th復刻アート メタリュクスバッジコレクション／B</div>
        <div class="block-purchase-history-detail--goods-code">00664-00603-00233</div>
      </td>
      <td><div class="block-purchase-history-detail--goods-qty">5</div></td>
      <td><div class="block-purchase-history-detail--goods-total-price">26,950円</div></td>
    </tr>
  </table>
  <table>
    <tr class="block-purchase-history-detail--items-total"><th>商品金額合計</th><td>26,950円</td></tr>
    <tr class="block-purchase-history-detail--shipping-fee"><th>送料</th><td>0円</td></tr>
    <tr class="block-purchase-history-detail--fee"><th>手数料</th><td>220円</td></tr>
    <tr class="block-purchase-history-detail--order-total">
      <th>支払金額合計</th>
      <td>27,170円<div>10%対象 27,170円</div></td>
    </tr>
  </table>
  <tr class="block-purchase-history-detail--delivey-plan-dt">
    <th>配送予定日</th><td>2026年9月19日頃発売予定</td>
  </tr>
  <table class="block-purchase-history-detail--shipment-items">
    <tr><td><a href="/shop/g/g00664-00603-00233/"><div>ペルソナ P25th復刻アート メタリュクスバッジコレクション／B</div></a></td></tr>
    <tr class="block-purchase-history-detail--destination-shipment-qty"><th>数量</th><td>5</td></tr>
  </table>
</div>
</body></html>
"""

TWO_LINES = """
<html><body class="page-historydetail">
<div class="block-purchase-history-detail">
  <h1>購入履歴詳細</h1>
  <p>https://www.movic.jp/shop/customer/historydetail.aspx</p>
  <tr class="block-purchase-history-detail--order-id"><td>MV0001</td></tr>
  <table class="block-purchase-history-detail--order-detail-items">
    <tr class="block-purchase-history-detail--order-detail-item">
      <td><div class="block-purchase-history-detail--goods-name">徽章A</div>
          <div class="block-purchase-history-detail--goods-code">aaa-1</div></td>
      <td><div class="block-purchase-history-detail--goods-qty">2</div></td>
      <td><div class="block-purchase-history-detail--goods-total-price">1,000円</div></td>
    </tr>
    <tr class="block-purchase-history-detail--order-detail-item">
      <td><div class="block-purchase-history-detail--goods-name">徽章B</div>
          <div class="block-purchase-history-detail--goods-code">bbb-2</div></td>
      <td><div class="block-purchase-history-detail--goods-qty">1</div></td>
      <td><div class="block-purchase-history-detail--goods-total-price">300円</div></td>
    </tr>
  </table>
  <tr class="block-purchase-history-detail--shipping-fee"><td>550円</td></tr>
  <tr class="block-purchase-history-detail--order-total"><td>1,850円</td></tr>
</div>
</body></html>
"""

LIST_PAGE = """
<html><body class="page-history">
<div class="block-purchase-history">
  <h1>購入履歴</h1>
  <a href="https://www.movic.jp/shop/customer/historydetail.aspx?order_id=MV1">MV1</a>
  <div class="block-purchase-history--goods-name">仅品名</div>
  <td>27,170円</td>
</div>
</body></html>
"""


KADOKAWA = """
<html><head>
<title>購入履歴詳細 | カドスト</title>
<meta name="rooturl" content="https://store.kadokawa.co.jp" />
</head>
<body class="page-historydetail">
<div class="block-purchase-history-detail">
  <h1>購入履歴詳細</h1>
  <table>
    <tr><th>注文コード</th><td class="block-purchase-history-detail--order-id">260629KD0102540</td></tr>
  </table>
  <table class="block-purchase-history-detail--order-detail-items">
    <tr>
      <td><div class="block-purchase-history-detail--goods-code">302507001801</div></td>
      <td><div class="block-purchase-history-detail--goods-name">缶バッジ BOX</div>
          <div class="variation-name">（BOX）</div></td>
      <td><div class="block-purchase-history-detail--goods-qty">&nbsp;5</div></td>
      <td><div class="block-purchase-history-detail--goods-total-price">&nbsp;15,400円</div></td>
    </tr>
    <tr>
      <td><div class="block-purchase-history-detail--goods-code">kad0000002289</div></td>
      <td><div class="block-purchase-history-detail--goods-name">購入特典クリアカード</div>
          <div class="variation-name"></div></td>
      <td><div class="block-purchase-history-detail--goods-qty">&nbsp;4</div></td>
      <td><div class="block-purchase-history-detail--goods-total-price">&nbsp;0円</div></td>
    </tr>
    <tr>
      <td><div class="block-purchase-history-detail--goods-code">4984995909905</div></td>
      <td><div class="block-purchase-history-detail--goods-name">P5X 缶バッジ（BOX）</div>
          <div class="variation-name">（BOX）</div></td>
      <td><div class="block-purchase-history-detail--goods-qty">&nbsp;10</div></td>
      <td><div class="block-purchase-history-detail--goods-total-price">&nbsp;49,500円</div></td>
    </tr>
  </table>
  <table class="block-purchase-history-detail--payment-info-items">
    <tr><th>送料</th><td class="block-purchase-history-detail--shipping-fee">1,320円</td></tr>
    <tr><th>手数料</th><td class="block-purchase-history-detail--fee">0円</td></tr>
    <tr><th>注文金額合計</th><td class="block-purchase-history-detail--order-total">66,220円</td></tr>
  </table>
  <div class="block-purchase-history-detail--shipment-item">
    <h2>配送1</h2>
    <table class="block-purchase-history-detail--shipment-items">
      <tr><td><a href="/shop/g/g302507001801/">缶バッジ BOX</a></td><td>5</td></tr>
    </table>
    <table>
      <tr><th>送り状No</th><td class="block-purchase-history-detail--shipping-fee">495700000001</td></tr>
      <tr><th>送料</th><td class="block-purchase-history-detail--shipping-fee">660円</td></tr>
    </table>
  </div>
</div>
</body></html>
"""


class MovicOrderDetailParseTests(unittest.TestCase):
    def test_detect_detail_not_list(self) -> None:
        self.assertTrue(is_movic_order_detail_html(FIXTURE))
        self.assertFalse(is_movic_order_detail_html(LIST_PAGE))

    def test_line_total_is_not_unit_and_ignores_cart_meta(self) -> None:
        parsed = parse_movic_order_detail_html(FIXTURE)
        products = parsed["products"]
        self.assertEqual(len(products), 1)
        item = products[0]
        self.assertEqual(item["name"], "ペルソナ P25th復刻アート メタリュクスバッジコレクション／B")
        self.assertEqual(item["qty"], 5)
        self.assertEqual(item["unit_cost"], 5390.0)
        self.assertEqual(item["barcode"], "")
        self.assertEqual(item["shop"], "movic.jp")
        self.assertEqual(
            item["source_url"],
            "https://www.movic.jp/shop/g/g00664-00603-00233/",
        )
        self.assertEqual(item["expected_ship_at"], "2026-09-19")
        self.assertNotIn("別商品", item["name"])
        self.assertEqual(parsed["order_ref"], "MV260902-033300193")
        self.assertEqual(parsed["shipping_fee"], 0.0)
        self.assertEqual(parsed["handling_fee"], 220.0)
        self.assertEqual(parsed["order_total"], 27170.0)

    def test_two_lines(self) -> None:
        parsed = parse_movic_order_detail_html(TWO_LINES)
        by_name = {p["name"]: p for p in parsed["products"]}
        self.assertEqual(by_name["徽章A"]["qty"], 2)
        self.assertEqual(by_name["徽章A"]["unit_cost"], 500.0)
        self.assertEqual(by_name["徽章B"]["unit_cost"], 300.0)
        self.assertEqual(parsed["shipping_fee"], 550.0)
        self.assertEqual(parsed["order_total"], 1850.0)

    def test_scrape_html_document(self) -> None:
        result = asyncio.run(scrape_html_document(FIXTURE))
        self.assertEqual(len(result["products"]), 1)
        self.assertEqual(result["order_ref"], "MV260902-033300193")
        self.assertEqual(result["shipping_fee"], 0.0)
        self.assertEqual(result["order_total"], 27170.0)
        self.assertEqual(result["products"][0]["barcode"], "")
        self.assertIn("ムービック", result["message"])
        self.assertIn("手续费", result["message"])

    def test_kadokawa_detail_uses_order_shipping_and_valid_jan(self) -> None:
        self.assertTrue(is_movic_order_detail_html(KADOKAWA))
        parsed = parse_movic_order_detail_html(KADOKAWA)
        self.assertEqual(parsed["order_ref"], "260629KD0102540")
        self.assertEqual(parsed["shipping_fee"], 1320.0)
        self.assertEqual(parsed["handling_fee"], 0.0)
        self.assertEqual(parsed["order_total"], 66220.0)
        self.assertEqual(len(parsed["products"]), 3)
        by_code = {p["product_id"]: p for p in parsed["products"]}
        box = by_code["302507001801"]
        self.assertEqual(box["qty"], 5)
        self.assertEqual(box["unit_cost"], 3080.0)
        self.assertEqual(box["barcode"], "")
        self.assertIn("（BOX）", box["name"])
        self.assertEqual(box["shop"], "store.kadokawa.co.jp")
        self.assertEqual(
            box["source_url"],
            "https://store.kadokawa.co.jp/shop/g/g302507001801/",
        )
        bonus = by_code["kad0000002289"]
        self.assertEqual(bonus["qty"], 4)
        self.assertEqual(bonus["unit_cost"], 0.0)
        self.assertEqual(bonus["barcode"], "")
        jan_line = by_code["4984995909905"]
        self.assertEqual(jan_line["qty"], 10)
        self.assertEqual(jan_line["unit_cost"], 4950.0)
        self.assertEqual(jan_line["barcode"], "4984995909905")
        self.assertEqual(jan_line["name"].count("（BOX）"), 1)
        result = asyncio.run(scrape_html_document(KADOKAWA))
        self.assertEqual(result["shipping_fee"], 1320.0)
        self.assertIn("カドスト", result["message"])
        self.assertIn("JAN", result["message"])

    def test_goods_page_image_prefers_large_and_skips_banner(self) -> None:
        html = """
        <html><head>
        <meta property="og:image" content="https://store.kadokawa.co.jp/img/goods/L/4984995909905.jpg">
        </head><body>
        <img src="/img/usr/banner/00.jpg">
        <img src="/img/goods/1/4984995909905.jpg" class="js-img-source">
        <img src="/img/goods/L/4984995909905.jpg" class="js-img-source">
        </body></html>
        """
        self.assertEqual(
            image_url_from_goods_page(
                html, "https://store.kadokawa.co.jp/shop/g/g4984995909905/"
            ),
            "https://store.kadokawa.co.jp/img/goods/L/4984995909905.jpg",
        )
        self.assertEqual(image_url_from_goods_page("<html></html>", "https://store.kadokawa.co.jp/"), "")


if __name__ == "__main__":
    unittest.main()
