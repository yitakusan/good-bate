import asyncio
import re

from playwright.async_api import async_playwright


async def probe(url: str, label: str) -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(locale="ja-JP")
        response = await page.goto(url, wait_until="networkidle", timeout=60000)
        print("===", label, response.status if response else None, page.url)
        html = await page.content()
        print("len", len(html))
        item_links = sorted(set(re.findall(r'href="([^"]+/items/[^"]+)"', html)))
        print("item links", len(item_links), item_links[:5])
        product_links = sorted(set(re.findall(r'href="([^"]+/products/[^"]+)"', html)))
        print("product links", len(product_links), product_links[:5])
        await browser.close()


async def main() -> None:
    await probe("https://internetangel.shop/", "internetangel")
    await probe("https://shibuyatsutaya.stores.jp/", "stores")


if __name__ == "__main__":
    asyncio.run(main())
