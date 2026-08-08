"""Probe item page HTML for pending scrapers."""
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

ITEM_PAGES = [
    ("ochanoko", "https://miraithings.com/view/item/000000000887"),
    ("ochanoko2", "https://www.pricafe.shop/view/item/000000010417"),
    ("eccube", "https://medicos-e-shop.net/products/detail/40439"),
    ("eccube2", "https://vvstore.jp/products/detail/188388"),
    ("asobi", "https://shop.asobistore.jp/products/detail/243307-00-00-00"),
    ("kadokawa", "https://store.kadokawa.co.jp/shop/g/g7015027011501/"),
    ("colorme", "https://www.i-rightsshop.com/?pid=1712345678"),
]

LIST_PAGES = [
    ("colorme_cate", "https://www.i-rightsshop.com/?mode=cate&cbid=2627370&csid=0"),
    ("colorme_grp", "https://www.i-rightsshop.com/?mode=grp&gid=2747082"),
    ("hakusensha", "https://www.hakusensha-shop.co.jp/"),
    ("hakuichi_cat", "https://hakuichi.jp/products/list.php?category_id=351"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0", "Accept-Language": "ja"}


def summarize(name: str, url: str, status: int, final_url: str, html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    og_title = soup.find("meta", property="og:title")
    og_image = soup.find("meta", property="og:image")
    price_candidates = []
    for selector in [".price", ".item_price", "#price", ".product-price", ".sales_price"]:
        node = soup.select_one(selector)
        if node:
            price_candidates.append(node.get_text(" ", strip=True)[:80])
    text = soup.get_text(" ", strip=True)
    for token in ["円", "SOLD OUT", "在庫", "カート", "品切れ"]:
        if token in text:
            price_candidates.append(f"has:{token}")
    links = [
        anchor.get("href", "")
        for anchor in soup.select("a[href]")
        if any(x in anchor.get("href", "") for x in ("detail", "view/item", "/shop/g/", "pid="))
    ][:8]
    return (
        f"=== {name} ===\n"
        f"url={url}\nfinal={final_url}\nstatus={status}\n"
        f"title={(soup.title.string if soup.title else '')[:100]}\n"
        f"og:title={(og_title['content'] if og_title else '')[:100]}\n"
        f"og:image={(og_image['content'] if og_image else '')[:100]}\n"
        f"price_candidates={price_candidates[:6]}\n"
        f"links={links}\n"
    )


async def main() -> None:
    lines: list[str] = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=HEADERS) as client:
        for name, url in ITEM_PAGES + LIST_PAGES:
            try:
                response = await client.get(url)
                lines.append(summarize(name, url, response.status_code, str(response.url), response.text))
            except Exception as exc:
                lines.append(f"=== {name} ===\nurl={url}\nERR={exc}\n")
    Path(__file__).resolve().parents[1].joinpath("probe_item_out.txt").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


if __name__ == "__main__":
    asyncio.run(main())
