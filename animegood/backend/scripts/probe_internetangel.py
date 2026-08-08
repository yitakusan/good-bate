import asyncio
import re

import httpx
from bs4 import BeautifulSoup


async def main() -> None:
    url = "https://internetangel.base.shop/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.9",
    }
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        response = await client.get(url)
        html = response.text
        print("status", response.status_code, "len", len(html))
        for pattern in [r"/items/\d+", r"/products/\d+", r"itemId", r"dataLayer"]:
            matches = sorted(set(re.findall(pattern, html)))
            print(pattern, len(matches), matches[:5])
        soup = BeautifulSoup(html, "html.parser")
        for selector in ['a[href*="/items/"]', 'a[href*="/products/"]', "a.item", ".itemCard a"]:
            found = soup.select(selector)
            print(selector, len(found))
            if found:
                print("sample", found[0].get("href"), found[0].get_text(" ", strip=True)[:60])


if __name__ == "__main__":
    asyncio.run(main())
