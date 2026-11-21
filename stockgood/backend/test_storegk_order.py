"""store-gk confirm.html order history is wired into scrape_html_document."""

from __future__ import annotations

import unittest

from app.scrapers.preview import scrape_html_document

HTML = """
<html><body>
<form><input name="db" value="gokurakuyu"></form>
<div class="orderBlock">
  <dl class="orderNum"><dt>注文番号：</dt><dd>P187766145113453904</dd></dl>
  <p class="orderStatus ok">準備中</p>
  <dl class="orderDaytime"><dd>2026年09月29日 19:25:00</dd></dl>
  <table class="orderList"><tbody>
    <tr>
      <td><dl class="orderItem">
        <dt><a href="javascript:open_brand_detail('shopdetail/000000005531/')">
          <img src="../images/none_image.png" class="productNoImage">
          <img src="https://makeshop-multi-images.akamaized.net/gokurakuyu/itemimages/0000000055313_x.jpg" style="display:none;">
        </a></dt>
        <dd><a href="javascript:open_brand_detail('shopdetail/000000005531/')">「12月中旬頃以降発送」きみが死ぬまで恋をしたい アクリルスタンド シーナ</a></dd>
      </dl></td>
      <td></td><td>1,800</td><td>1</td><td>10%</td><td>1,800円</td>
    </tr>
    <tr class="orderCharge"><th>送料</th><td>660円</td></tr>
    <tr class="orderTotal"><th>合計金額</th><td>28,820円</td></tr>
  </tbody></table>
</div>
<div class="orderBlock">
  <dl class="orderNum"><dt>注文番号：</dt><dd>P186589095997101361</dd></dl>
  <dl class="orderDaytime"><dd>2026年05月22日 21:18:05</dd></dl>
  <table class="orderList"><tbody>
    <tr>
      <td><dl class="orderItem">
        <dd><a href="javascript:open_brand_detail('shopdetail/000000004984/')">「7月中旬頃以降発送」初音ミク アクリルスタンド</a></dd>
      </dl></td>
      <td></td><td>1,500</td><td>3</td><td>10%</td><td>4,500円</td>
    </tr>
    <tr class="orderCharge"><th>送料</th><td>660円</td></tr>
    <tr class="orderTotal"><th>合計金額</th><td>22,110円</td></tr>
  </tbody></table>
</div>
<p>https://www.store-gk.com/</p>
</body></html>
"""


class StoreGkOrderHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_multi_order_page_lists_lines_without_merging_ref(self) -> None:
        result = await scrape_html_document(HTML)
        self.assertEqual(result["order_ref"], "")
        self.assertIsNone(result["shipping_fee"])
        self.assertEqual(len(result["products"]), 2)
        first = result["products"][0]
        self.assertIn("シーナ", first["name"])
        self.assertEqual(first["qty"], 1)
        self.assertEqual(first["unit_cost"], 1980.0)
        self.assertEqual(first["shop"], "store-gk.com")
        self.assertEqual(
            first["source_url"], "https://www.store-gk.com/shopdetail/000000005531/"
        )
        self.assertTrue(first["image_url"].startswith("https://makeshop-multi-images."))
        self.assertEqual(first["expected_ship_at"], "2026-12")
        self.assertEqual(first["expected_ship_period"], "mid")
        self.assertIn("2 笔", result["message"])
        self.assertIn("P187766145113453904", result["message"])

    async def test_thechara_order_uses_its_own_shop(self) -> None:
        html = """
<html><body>
<div class="orderBlock first">
  <dl class="orderNum"><dt>注文番号：</dt><dd>P187376629496392944</dd></dl>
  <dl class="orderDaytime"><dd>2026年08月17日 19:33:10</dd></dl>
  <table class="orderList"><tbody>
    <tr>
      <td><dl class="orderItem">
        <dt><a href="javascript:open_brand_detail('shopdetail/000000090718/')">
          <img src="https://makeshop-multi-images.akamaized.net/thechara55/itemimages/0000000907183_x.jpg">
        </a></dt>
        <dd><a href="javascript:open_brand_detail('shopdetail/000000090718/')">【事後通販】学園アイドルマスター　オーロラアクリルキーホルダー 篠澤 広 sunflower ver.【2026年10月中旬～11月上旬以降順次発送】 - 【2026年10月中旬～11月上旬以降順次発送】</a></dd>
      </dl></td>
      <td><p></p></td><td>1,050</td><td>1</td><td>10%</td><td>1,050円</td>
    </tr>
    <tr>
      <td><dl class="orderItem">
        <dd><a href="javascript:open_brand_detail('shopdetail/000000090720/')">キーホルダー 秦谷美鈴【2026年10月中旬～11月上旬以降順次発送】</a></dd>
      </dl></td>
      <td></td><td>1,050</td><td>2</td><td>10%</td><td>2,100円</td>
    </tr>
    <tr class="orderCharge"><th colspan="5">送料</th><td>770円</td></tr>
    <tr class="orderTotal"><th colspan="5">合計金額</th><td>57,475円</td></tr>
  </tbody></table>
</div>
</body></html>
"""
        result = await scrape_html_document(html)
        self.assertEqual(result["order_ref"], "P187376629496392944")
        self.assertEqual(result["shipping_fee"], 770.0)
        self.assertEqual(result["order_total"], 57475.0)
        self.assertEqual(len(result["products"]), 2)
        first = result["products"][0]
        self.assertIn("篠澤", first["name"])
        self.assertNotIn(" - 【2026年10月中旬", first["name"])
        self.assertEqual(first["qty"], 1)
        self.assertEqual(first["unit_cost"], 1155.0)
        self.assertEqual(first["shop"], "the-chara.com")
        self.assertEqual(
            first["source_url"],
            "https://www.the-chara.com/shopdetail/000000090718/",
        )
        self.assertIn("thechara55", first["image_url"])
        self.assertEqual(first["expected_ship_at"], "2026-10")
        self.assertEqual(first["expected_ship_period"], "mid")
        second = result["products"][1]
        self.assertEqual(second["qty"], 2)
        self.assertEqual(second["unit_cost"], 1155.0)
        self.assertIn("THEキャラ", result["message"])

    async def test_twincre_order_keeps_tax_included_price(self) -> None:
        html = """
<html><body>
<div class="dayBlock first">
  <h2 class="dayTitle">2026年10月09日</h2>
  <div class="orderBlock first">
    <dl class="orderNum"><dt>注文番号：</dt><dd>P187853363280551690</dd></dl>
    <p class="orderStatus ok">発送完了</p>
    <dl class="orderDaytime"><dd>2026年10月09日 10:27:58</dd></dl>
    <table class="orderList"><tbody>
      <tr>
        <td><dl class="orderItem">
          <dt><a href="javascript:open_brand_detail('shopdetail/000000004820/')">
            <img src="https://makeshop-multi-images.akamaized.net/TwinCre/itemimages/0000000048203_iOsp1fx.jpg">
          </a></dt>
          <dd><a href="javascript:open_brand_detail('shopdetail/000000004820/')">初音ミク　街道さんぽ ～京友禅ver.～　ジオラマアクリル　初音ミク - 2026年10月発送</a></dd>
        </dl></td>
        <td><p></p></td><td>4,950</td><td>1</td><td>10%</td><td>4,950円 <br>（税込）</td>
      </tr>
      <tr>
        <td><dl class="orderItem">
          <dd><a href="javascript:open_brand_detail('shopdetail/000000004824/')">初音ミク　街道さんぽ ～京友禅ver.～　絵馬風ストラップ　初音ミク - 2026年10月発送</a></dd>
        </dl></td>
        <td><p></p></td><td>1,100</td><td>4</td><td>10%</td><td>4,400円 <br>（税込）</td>
      </tr>
      <tr class="orderCharge"><th colspan="5">送料</th><td>880円</td></tr>
      <tr class="orderTotal"><th colspan="5">合計金額</th><td>10,230円</td></tr>
    </tbody></table>
  </div>
</div>
</body></html>
"""
        result = await scrape_html_document(html)
        self.assertEqual(result["order_ref"], "P187853363280551690")
        self.assertEqual(result["shipping_fee"], 880.0)
        self.assertEqual(result["order_total"], 10230.0)
        self.assertEqual(len(result["products"]), 2)
        first, second = result["products"]
        self.assertIn("ジオラマアクリル", first["name"])
        self.assertEqual(first["qty"], 1)
        self.assertEqual(first["unit_cost"], 4950.0)
        self.assertEqual(first["shop"], "shop.twincre.com")
        self.assertEqual(
            first["source_url"],
            "https://shop.twincre.com/shopdetail/000000004820/",
        )
        self.assertIn("TwinCre", first["image_url"])
        self.assertEqual(first["expected_ship_at"], "2026-10")
        self.assertIsNone(first["expected_ship_period"])
        self.assertEqual(second["qty"], 4)
        self.assertEqual(second["unit_cost"], 1100.0)
        self.assertIn("絵馬風ストラップ", second["name"])
        self.assertIn("税込", result["message"])
        self.assertNotIn("税抜", result["message"])


if __name__ == "__main__":
    unittest.main()
