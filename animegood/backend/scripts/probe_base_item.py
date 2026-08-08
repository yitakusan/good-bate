import asyncio
import json
import re

import httpx
from bs4 import BeautifulSoup


async def inspect_item(url: str) -> None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.9",
        "Referer": "https://csmcanvasshp.base.shop/",
    }
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        response = await client.get(url)
        print("item", response.status_code, url)
        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.find("meta", property="og:title")
        image = soup.find("meta", property="og:image")
        print("og:title", title["content"] if title else None)
        print("og:image", (image["content"][:80] + "...") if image else None)
        for script in soup.find_all("script"):
            text = script.string or script.get_text()
            if not text or "price" not in text.lower():
                continue
            if len(text) < 5000:
                print("script", text[:500])
        text = soup.get_text(" ", strip=True)
        for kw in ["SOLD OUT", "在庫", "予約", "発送", "お届け", "¥"]:
            if kw in text:
                print("has", kw)


async def inspect_list(url: str) -> None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.9",
    }
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        response = await client.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.select('a[href*="/items/"]')
        print("cards", len(cards))
        seen = set()
        for card in cards:
            href = card.get("href", "")
            if href in seen:
                continue
            seen.add(href)
            print("card", href, card.get_text(" ", strip=True)[:80])
            if len(seen) >= 3:
                break


async def main() -> None:
    await inspect_list("https://csmcanvasshp.base.shop/")
    await inspect_item("https://csmcanvasshp.base.shop/items/141875427")


if __name__ == "__main__":
    asyncio.run(main())
