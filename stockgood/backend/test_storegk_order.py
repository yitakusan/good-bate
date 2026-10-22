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


if __name__ == "__main__":
    unittest.main()
