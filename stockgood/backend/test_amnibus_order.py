"""amnibus.com historyCard order scrape tests."""

from __future__ import annotations

import asyncio
import unittest

from app.scrapers.amnibus import is_amnibus_order_html, parse_amnibus_order_html
from app.scrapers.preview import scrape_html_document

FIXTURE = """
<div class="historyCard boxCard">
  <div class="historyCardHeader">
    <div class="historyCardHeader__orderDate">
      <p class="historyCardHeader__orderDate--title">注文日</p>
      <p class="historyCardHeader__orderDate--value">2026/07/17</p>
    </div>
    <div class="historyCardHeader__total">
      <p class="historyCardHeader__total--title">合計</p>
      <p class="historyCardHeader__total--value">¥ 78,650(税込)</p>
    </div>
    <div class="historyCardHeader__orderNumber">
      <p>注文番号：2251600</p>
    </div>
  </div>
  <div class="historyCardOrderStatus__deliverySchedule">
    <p>お届け予定日：<span>2026年9月中旬より順次発送</span></p>
  </div>
  <div class="historyCardItems">
    <div class="historyCardItemContainer">
      <a href="https://amnibus.com/products/detail/111868">
        <img src="https://cdn.amnibus.com/upload/save_image/111868.jpg">
      </a>
      <a class="historyCardItemContainer__detail--artworkTitle" href="https://amnibus.com/products/title/1858">ブルーアーカイブ</a>
      <a class="historyCardItemContainer__productName" href="https://amnibus.com/products/detail/111868">トレーディンググリッター缶バッジ</a>
      <p class="historyCardItemContainer__detail--className">単位：BOX</p>
      <p class="historyCardItemContainer__detail--productNumber">商品コード：00228904</p>
      <div class="historyCardItemContainer__priceQuantity--price"><p>¥ 6,050(税込)</p></div>
      <div class="historyCardItemContainer__priceQuantity--quantity"><p>13個</p></div>
    </div>
    <div class="historyCardItemContainer__accordionContainer" style="display: none;">
      <div class="historyCardItemContainer">
        <img src="https://cdn.amnibus.com/upload/save_image/sp12620.jpg" alt="便利屋68 75mmグリッター缶バッジ AMNIBUS＆アニメイト限定特典">
        <p class="historyCardItemContainer__productName">便利屋68 75mmグリッター缶バッジ AMNIBUS＆アニメイト限定特典</p>
        <p class="historyCardItemContainer__detail--productNumber">景品コード：sp12620</p>
        <div class="historyCardItemContainer__priceQuantity--price"><p>&nbsp;</p></div>
        <div class="historyCardItemContainer__priceQuantity--quantity"><p>13個</p></div>
      </div>
    </div>
  </div>
  <div class="historyCardInfo__accordionContainer--fee">
    <dl>
      <dt>料金</dt>
      <dd>小計：¥ 78,650</dd>
      <dd>合計：¥ 78,650(税込)</dd>
    </dl>
  </div>
</div>
"""

TWO_CARDS = FIXTURE + """
<div class="historyCard">
  <div class="historyCardHeader__orderNumber"><p>注文番号：2251601</p></div>
  <div class="historyCardItemContainer">
    <a href="https://amnibus.com/products/detail/1" class="historyCardItemContainer__productName">別商品</a>
    <div class="historyCardItemContainer__priceQuantity--price"><p>¥ 100</p></div>
    <div class="historyCardItemContainer__priceQuantity--quantity"><p>1個</p></div>
  </div>
</div>
"""


class AmnibusOrderParseTests(unittest.TestCase):
    def test_unit_price_not_order_total(self) -> None:
        self.assertTrue(is_amnibus_order_html(FIXTURE))
        parsed = parse_amnibus_order_html(FIXTURE)
        self.assertEqual(parsed["order_ref"], "2251600")
        self.assertEqual(parsed["shipping_fee"], 0.0)
        self.assertEqual(parsed["order_total"], 78650.0)
        self.assertEqual(len(parsed["products"]), 2)
        box = parsed["products"][0]
        self.assertEqual(box["name"], "トレーディンググリッター缶バッジ (BOX)")
        self.assertEqual(box["qty"], 13)
        self.assertEqual(box["unit_cost"], 6050.0)
        self.assertEqual(box["barcode"], "")
        self.assertEqual(box["ip"], "ブルーアーカイブ")
        self.assertEqual(box["shop"], "amnibus.com")
        self.assertEqual(box["source_url"], "https://amnibus.com/products/detail/111868")
        self.assertEqual(box["image_url"], "https://cdn.amnibus.com/upload/save_image/111868.jpg")
        self.assertEqual(box["product_id"], "00228904")
        self.assertEqual(box["expected_ship_at"], "2026-09")
        self.assertEqual(box["expected_ship_period"], "mid")
        prize = parsed["products"][1]
        self.assertEqual(prize["qty"], 13)
        self.assertEqual(prize["unit_cost"], 0.0)
        self.assertEqual(prize["product_id"], "sp12620")
        self.assertEqual(prize["source_url"], "")
        self.assertIn("限定特典", prize["name"])

    def test_two_cards_are_not_merged(self) -> None:
        parsed = parse_amnibus_order_html(TWO_CARDS)
        self.assertTrue(parsed["multi"])
        self.assertEqual(parsed["products"], [])
        self.assertEqual(parsed["order_ref"], "")

    def test_scrape_html_document(self) -> None:
        result = asyncio.run(scrape_html_document(FIXTURE))
        self.assertEqual(result["order_ref"], "2251600")
        self.assertEqual(result["shipping_fee"], 0.0)
        self.assertEqual(result["order_total"], 78650.0)
        self.assertEqual(result["products"][0]["unit_cost"], 6050.0)
        self.assertEqual(result["products"][0]["qty"], 13)
        self.assertIn("amnibus", result["message"])
        self.assertIn("2251600", result["message"])


if __name__ == "__main__":
    unittest.main()
