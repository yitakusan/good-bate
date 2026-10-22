"""FutureShop product parse + KADOKAWA cart URL."""

from __future__ import annotations

import unittest

from app.scrapers.futureshop import parse_futureshop_product_html
from app.services.retailer_cart import add_to_cart, product_id_from_url

PAGE = (
    "https://store.kadokawa.co.jp/shop/g/g4984995910796/"
    "?publication_id=ebten-b00020"
)
HTML = """
<html><head>
<meta property="og:title" content="P30th keyholder: goods | kadost">
<meta property="og:image" content="https://store.kadokawa.co.jp/img/goods/S/4984995910796.jpg">
<meta property="product:price:amount" content="1320">
<script type="application/ld+json">
{"@type":"Product","name":"P30th 30周年記念イラストC 主人公アクリルキーホルダー（P3P）","offers":{"price":"1320"}}
</script>
</head><body>
<input name="goods" value="4984995910796">
<p>デート・ア・ライブ 関連</p>
</body></html>
"""


class FutureShopKadokawaTests(unittest.TestCase):
    def test_goods_code_keeps_publication_query(self) -> None:
        self.assertEqual(product_id_from_url(PAGE), "4984995910796")

    def test_parse_uses_product_name_not_page_noise(self) -> None:
        product = parse_futureshop_product_html(HTML, PAGE)
        assert product is not None
        self.assertEqual(
            product["name"],
            "P30th 30周年記念イラストC 主人公アクリルキーホルダー（P3P）",
        )
        self.assertEqual(product["unit_cost"], 1320.0)
        self.assertEqual(product["shop"], "store.kadokawa.co.jp")
        self.assertIn("/img/goods/L/4984995910796.jpg", product["image_url"])
        self.assertEqual(product["barcode"], "4984995910796")
        self.assertNotEqual(product["ip"], "デート・ア・ライブ")

    def test_cart_url_for_publication_link(self) -> None:
        result = add_to_cart(
            [{"source_url": PAGE, "qty": 2, "shop": "store.kadokawa.co.jp"}]
        )
        self.assertEqual(
            result["carts"][0]["cart_url"],
            "https://store.kadokawa.co.jp/shop/cart/cart.aspx?goods=4984995910796&qty=2",
        )


if __name__ == "__main__":
    unittest.main()
