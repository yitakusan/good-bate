"""Second-pass probe for tricky pending sources."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

CHECKS = [
    ("miraithings", "https://miraithings.com/view/category/all_items"),
    ("miraithings2", "https://miraithings.com/view/search?search_keyword="),
    ("i-rights", "https://i-rightsshop.com/"),
    ("i-rights2", "https://i-rightsshop.com/?mode=srh&cid=&keyword="),
    ("hakuichi", "https://hakuichi.jp/products/list.php?category_id=351"),
    ("kadokawa", "https://store.kadokawa.co.jp/shop/g/g502404/"),
    ("kadokawa2", "https://store.kadokawa.co.jp/shop/default.aspx"),
    ("hakusensha", "https://www.hakusensha-shop.co.jp/"),
    ("pricafe", "https://www.pricafe.shop/view/category/all_items"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0",
    "Accept-Language": "ja",
}


async def main() -> None:
    lines: list[str] = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=HEADERS) as client:
        for name, url in CHECKS:
            try:
                response = await client.get(url)
                text = response.text
                soup = BeautifulSoup(text, "html.parser")
                item_links = [
                    a.get("href", "")
                    for a in soup.select("a[href]")
                    if "/view/item/" in a.get("href", "")
                    or "/products/detail/" in a.get("href", "")
                    or "/shop/g/g" in a.get("href", "")
                    or "/fs/" in a.get("href", "")
                ]
                lines.append(f"=== {name} {url} => {response.status_code} ===")
                lines.append(f"final={response.url}")
                lines.append(f"title={(soup.title.string if soup.title else '')[:100]}")
                lines.append(f"item_links={item_links[:10]}")
                lines.append(
                    "regex="
                    + str(
                        {
                            "view_item": len(re.findall(r"/view/item/\d+", text)),
                            "detail": len(re.findall(r"/products/detail/[^\"']+", text)),
                            "shop_g": len(re.findall(r"/shop/g/g\d+", text)),
                            "fs": len(re.findall(r"/fs/[^\"']+", text)),
                        }
                    )
                )
                lines.append("")
            except Exception as exc:
                lines.append(f"=== {name} {url} ERR {exc} ===\n")

    Path(__file__).resolve().parents[1].joinpath("probe_pending_out2.txt").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


if __name__ == "__main__":
    asyncio.run(main())
