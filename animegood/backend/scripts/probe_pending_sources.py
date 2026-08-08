"""Probe disabled sources for platform signals and product list endpoints."""
from __future__ import annotations

import asyncio
import re

import httpx

SOURCES = [
    ("internetangel", "https://internetangel.base.shop/"),
    ("miraithings", "https://miraithings.com/"),
    ("pricafe", "https://pricafe.shop/"),
    ("i-rightsshop", "https://i-rightsshop.com/"),
    ("vvstore", "https://vvstore.jp/"),
    ("hakuichi", "https://hakuichi.jp/"),
    ("hakusensha-shop", "https://hakusensha-shop.jp/"),
    ("shop-asobistore", "https://shop.asobistore.jp/"),
    ("medicos-e-shop", "https://medicos-e-shop.net/"),
    ("store-kadokawa", "https://store.kadokawa.co.jp/"),
]

PATHS = [
    "",
    "products/list",
    "products/list.php",
    "product/list",
    "shop",
    "collections/all/products.json",
    "products.json",
    "items",
    "items/all",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9",
}


def signals(text: str, url: str) -> list[str]:
    found: list[str] = []
    checks = [
        ("shopify", r"cdn\.shopify|Shopify\.theme|/products\.json"),
        ("eccube", r"EC-CUBE|eccube|/products/list"),
        ("ochanoko", r"おちゃのこ|ochanoko|ocnk"),
        ("colorme", r"カラーミー|colorme|shop-pro\.jp"),
        ("futureshop", r"futureshop|FutureShop|/fs/"),
        ("base", r"powered by BASE|base\.shop|/items/\d+"),
        ("stores", r"stores\.jp|/items/[0-9a-f]{24}"),
    ]
    for name, pattern in checks:
        if re.search(pattern, text, re.I):
            found.append(name)
    if "/items/" in text:
        found.append("has-items")
    if "product_id" in text or "/products/detail/" in text:
        found.append("has-product-links")
    return found


async def probe_one(client: httpx.AsyncClient, source_id: str, base_url: str) -> None:
    print(f"\n=== {source_id} {base_url} ===")
    best = None
    for path in PATHS:
        url = base_url.rstrip("/") + (f"/{path}" if path else "/")
        try:
            response = await client.get(url)
            text = response.text[:120000]
            item_ids = len(set(re.findall(r"/items/(\d+)", text)))
            product_links = len(re.findall(r"/products/(?:detail/)?(\d+)", text))
            sig = signals(text, url)
            if response.status_code == 200 and (sig or item_ids or product_links):
                line = (
                    f"  {response.status_code} {url}\n"
                    f"    signals={sig} items={item_ids} product_links={product_links}"
                )
                print(line)
                if best is None or product_links > best[0] or item_ids > best[0]:
                    best = (max(product_links, item_ids), url, sig)
        except Exception as exc:
            print(f"  ERR {url}: {exc}")
    if best:
        print(f"  >> best: {best}")


async def main() -> None:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=HEADERS) as client:
        for source_id, base_url in SOURCES:
            await probe_one(client, source_id, base_url)


if __name__ == "__main__":
    asyncio.run(main())
