import asyncio
import re

import httpx


async def main() -> None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.9",
        "Referer": "https://shibuyatsutaya.stores.jp/",
    }
    urls = [
        "https://shibuyatsutaya.stores.jp/",
        "https://shibuyatsutaya.stores.jp/items/6a49f2e550f81de53c4c910d",
        "https://shibuyatsutaya.stores.jp/items",
    ]
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        for url in urls:
            response = await client.get(url)
            og = re.search(r'property="og:title"\s+content="([^"]+)"', response.text)
            items = len(set(re.findall(r"/items/[0-9a-f]{24}", response.text)))
            print(response.status_code, items, og.group(1)[:40] if og else None, url)


if __name__ == "__main__":
    asyncio.run(main())
