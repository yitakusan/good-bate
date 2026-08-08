import asyncio
import re

import httpx


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
        html = (await client.get(url)).text
        for pattern in [
            r"https?://[^\"'\s]+",
            r"item[s]?[_\"][^\"']{0,40}",
            r"shopId[^,]{0,80}",
            r"baseec[^\"'\s]+",
            r"/categories/[^\"']+",
        ]:
            matches = sorted(set(re.findall(pattern, html)))[:10]
            print("---", pattern, len(matches))
            for match in matches:
                print(match[:120])


if __name__ == "__main__":
    asyncio.run(main())
