import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright


async def main() -> None:
    url = "https://shibuyatsutaya.stores.jp/"
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(
            locale="ja-JP",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
        )
        await page.goto(url, wait_until="networkidle", timeout=90000)
        await page.wait_for_selector('a[href*="/items/"]', timeout=15000)
        html = await page.content()
        Path("probe_list.html").write_text(html, encoding="utf-8")
        print("len", len(html))
        ids = re.findall(r"/items/([0-9a-f]{24})", html)
        print("ids", len(set(ids)))
        # JSON blobs
        for script in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S):
            text = script.strip()
            if '"price"' in text or '"name"' in text:
                if len(text) < 5000:
                    print("script snippet", text[:400])
                else:
                    print("large script", len(text), text[:200])
        # card text near links
        soup_links = re.findall(
            r'href="(/items/[0-9a-f]{24})"[^>]*>(.*?)</a>',
            html,
            re.S,
        )
        print("link blocks", len(soup_links))
        for href, inner in soup_links[:3]:
            text = re.sub(r"<[^>]+>", " ", inner)
            text = re.sub(r"\s+", " ", text).strip()
            print(href, text[:120])
        # ld+json
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
            print("ld+json", block[:300])
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
