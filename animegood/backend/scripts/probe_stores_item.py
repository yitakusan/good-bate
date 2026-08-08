import asyncio
import re
from pathlib import Path

from playwright.async_api import async_playwright


async def main() -> None:
    url = "https://shibuyatsutaya.stores.jp/items/6a3a1611a7f9cb00494e48b3"
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(locale="ja-JP")
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            await page.wait_for_selector("h1", timeout=15000)
        except Exception:
            pass
        await page.wait_for_timeout(3000)
        html = await page.content()
        Path("probe_item.html").write_text(html, encoding="utf-8")
        print("html len", len(html))
        print("title tag", await page.title())
        for key in ("og:title", "og:image", "og:description", "twitter:title"):
            m = re.search(rf'property="{key}" content="([^"]*)"', html)
            if not m:
                m = re.search(rf'name="{key}" content="([^"]*)"', html)
            print(key, m.group(1)[:120] if m else None)
        for pattern in [r'"price"\s*:\s*(\d+)', r"¥\s*([\d,]+)", r"([\d,]+)\s*円", r"itemPrice", r"product_name"]:
            if re.search(pattern, html):
                print("found", pattern)
        idx = html.find("STORES_JP")
        if idx >= 0:
            print("STORES_JP snippet", html[idx : idx + 500])
        idx = html.find("__NEXT_DATA__")
        if idx >= 0:
            print("NEXT_DATA len", len(html[idx : idx + 2000]))
        print("SOLD OUT" in html, "カート" in html)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
