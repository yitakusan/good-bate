"""Yahoo!ショッピング 注文履歴詳細 HTML order scrape tests."""

from __future__ import annotations

import asyncio
import unittest

from app.scrapers.preview import scrape_html_document
from app.scrapers.yahoo_shopping import (
    is_yahoo_shopping_order_html,
    parse_yahoo_shopping_order_html,
)

FIXTURE = """
<html><head><title>注文履歴詳細 - Yahoo!ショッピング</title></head>
<body>
<div class="mdOrderNumber">
  <li class="elOrderNumber">
    <dt>注文番号</dt>
    <dd><ul class="elOrderList"><li>example-store-10000001</li></ul></dd>
  </li>
</div>
<div class="mdOrderItem" id="orddtl">
  <h2>ご注文商品</h2>
  <ul class="elList">
    <li><dl class="elDetail">
      <a href="https://store.shopping.yahoo.co.jp/example-store/fgosp26001.html">
        <img src=https://item-shopping.c.yimg.jp/i/j/example-store_fgosp26001 alt=FGO inスイパラ 等身アクリルスタンド>
      </a>
      <dd class="elName"><a href="https://store.shopping.yahoo.co.jp/example-store/fgosp26001.html"><span>FGO inスイパラ 等身アクリルスタンド（スイパラver.）</span></a></dd>
      <dd class="elInfo"><span class="elOrderMainInfo"><span class="elPrice">1,650円</span><span class="elNum">×1</span></span>
        <span class="elItemOption"><div class="elItemOptionExpand">
          <p class="elShipDate">発送目安：5ヵ月以内に発送（受注生産）</p>
          <p>等身アクリルスタンド（スイパラver.）:テュフォン・エフェメロス</p>
        </div></span>
      </dd>
    </dl></li>
    <li><dl class="elDetail">
      <a href="https://store.shopping.yahoo.co.jp/example-store/fgosp26001.html">
        <img src=https://item-shopping.c.yimg.jp/i/j/example-store_fgosp26001 alt=FGO inスイパラ 等身アクリルスタンド>
      </a>
      <dd class="elName"><span>FGO inスイパラ 等身アクリルスタンド（スイパラver.）</span></dd>
      <dd class="elInfo"><span class="elPrice">1,650円</span><span class="elNum">×2</span>
        <div class="elItemOptionExpand"><p>等身アクリルスタンド（スイパラver.）:ジャンヌ・ダルク〔オルタ〕</p></div>
      </dd>
    </dl></li>
    <li><dl class="elDetail">
      <a href="https://store.shopping.yahoo.co.jp/example-store/chokaguya001.html">
        <img src=https://item-shopping.c.yimg.jp/i/j/example-store_chokaguya001 alt=badge>
      </a>
      <dd class="elName"><span>超かぐや姫！&times;SWEETS PARADISE トレーディングアクリルスタンド</span></dd>
      <dd class="elInfo"><span class="elPrice">880円</span><span class="elNum">×160</span>
        <div class="elItemOptionExpand"><p class="elShipDate">発送目安：5ヵ月以内に発送</p></div>
      </dd>
    </dl></li>
    <li><dl class="elDetail">
      <a href="https://store.shopping.yahoo.co.jp/example-store/chokaguya004.html">
        <img src=https://item-shopping.c.yimg.jp/i/j/example-store_chokaguya004 alt=can>
      </a>
      <dd class="elName"><span>超かぐや姫！×SWEETS PARADISE トレーディング缶バッジ</span></dd>
      <dd class="elInfo"><span class="elPrice">550円</span><span class="elNum">×60</span></dd>
    </dl></li>
  </ul>
</div>
<div class="mdOrderReceipt">
  <p class="elStore"><span>示例商店</span></p>
  <div class="elTotalAmount">
    <ul class="elList">
      <li><dl><dt>商品合計（4点）</dt><dd>190,300円</dd></dl></li>
      <li><dl><dt>送料</dt><dd>715円</dd></dl></li>
      <li><dl><dt>手数料</dt><dd>0円</dd></dl></li>
      <li class="elSum"><dl><dt>合計金額（税込）</dt><dd>191,015円</dd></dl></li>
    </ul>
  </div>
</div>
<div class="mdStoreInfo"><li class="elName"><a href="https://store.shopping.yahoo.co.jp/example-store/">示例商店</a></li></div>
</body></html>
"""


class YahooShoppingOrderParseTests(unittest.TestCase):
    def test_detect(self) -> None:
        self.assertTrue(is_yahoo_shopping_order_html(FIXTURE))
        self.assertFalse(
            is_yahoo_shopping_order_html(
                "<html><body>Yahoo!ショッピング 商品一覧 1,650円</body></html>"
            )
        )

    def test_parse_lines_keep_variants(self) -> None:
        parsed = parse_yahoo_shopping_order_html(FIXTURE)
        products = parsed["products"]
        self.assertEqual(len(products), 4)
        self.assertEqual(parsed["order_ref"], "example-store-10000001")
        self.assertEqual(parsed["shipping_fee"], 715.0)
        self.assertEqual(parsed["order_total"], 191015.0)
        self.assertEqual(parsed["store_name"], "示例商店")
        self.assertEqual(parsed["shop"], "example-store")
        by_name = {p["name"]: p for p in products}
        typhoon = by_name[
            "FGO inスイパラ 等身アクリルスタンド（スイパラver.） (テュフォン・エフェメロス)"
        ]
        jeanne = by_name[
            "FGO inスイパラ 等身アクリルスタンド（スイパラver.） (ジャンヌ・ダルク〔オルタ〕)"
        ]
        self.assertEqual(typhoon["qty"], 1)
        self.assertEqual(typhoon["unit_cost"], 1650.0)
        self.assertEqual(typhoon["barcode"], "")
        self.assertEqual(typhoon["shop"], "example-store")
        self.assertIn("fgosp26001.html", typhoon["source_url"])
        self.assertEqual(jeanne["qty"], 2)
        self.assertEqual(jeanne["unit_cost"], 1650.0)
        stand = by_name["超かぐや姫！×SWEETS PARADISE トレーディングアクリルスタンド"]
        badge = by_name["超かぐや姫！×SWEETS PARADISE トレーディング缶バッジ"]
        self.assertEqual(stand["qty"], 160)
        self.assertEqual(stand["unit_cost"], 880.0)
        self.assertEqual(badge["qty"], 60)
        self.assertEqual(badge["unit_cost"], 550.0)
        self.assertNotIn("発送目安", stand["name"])

    def test_scrape_html_document(self) -> None:
        result = asyncio.run(scrape_html_document(FIXTURE))
        self.assertEqual(len(result["products"]), 4)
        self.assertEqual(result["order_ref"], "example-store-10000001")
        self.assertEqual(result["shipping_fee"], 715.0)
        self.assertEqual(result["order_total"], 191015.0)
        self.assertIn("Yahoo!ショッピング", result["message"])
        self.assertIn("税込", result["message"])
        self.assertIn("无 JAN", result["message"])
        self.assertEqual(sum(int(p["qty"]) for p in result["products"]), 223)


if __name__ == "__main__":
    unittest.main()
