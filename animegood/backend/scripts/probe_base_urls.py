import asyncio
import re

import httpx


URLS = [
    "https://csmcanvasshp.base.shop/",
    "https://csmcanvasshp.base.shop/items",
    "https://csmcanvasshp.base.shop/items/all",
    "https://csmcanvasshp.base.shop/categories/all",
    "https://internetangel.base.shop/",
    "https://internetangel.base.shop/items",
    "https://internetangel.base.shop/items/all",
    "https://internetangel.shop/",
]


async def main() -> None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.9",
    }
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        for url in URLS:
            try:
                response = await client.get(url)
                items = len(set(re.findall(r"/items/(\d+)", response.text)))
                print(response.status_code, items, url)
            except Exception as exc:
                print("ERR", url, exc)


if __name__ == "__main__":
    asyncio.run(main())
