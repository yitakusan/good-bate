"""FEATURE: RETAILER_CART — bushiroad-store.com template + cart permalink tests."""

from __future__ import annotations

import unittest

from app.services.retailer_cart import (
    TEMPLATE_CSV,
    add_to_cart,
    build_cart_permalink,
    build_order_payload,
    parse_template,
    pick_variant,
    product_id_from_url,
)

FAKE_PRODUCT = {
    "handle": "2000326637643",
    "title": "Roselia keyholder",
    "images": [{"src": "https://cdn.example/roselia.jpg"}],
    "variants": [
        {
            "id": 46137068159183,
            "available": True,
            "title": "Default Title",
            "price": "1500",
        },
        {
            "id": 46137068159184,
            "available": False,
            "title": "Other",
            "price": "1600",
        },
    ],
}


class RetailerCartParseTests(unittest.TestCase):
    def test_handle_from_product_and_collection_url(self) -> None:
        self.assertEqual(
            product_id_from_url(
                "https://bushiroad-store.com/products/2000326637643"
            ),
            "2000326637643",
        )
        self.assertEqual(
            product_id_from_url(
                "https://bushiroad-store.com/collections/x/products/2000326637643?variant=1"
            ),
            "2000326637643",
        )

    def test_csv_whitelist_and_skip(self) -> None:
        raw = (
            "链接,数量\n"
            "https://bushiroad-store.com/products/2000326637643,2\n"
            "https://bushiroad-store.com/products/2000326637643,3\n"
            "https://www.animate-onlineshop.jp/pd/3459202/,1\n"
            "https://bushiroad-store.com/collections/all,1\n"
            ",\n"
        ).encode("utf-8")
        parsed = parse_template(raw, "cart.csv")
        self.assertEqual(len(parsed["eligible"]), 1)
        line = parsed["eligible"][0]
        self.assertEqual(line["product_id"], "2000326637643")
        self.assertEqual(line["qty"], 5)
        reasons = {row["skip_reason"] for row in parsed["skipped"]}
        self.assertIn("host_not_allowed", reasons)
        self.assertIn("not_product_page", reasons)

    def test_template_csv_fixture(self) -> None:
        parsed = parse_template(TEMPLATE_CSV.encode("utf-8"), "sample.csv")
        self.assertEqual(len(parsed["eligible"]), 1)
        self.assertEqual(parsed["eligible"][0]["product_id"], "2000326637643")

    def test_pick_available_then_variant_query(self) -> None:
        picked = pick_variant(
            FAKE_PRODUCT, "https://bushiroad-store.com/products/2000326637643"
        )
        self.assertEqual(int(picked["id"]), 46137068159183)
        picked2 = pick_variant(
            FAKE_PRODUCT,
            "https://bushiroad-store.com/products/2000326637643?variant=46137068159184",
        )
        self.assertEqual(int(picked2["id"]), 46137068159184)

    def test_permalink(self) -> None:
        url = build_cart_permalink(
            "www.bushiroad-store.com",
            [(46137068159183, 2), (46137068159183, 1)],
        )
        self.assertEqual(
            url, "https://bushiroad-store.com/cart/46137068159183:3"
        )

    def test_add_builds_permalink(self) -> None:
        parsed = parse_template(TEMPLATE_CSV.encode("utf-8"), "sample.csv")

        def fake_fetch(_url: str) -> dict:
            return FAKE_PRODUCT

        result = add_to_cart(parsed["eligible"], fetch_product=fake_fetch)
        self.assertEqual(
            result["cart_url"],
            "https://bushiroad-store.com/cart/46137068159183:1",
        )
        self.assertEqual(result["items"][0]["variant_id"], "46137068159183")
        self.assertEqual(len(result["carts"]), 1)
        self.assertEqual(result["carts"][0]["shop"], "bushiroad-store.com")

    def test_inclusive_shop_keeps_json_price(self) -> None:
        raw = (
            "链接,数量\n"
            "https://lafary.shop/products/1000000200652,1\n"
        ).encode("utf-8")

        def fake_fetch(_url: str) -> dict:
            return FAKE_PRODUCT

        parsed = parse_template(raw, "cart.csv", fetch_product=fake_fetch)
        line = parsed["eligible"][0]
        self.assertEqual(line["shop"], "lafary.shop")
        self.assertEqual(line["unit_cost"], 1500.0)
        self.assertEqual(line["name"], "Roselia keyholder")

    def test_mixed_shops_split_carts_and_orders(self) -> None:
        raw = (
            "链接,数量\n"
            "https://bushiroad-store.com/products/2000326637643,1\n"
            "https://www.lafary.shop/products/1000000200652,2\n"
            "https://animeshi.jp/products/11a0761661011,1\n"
        ).encode("utf-8")

        def fake_fetch(_url: str) -> dict:
            return FAKE_PRODUCT

        parsed = parse_template(raw, "cart.csv", fetch_product=fake_fetch)
        shops = [row["shop"] for row in parsed["eligible"]]
        self.assertEqual(
            shops,
            ["bushiroad-store.com", "lafary.shop", "animeshi.jp"],
        )
        result = add_to_cart(parsed["eligible"], fetch_product=fake_fetch)
        self.assertEqual(len(result["carts"]), 3)
        self.assertTrue(
            result["carts"][0]["cart_url"].startswith(
                "https://bushiroad-store.com/cart/"
            )
        )
        self.assertTrue(
            result["carts"][1]["cart_url"].startswith("https://lafary.shop/cart/")
        )
        with self.assertRaises(ValueError):
            build_order_payload(parsed["eligible"], "MIX-1", 1000)
        lafary = [row for row in parsed["eligible"] if row["shop"] == "lafary.shop"]
        payload = build_order_payload(lafary, "LF-1", 4000)
        self.assertEqual(payload["shop"], "lafary.shop")
        self.assertEqual(payload["order_qty"], 2)
        self.assertEqual(payload["lines"][0]["unit_cost"], 1500.0)
        self.assertEqual(payload["shipping_fee"], 1000.0)

    def test_futureshop_makeshop_and_asobi_carts(self) -> None:
        raw = (
            "链接,数量\n"
            "https://jumpcs.shueisha.co.jp/shop/g/g4530430559404/,1\n"
            "https://www.jumpcs.shueisha.co.jp/shop/g/g4530430559404/,2\n"
            "https://store.kadokawa.co.jp/shop/g/g302512002854/,1\n"
            "https://miraithings.com/view/item/000000000886,3\n"
            "https://www.pricafe.shop/view/item/000000020359,1\n"
            "https://www.store-gk.com/shopdetail/000000019536/,2\n"
            "https://shop.asobistore.jp/products/detail/237789-00-00-00,4\n"
            "https://www.animate-onlineshop.jp/pd/3459202/,1\n"
        ).encode("utf-8")
        parsed = parse_template(raw, "cart.csv")
        by_shop = {row["shop"]: row for row in parsed["eligible"]}
        self.assertEqual(by_shop["jumpcs.shueisha.co.jp"]["qty"], 3)
        self.assertEqual(by_shop["jumpcs.shueisha.co.jp"]["product_id"], "4530430559404")
        self.assertEqual(by_shop["jumpcs.shueisha.co.jp"]["name"], "4530430559404")
        self.assertEqual(by_shop["store.kadokawa.co.jp"]["product_id"], "302512002854")
        self.assertEqual(by_shop["miraithings.com"]["product_id"], "000000000886")
        self.assertEqual(by_shop["pricafe.shop"]["shop"], "pricafe.shop")
        self.assertEqual(by_shop["store-gk.com"]["product_id"], "000000019536")
        self.assertEqual(
            by_shop["shop.asobistore.jp"]["product_id"], "237789-00-00-00"
        )
        self.assertIn(
            "host_not_allowed",
            {row["skip_reason"] for row in parsed["skipped"]},
        )
        result = add_to_cart(parsed["eligible"])
        kinds = {cart["shop"]: cart for cart in result["carts"]}
        self.assertEqual(
            kinds["jumpcs.shueisha.co.jp"]["cart_urls"],
            [
                "https://jumpcs.shueisha.co.jp/shop/cart/cart.aspx?goods=4530430559404&qty=3"
            ],
        )
        self.assertEqual(kinds["jumpcs.shueisha.co.jp"]["method"], "get")
        self.assertEqual(
            kinds["store.kadokawa.co.jp"]["cart_url"],
            "https://store.kadokawa.co.jp/shop/cart/cart.aspx?goods=302512002854&qty=1",
        )
        self.assertEqual(
            kinds["miraithings.com"]["posts"][0]["fields"]["brand_info"],
            "1,000000000886,3,N",
        )
        self.assertEqual(
            kinds["pricafe.shop"]["posts"][0]["action"],
            "https://pricafe.shop/api/basket/add.html",
        )
        self.assertEqual(
            kinds["store-gk.com"]["posts"][0]["fields"]["brand_info"],
            "1,000000019536,2,N",
        )
        self.assertEqual(
            kinds["shop.asobistore.jp"]["posts"][0]["fields"],
            {"ec_number": "237789-00-00-00", "num": "4"},
        )
        self.assertEqual(kinds["shop.asobistore.jp"]["method"], "post")

    def test_hmv_item_url_repeats_inbasket_per_qty(self) -> None:
        raw = (
            "链接,数量\n"
            "https://www.hmv.co.jp/artist_%E5%8B%9D%E5%88%A9%E3%81%AE%E5%A5%B3%E7%A5%9E%EF%BC%9ANIKKE_000000000968859/item_%E3%82%A2%E3%82%AF%E3%83%AA%E3%83%AB%E3%82%B9%E3%82%BF%E3%83%B3%E3%83%89_17043125,2\n"
            "https://www.hmv.co.jp/artist_NIKKE_000000000968859/,1\n"
        ).encode("utf-8")
        parsed = parse_template(raw, "hmv.csv")
        self.assertEqual(len(parsed["eligible"]), 1)
        line = parsed["eligible"][0]
        self.assertEqual(line["shop"], "hmv.co.jp")
        self.assertEqual(line["product_id"], "17043125")
        self.assertEqual(line["qty"], 2)
        self.assertEqual(parsed["skipped"][0]["skip_reason"], "not_product_page")
        result = add_to_cart(parsed["eligible"])
        cart = result["carts"][0]
        self.assertEqual(cart["kind"], "hmv")
        self.assertEqual(
            cart["cart_urls"],
            [
                "https://www.hmv.co.jp/basket/inbasket/?sku=17043125",
                "https://www.hmv.co.jp/basket/inbasket/?sku=17043125",
            ],
        )

    def test_parse_default_skips_network_preview(self) -> None:
        parsed = parse_template(TEMPLATE_CSV.encode("utf-8"), "sample.csv")
        line = parsed["eligible"][0]
        self.assertEqual(line["name"], "")
        self.assertEqual(line["image_url"], "")
        self.assertIsNone(line["unit_cost"])

    def test_parse_enrich_name_image_tax_inclusive(self) -> None:
        raw = (
            "链接,数量\n"
            "https://bushiroad-store.com/products/2000326637643?variant=46137068159184,1\n"
        ).encode("utf-8")

        def fake_fetch(_url: str) -> dict:
            return FAKE_PRODUCT

        parsed = parse_template(raw, "cart.csv", fetch_product=fake_fetch)
        line = parsed["eligible"][0]
        self.assertEqual(line["name"], "Roselia keyholder")
        self.assertEqual(line["image_url"], "https://cdn.example/roselia.jpg")
        self.assertEqual(line["unit_cost"], 1760.0)

    def test_parse_enrich_keeps_eligible_on_fail(self) -> None:
        def boom(_url: str) -> dict:
            raise RuntimeError("offline")

        parsed = parse_template(
            TEMPLATE_CSV.encode("utf-8"), "sample.csv", fetch_product=boom
        )
        self.assertEqual(len(parsed["eligible"]), 1)
        self.assertEqual(parsed["eligible"][0]["name"], "2000326637643")
        self.assertEqual(parsed["eligible"][0]["image_url"], "")
        self.assertIsNone(parsed["eligible"][0]["unit_cost"])

    def test_csv_gbk_header(self) -> None:
        raw = (
            "链接,数量\n"
            "https://bushiroad-store.com/products/2000326637643,2\n"
        ).encode("gbk")
        parsed = parse_template(raw, "cart.csv")
        self.assertEqual(len(parsed["eligible"]), 1)
        self.assertEqual(parsed["eligible"][0]["qty"], 2)
        self.assertEqual(parsed["eligible"][0]["product_id"], "2000326637643")

    def test_build_order_payload_shipping_residual(self) -> None:
        raw = (
            "链接,数量\n"
            "https://bushiroad-store.com/products/2000326637643,2\n"
        ).encode("utf-8")
        parsed = parse_template(raw, "cart.csv", fetch_product=lambda _u: FAKE_PRODUCT)
        payload = build_order_payload(parsed["eligible"], "BR-1001", 4000)
        self.assertEqual(payload["order_ref"], "BR-1001")
        self.assertEqual(payload["shop"], "bushiroad-store.com")
        self.assertEqual(payload["order_qty"], 2)
        self.assertEqual(payload["lines"][0]["name"], "Roselia keyholder")
        self.assertEqual(payload["lines"][0]["qty"], 2)
        self.assertEqual(payload["lines"][0]["unit_cost"], 1650.0)
        self.assertEqual(payload["shipping_fee"], 700.0)
        self.assertIn("4000", payload["note"])

    def test_add_rejects_non_whitelist(self) -> None:
        with self.assertRaises(ValueError):
            add_to_cart(
                [
                    {
                        "source_url": "https://zozo.jp/shop/a/goods/1/",
                        "qty": 1,
                    }
                ],
                fetch_product=lambda _u: FAKE_PRODUCT,
            )


if __name__ == "__main__":
    unittest.main()
