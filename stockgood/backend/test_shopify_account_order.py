"""Shopify new customer-account rendered order HTML."""

from __future__ import annotations

import unittest

from app.scrapers.preview import scrape_html_document

HTML = """
<div>
  <h1>注文 (4227)</h1>
  <a href="https://acaciacreate.shop/cart/1:2">再購入</a>
  <h3 id="items">注文アイテム</h3>
  <div role="table" aria-labelledby="items">
    <div role="row">
      <div role="cell">
        <img src="https://cdn.shopify.com/s/files/1/1/files/a_128x128.jpg" alt="魔法少女ノ魔女裁判 x h.naoto 等身アクリルスタンド">
        <div><span>数量</span>2</div>
      </div>
      <div role="cell">
        <span>魔法少女ノ魔女裁判 x h.naoto 等身アクリルスタンド</span>
        <small><span>沢渡ココ</span></small>
        <small>￥1,980/ユニット</small>
      </div>
      <div role="cell"><span>￥3,960</span></div>
    </div>
    <div role="row">
      <div role="cell">
        <img src="https://cdn.shopify.com/s/files/1/1/files/b_128x128.jpg" alt="魔法少女ノ魔女裁判 x h.naoto 等身アクリルスタンド">
        <div><span>数量</span>3</div>
      </div>
      <div role="cell">
        <span>魔法少女ノ魔女裁判 x h.naoto 等身アクリルスタンド</span>
        <small><span>紫藤アリサ</span></small>
        <small>￥1,980/ユニット</small>
      </div>
      <div role="cell"><span>￥5,940</span></div>
    </div>
  </div>
  <h3>注文合計</h3>
  <div role="table">
    <div role="row">
      <div role="rowheader"><span>小計・5アイテム</span></div>
      <div role="cell"><span>￥9,900</span></div>
    </div>
    <div role="row">
      <div role="rowheader"><span>配送</span></div>
      <div role="cell"><span>￥880</span></div>
    </div>
    <div role="row">
      <div role="rowheader"><strong>合計</strong></div>
      <div role="cell"><strong>￥16,720</strong></div>
    </div>
  </div>
</div>
"""


class ShopifyCustomerOrderTests(unittest.IsolatedAsyncioTestCase):
    async def test_rendered_item_block(self) -> None:
        result = await scrape_html_document(HTML)
        self.assertEqual(result["order_ref"], "4227")
        self.assertEqual(result["shipping_fee"], 880.0)
        self.assertEqual(result["order_total"], 16720.0)
        self.assertEqual(len(result["products"]), 2)
        first, second = result["products"]
        self.assertIn("沢渡ココ", first["name"])
        self.assertEqual(first["qty"], 2)
        self.assertEqual(first["unit_cost"], 1980.0)
        self.assertEqual(first["shop"], "acaciacreate.shop")
        self.assertTrue(first["image_url"].endswith("a_128x128.jpg"))
        self.assertIn("紫藤アリサ", second["name"])
        self.assertEqual(second["qty"], 3)
        self.assertIn("税込", result["message"])


if __name__ == "__main__":
    unittest.main()
