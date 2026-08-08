import asyncio
import json
import re

import httpx


async def probe(url: str, label: str) -> None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.9",
    }
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        response = await client.get(url)
        print("===", label, response.status_code, str(response.url))
        html = response.text
        print("len", len(html))
        for pattern in ["__NEXT_DATA__", "application/ld+json", "/api/", "itemListElement", "/items/"]:
            print(pattern, pattern in html)
        match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
        if match:
            data = json.loads(match.group(1))
            print("next keys", list(data.keys())[:8])
            print("next sample", json.dumps(data, ensure_ascii=False)[:500])
        scripts = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        print("ld+json count", len(scripts))
        if scripts:
            print("ld sample", scripts[0][:400])
        links = re.findall(r'href="([^"]+/items/[^"]+)"', html)
        print("item links", len(links), links[:5])


async def main() -> None:
    await probe("https://csmcanvasshp.base.shop/", "base")
    await probe("https://internetangel.shop/", "internetangel")
    await probe("https://shibuyatsutaya.stores.jp/", "stores")


if __name__ == "__main__":
    asyncio.run(main())
