import asyncio
import re

import httpx


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


async def try_url(client: httpx.AsyncClient, url: str) -> None:
    response = await client.get(url)
    html = response.text
    items = len(set(re.findall(r"/items/\d+", html)))
    products = len(set(re.findall(r"/products/\d+", html)))
    print(response.status_code, url, "items", items, "products", products, "len", len(html))


async def main() -> None:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=HEADERS) as client:
        for url in [
            "https://internetangel.shop/",
            "https://www.internetangel.shop/",
            "https://internetangel.base.shop/",
            "https://shibuyatsutaya.stores.jp/",
            "https://www.shibuyatsutaya.stores.jp/",
            "https://shibuyatsutaya.stores.jp/products",
            "https://shibuyatsutaya.stores.jp/items",
        ]:
            await try_url(client, url)


if __name__ == "__main__":
    asyncio.run(main())
