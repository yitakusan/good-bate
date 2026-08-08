"""Extract product link patterns from pending sources."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

PAGES = {
    "hakuichi": "https://hakuichi.jp/products/list.php",
    "asobi": "https://shop.asobistore.jp/",
    "kadokawa": "https://store.kadokawa.co.jp/",
    "miraithings": "https://miraithings.com/",
    "pricafe": "https://pricafe.shop/",
    "i-rights": "https://i-rightsshop.com/",
    "medicos": "https://medicos-e-shop.net/products/list",
    "vvstore": "https://vvstore.jp/products/list",
    "internetangel": "https://internetangel.base.shop/items/all",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0",
    "Accept-Language": "ja",
}


async def main() -> None:
    out: list[str] = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=HEADERS) as client:
        for name, url in PAGES.items():
            response = await client.get(url)
            soup = BeautifulSoup(response.text, "html.parser")
            links: list[str] = []
            for anchor in soup.select("a[href]"):
                href = anchor.get("href", "")
                if any(token in href for token in ("product", "item", "goods", "/fs/", "detail")):
                    links.append(href)
            patterns = {
                "detail_num": sorted(set(re.findall(r"/products/detail/(\d+)", response.text)))[:5],
                "detail_path": sorted(set(re.findall(r"/products/detail/[^\"'\s>]+", response.text)))[:5],
                "fs_goods": sorted(set(re.findall(r"/fs/goods/[^\"'\s>]+", response.text)))[:5],
                "base_items": sorted(set(re.findall(r"/items/(\d+)", response.text)))[:5],
                "ocnk": "ocnk" in response.text.lower() or "おちゃのこ" in response.text,
                "colorme": "colorme" in response.text.lower() or "shop-pro" in response.text.lower(),
            }
            out.append(f"=== {name} {url} status={response.status_code} ===")
            out.append(f"title={(soup.title.string if soup.title else '')[:120]}")
            out.append(f"sample_links={links[:12]}")
            out.append(f"patterns={patterns}")
            out.append("")

    Path(__file__).resolve().parents[1].joinpath("probe_pending_out.txt").write_text(
        "\n".join(out),
        encoding="utf-8",
    )


if __name__ == "__main__":
    asyncio.run(main())
