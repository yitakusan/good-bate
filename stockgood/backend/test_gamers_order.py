"""gamers.co.jp order history: line total / qty, JAN from the product page."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from app.scrapers.animate import is_animate_order_history_html
from app.scrapers.gamers import (
    fill_gamers_barcodes,
    is_gamers_order_history_html,
    jan_from_gamers_product_html,
    parse_gamers_order_history_html,
)
from app.scrapers.jan import canonicalize_jan
from app.scrapers.preview import scrape_html_document

ORDER = """
<div class="order_histories">
  <div class="order">
    <div class="order_status">
      <p><span>注文番号 : </span>24127701</p>
    </div>
    <div class="order_inner">
      <div class="order_item cf">
        <div class="order_item_img">
          <a href="/pn/reia/pd/10919972/"><img src="https://tc-gamers.techorus-cdn.com/resize_image/resize_image.php?image=07301633_6a6afe60a7adb.jpg&amp;width=130" alt="レイヤ"></a>
        </div>
        <div class="order_item_info">
          <h3><a href="/pn/reia/pd/10919972/">BanG Dream! アクリルスタンド レイヤ</a></h3>
          <p class="num">2点</p>
          <p class="price">3,520円</p>
        </div>
      </div>
      <div class="order_item cf">
        <div class="order_item_img">
          <a href="/pn/rock/pd/10919973/"><img src="https://tc-gamers.techorus-cdn.com/resize_image/resize_image.php?image=07301634_6a6afe7032cae.jpg&amp;width=130" alt="ロック"></a>
        </div>
        <div class="order_item_info">
          <h3><a href="/pn/rock/pd/10919973/">BanG Dream! アクリルスタンド ロック</a></h3>
          <p class="num">5点</p>
          <p class="price">8,800円</p>
        </div>
      </div>
      <div class="order_footer">
        <p class="number"><span>配送伝票番号：988800000001</span></p>
      </div>
    </div>
    <div class="order_bill">
      <table>
        <tr><th>商品小計</th><td>12,320円</td></tr>
        <tr><th>配送料・手数料</th><td>0円</td></tr>
        <tr><th>注文合計金額</th><td>12,320円</td></tr>
      </table>
    </div>
    <p>【ゲーマーズ】ご注文の確認</p>
  </div>
</div>
"""

PRODUCT = """
<html><body>
<a href="javascript:void(0);" id="opener_sp" class="relation_keyword">店舗予約用バーコード：{jan}</a>
</body></html>
"""


def _jan(body: str) -> str:
    for digit in "0123456789":
        jan = canonicalize_jan(body + digit)
        if jan:
            return jan
    raise AssertionError(body)


JAN_A = _jan("457019449838")
JAN_B = _jan("457019449839")


class GamersOrderTests(unittest.TestCase):
    def test_not_animate_and_line_total_is_not_unit(self) -> None:
        self.assertTrue(is_gamers_order_history_html(ORDER))
        self.assertFalse(is_animate_order_history_html(ORDER))
        parsed = parse_gamers_order_history_html(ORDER)
        self.assertEqual(parsed["order_ref"], "24127701")
        self.assertEqual(parsed["shipping_fee"], 0.0)
        self.assertEqual(parsed["order_total"], 12320.0)
        self.assertEqual(len(parsed["products"]), 2)
        first, second = parsed["products"]
        self.assertEqual(first["qty"], 2)
        self.assertEqual(first["unit_cost"], 1760.0)
        self.assertEqual(first["barcode"], "")
        self.assertEqual(first["product_id"], "10919972")
        self.assertEqual(
            first["source_url"], "https://www.gamers.co.jp/pn/reia/pd/10919972/"
        )
        self.assertIn("07301633_", first["image_url"])
        self.assertEqual(second["qty"], 5)
        self.assertEqual(second["unit_cost"], 1760.0)
        self.assertNotIn("988800000001", parsed["order_ref"])

    def test_product_page_barcode(self) -> None:
        self.assertEqual(JAN_A, "4570194498380")
        html = PRODUCT.format(jan=JAN_A)
        self.assertEqual(jan_from_gamers_product_html(html), JAN_A)
        self.assertEqual(jan_from_gamers_product_html("<html></html>"), "")

    def test_fill_and_scrape_document(self) -> None:
        parsed = parse_gamers_order_history_html(ORDER)
        pages = {
            "https://www.gamers.co.jp/pn/reia/pd/10919972/": PRODUCT.format(jan=JAN_A),
            "https://www.gamers.co.jp/pn/rock/pd/10919973/": PRODUCT.format(jan=JAN_B),
        }

        async def fetch_html(url: str) -> str:
            return pages[url]

        filled = asyncio.run(fill_gamers_barcodes(parsed["products"], fetch_html))
        self.assertEqual(filled, 2)
        self.assertEqual(parsed["products"][0]["barcode"], JAN_A)
        self.assertEqual(parsed["products"][1]["barcode"], JAN_B)

        class _Resp:
            def __init__(self, url: str) -> None:
                self.status_code = 200
                self.text = pages[url]

        class _Client:
            def __init__(self, *args: object, **kwargs: object) -> None:
                pass

            async def __aenter__(self) -> "_Client":
                return self

            async def __aexit__(self, *args: object) -> bool:
                return False

            async def get(self, url: str, **kwargs: object) -> _Resp:
                return _Resp(url)

        with patch("app.scrapers.preview.httpx.AsyncClient", _Client):
            result = asyncio.run(scrape_html_document(ORDER))
        self.assertEqual(result["order_ref"], "24127701")
        self.assertEqual(result["shipping_fee"], 0.0)
        self.assertEqual(result["order_total"], 12320.0)
        self.assertEqual(result["products"][0]["barcode"], JAN_A)
        self.assertEqual(result["products"][1]["barcode"], JAN_B)
        self.assertIn("ゲーマーズ", result["message"])
        self.assertIn("JAN", result["message"])


if __name__ == "__main__":
    unittest.main()
