from __future__ import annotations

import asyncio
import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.ip_normalizer import IpNormalizer
from app.release_date import map_release_to_expected_ship
from app.scrapers.biccamera import is_biccamera_blocked_page, is_biccamera_url
from app.scrapers.hmv import is_hmv_empty_shell, is_hmv_url
from app.scrapers.jan import extract_jan_from_html, extract_jan_from_shopify_product
from app.settings import get_settings

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.8,zh;q=0.7",
}

PRICE_RE = re.compile(
    r"(?:¥|￥|JPY)\s*([\d,]+)|([\d,]+)\s*円",
    re.IGNORECASE,
)

_RELEASE_RE = re.compile(
    r"(?:商品のお届け|お届け時期|お届け予定日|配送時期|配送予定|発売予定日|発売日|発送予定|出荷予定)"
    r"[^。．\n\r]*?(?:(\d{4})年)?\s*(\d{1,2})月\s*(上旬|中旬|下旬|\d{1,2}日)?",
)


def _shop_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _clean_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.split("#")[0]


def _guess_ip(text: str) -> str:
    return IpNormalizer(get_settings().ip_alias_path).normalize(text)


def _parse_price_text(text: str) -> Optional[float]:
    """Pick first yen amount that is not a free-shipping threshold."""
    cleaned = text.replace("\u00a0", " ")
    for m in PRICE_RE.finditer(cleaned):
        after = cleaned[m.end() : m.end() + 24]
        # e.g. "8,800円 (税込)以上で" — not a product price
        if "以上" in after:
            continue
        before = cleaned[max(0, m.start() - 24) : m.start()]
        if "送料" in before and "無料" in after:
            continue
        raw = next((g for g in m.groups() if g), None)
        if not raw:
            continue
        try:
            return float(raw.replace(",", ""))
        except ValueError:
            continue
    return None


def _parse_price_from_page(soup: BeautifulSoup, html: str) -> Optional[float]:
    """Prefer product price nodes / analytics snippets over whole-page regex."""
    # FutureShop / asobi: main price id — never use related-item .selling_price first.
    for sel in ("#selling_price", "#selling_price_wrap dd", "#selling_price_wrap"):
        tag = soup.select_one(sel)
        if not tag:
            continue
        value = _parse_price_text(tag.get_text(" ", strip=True))
        if value is None:
            raw = re.sub(r"[^\d.]", "", tag.get_text("", strip=True).replace(",", ""))
            if raw:
                try:
                    value = float(raw)
                except ValueError:
                    value = None
        if value is not None:
            return value

    for sel in (
        ".price.new_price",
        "p.price.new_price",
        ".item_price .price",
        ".item_price p.price",
        "[itemprop='price']",
        "meta[itemprop='price']",
        ".product__price",
        ".price-item--regular",
        ".price__regular .price-item",
        "p.price",
        "span.selling_price",
    ):
        for tag in soup.select(sel):
            if tag.find_parent(
                class_=re.compile(r"area_rel_product|shopbox_wrap|related", re.I)
            ):
                continue
            content = tag.get("content")
            if content:
                try:
                    return float(str(content).replace(",", "").strip())
                except ValueError:
                    pass
            value = _parse_price_text(tag.get_text(" ", strip=True))
            if value is not None:
                return value

    m = re.search(r"price\s*:\s*(\d+)\s*,\s*//\s*商品金額", html)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass

    return _parse_price_text(html)


def _extract_release_from_text(text: str) -> Optional[str]:
    m = _RELEASE_RE.search(text)
    if not m:
        return None
    year_text, month_text, day_or_period = m.groups()
    if not month_text:
        return None
    from datetime import datetime, timezone, timedelta

    year = int(year_text) if year_text else datetime.now(
        timezone(timedelta(hours=9))
    ).year
    month = int(month_text)
    if not day_or_period:
        return f"{year:04d}-{month:02d}"
    if day_or_period.endswith("日"):
        return f"{year:04d}-{month:02d}-{int(day_or_period[:-1]):02d}"
    return f"{year:04d}-{month:02d}-{day_or_period}"


def _meta(soup: BeautifulSoup, key: str) -> str:
    tag = soup.find("meta", attrs={"property": key}) or soup.find(
        "meta", attrs={"name": key}
    )
    if tag and tag.get("content"):
        return str(tag["content"]).strip()
    return ""


def _product_dict(
    *,
    name: str,
    source_url: str,
    shop: str = "",
    unit_cost: Optional[float] = None,
    image_url: str = "",
    ip: str = "",
    barcode: str = "",
    search_text: str = "",
    release_date: Optional[str] = None,
) -> dict[str, Any]:
    name = (name or "").strip()
    if not ip:
        ip = _guess_ip(f"{name} {search_text}".strip())
    ship_at, ship_period = map_release_to_expected_ship(release_date)
    return {
        "name": name,
        "shop": shop or _shop_from_url(source_url),
        "unit_cost": unit_cost,
        "image_url": image_url.strip(),
        "source_url": source_url.strip(),
        "ip": ip,
        "barcode": (barcode or "").strip(),
        "expected_ship_at": ship_at,
        "expected_ship_period": ship_period,
        "release_date": release_date,
    }


async def _fetch(
    client: httpx.AsyncClient, url: str, *, timeout: float = 25.0
) -> httpx.Response:
    return await client.get(url, follow_redirects=True, timeout=timeout)


class RetailerAccessBlockedError(RuntimeError):
    """A retailer sent a waiting-room, bot-wall, or rate-limit response."""


def _is_retailer_access_blocked(url: str, resp: httpx.Response) -> bool:
    if resp.status_code in (403, 429, 503):
        return True
    html = resp.text
    return (is_hmv_url(url) and is_hmv_empty_shell(html)) or (
        is_biccamera_url(url) and is_biccamera_blocked_page(html)
    )


async def _fetch_retailer_html(
    client: httpx.AsyncClient, url: str
) -> Optional[httpx.Response]:
    """Retry HMV/Bic Camera waiting-room and transient access responses."""
    is_hmv = is_hmv_url(url)
    is_biccamera = is_biccamera_url(url)
    if not (is_hmv or is_biccamera):
        try:
            return await _fetch(client, url)
        except httpx.HTTPError:
            return None

    for attempt in range(3):
        try:
            resp = await _fetch(client, url, timeout=12.0)
        except httpx.HTTPError:
            resp = None
        if resp is not None and not _is_retailer_access_blocked(url, resp):
            return resp
        if attempt < 2:
            await asyncio.sleep(1.5 * (attempt + 1))

    shop = "HMV.co.jp" if is_hmv else "Bic Camera"
    raise RetailerAccessBlockedError(shop)


def _shopify_product_json_url(url: str) -> Optional[str]:
    path = urlparse(url).path
    if "/products/" not in path:
        return None
    # strip query; append .json to product path
    base = url.split("?")[0].rstrip("/")
    if base.endswith(".json"):
        return base
    return base + ".json"


def _shopify_collection_json_url(url: str) -> Optional[str]:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    m = re.search(r"/collections/([^/]+)", path)
    if not m:
        return None
    handle = m.group(1)
    if handle == "all":
        return f"{parsed.scheme}://{parsed.netloc}/products.json?limit=50"
    return (
        f"{parsed.scheme}://{parsed.netloc}/collections/{handle}/products.json?limit=50"
    )


def _normalize_image_url(url: str, base: str = "") -> str:
    text = (url or "").strip()
    if not text:
        return ""
    if text.startswith("//"):
        text = "https:" + text
    elif text.startswith("/") and base:
        text = urljoin(base.rstrip("/") + "/", text.lstrip("/"))
    return text


def _shopify_image_url(item: dict[str, Any], base: str = "") -> str:
    """Shopify list/detail JSON may put the pic in images[], image, or featured_image."""
    images = item.get("images") or []
    if isinstance(images, list):
        for img in images:
            if isinstance(img, dict):
                src = _normalize_image_url(str(img.get("src") or ""), base)
                if src:
                    return src
            elif isinstance(img, str):
                src = _normalize_image_url(img, base)
                if src:
                    return src
    for key in ("image", "featured_image"):
        raw = item.get(key)
        if isinstance(raw, dict):
            src = _normalize_image_url(str(raw.get("src") or ""), base)
            if src:
                return src
        elif isinstance(raw, str):
            src = _normalize_image_url(raw, base)
            if src:
                return src
    # Some catalog payloads only expose variant featured images.
    for variant in item.get("variants") or []:
        if not isinstance(variant, dict):
            continue
        featured = variant.get("featured_image")
        if isinstance(featured, dict):
            src = _normalize_image_url(str(featured.get("src") or ""), base)
            if src:
                return src
    return ""


def _from_shopify_product(item: dict[str, Any], shop_host: str, base: str) -> dict[str, Any]:
    handle = item.get("handle") or ""
    title = str(item.get("title") or handle)
    image_url = _shopify_image_url(item, base)
    variants = item.get("variants") or []
    unit_cost = None
    if variants:
        try:
            unit_cost = float(variants[0].get("price"))
        except (TypeError, ValueError):
            unit_cost = None
    product_type = str(item.get("product_type") or "")
    vendor = str(item.get("vendor") or "")
    tags = item.get("tags") or []
    if isinstance(tags, str):
        tags_text = tags
    else:
        tags_text = " ".join(str(t) for t in tags)
    body = BeautifulSoup(str(item.get("body_html") or ""), "html.parser").get_text(
        " ", strip=True
    )
    search_text = " ".join(p for p in (vendor, product_type, tags_text, body) if p)
    release_date = _extract_release_from_text(body) if body else None
    source_url = f"{base}/products/{handle}" if handle else base
    barcode = extract_jan_from_shopify_product(item) or ""
    return _product_dict(
        name=title,
        source_url=source_url,
        shop=shop_host,
        unit_cost=unit_cost,
        image_url=image_url,
        barcode=barcode,
        search_text=search_text,
        release_date=release_date,
    )


async def _scrape_shopify_product(
    client: httpx.AsyncClient, url: str
) -> Optional[dict[str, Any]]:
    json_url = _shopify_product_json_url(url)
    if not json_url:
        return None
    try:
        resp = await _fetch(client, json_url)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception:
        return None
    product = data.get("product") if isinstance(data, dict) else None
    if not isinstance(product, dict):
        return None
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    return _from_shopify_product(product, _shop_from_url(url), base)


async def _enrich_missing_shopify_images(
    client: httpx.AsyncClient,
    products: list[dict[str, Any]],
    *,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """List endpoints sometimes omit images; pull product.json for the first N blanks."""
    filled = 0
    for product in products:
        if product.get("image_url"):
            continue
        if filled >= limit:
            break
        source = product.get("source_url") or ""
        detail = await _scrape_shopify_product(client, source)
        filled += 1
        if detail and detail.get("image_url"):
            product["image_url"] = detail["image_url"]
            if not product.get("unit_cost") and detail.get("unit_cost") is not None:
                product["unit_cost"] = detail["unit_cost"]
        if detail and not product.get("barcode") and detail.get("barcode"):
            product["barcode"] = detail["barcode"]
    return products


async def _scrape_shopify_collection(
    client: httpx.AsyncClient, url: str
) -> Optional[list[dict[str, Any]]]:
    json_url = _shopify_collection_json_url(url)
    if not json_url:
        return None
    try:
        resp = await _fetch(client, json_url)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception:
        return None
    products = data.get("products") if isinstance(data, dict) else None
    if not isinstance(products, list):
        return None
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    shop = _shop_from_url(url)
    items = [
        _from_shopify_product(p, shop, base) for p in products if isinstance(p, dict)
    ]
    return await _enrich_missing_shopify_images(client, items)


async def _scrape_shopify_shop(
    client: httpx.AsyncClient, url: str
) -> Optional[list[dict[str, Any]]]:
    """Fetch up to 250 Shopify products from a shop root or /products page."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path not in ("", "/products"):
        return None
    base = f"{parsed.scheme}://{parsed.netloc}"
    shop = _shop_from_url(url)
    products: list[dict[str, Any]] = []
    for page in range(1, 6):
        try:
            resp = await _fetch(
                client, f"{base}/products.json?limit=50&page={page}"
            )
            if resp.status_code != 200:
                break
            data = resp.json()
        except Exception:
            return None if not products else products
        batch = data.get("products") if isinstance(data, dict) else None
        if not isinstance(batch, list):
            return None if not products else products
        products.extend(
            _from_shopify_product(product, shop, base)
            for product in batch
            if isinstance(product, dict)
        )
        if len(batch) < 50:
            break
    if not products:
        return None
    return await _enrich_missing_shopify_images(client, products)


def _is_generic_site_image(url: str) -> bool:
    """JumpCS etc. put a site-wide ogp/logo into og:image — skip those."""
    text = (url or "").lower()
    if not text:
        return True
    bad_tokens = (
        "/ogp.",
        "/ogp/",
        "og-image",
        "/logo.",
        "/logo-",
        "/assets/img/ogp",
        "apple-touch-icon",
        "favicon",
    )
    return any(token in text for token in bad_tokens)


def _json_ld_products(soup: BeautifulSoup) -> list[dict[str, Any]]:
    import json

    products: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        type_value = node.get("@type")
        types = (
            [type_value]
            if isinstance(type_value, str)
            else list(type_value or [])
        )
        if any(str(t).lower() == "product" for t in types):
            products.append(node)
        for value in node.values():
            if isinstance(value, (dict, list)):
                walk(value)

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        walk(data)
    return products


def _first_json_ld_image(product: dict[str, Any]) -> str:
    image = product.get("image")
    if isinstance(image, str):
        return image
    if isinstance(image, list):
        for item in image:
            if isinstance(item, str) and item.strip():
                return item
            if isinstance(item, dict):
                url = item.get("url") or item.get("contentUrl") or item.get("src")
                if url:
                    return str(url)
    if isinstance(image, dict):
        url = image.get("url") or image.get("contentUrl") or image.get("src")
        if url:
            return str(url)
    return ""


def _pick_html_product_image(soup: BeautifulSoup, page_url: str) -> str:
    candidates: list[str] = []
    for key in (
        "twitter:image",
        "twitter:image:src",
        "og:image:secure_url",
        "og:image",
    ):
        value = _meta(soup, key)
        if value:
            candidates.append(value)

    link = soup.find("link", attrs={"rel": "image_src"})
    if link and link.get("href"):
        candidates.append(str(link["href"]))

    for selector in (
        "img[src*='/img/goods/']",
        "img[data-src*='/img/goods/']",
        "img[src*='imgz.jp']",
        "img[data-src*='imgz.jp']",
        "img.product__media",
        "img.product-single__photo",
        "media-gallery img",
        ".product__media img",
        "img[src*='cdn.shopify.com']",
        "img[data-src*='cdn.shopify.com']",
    ):
        for tag in soup.select(selector):
            candidate = (
                tag.get("src")
                or tag.get("data-src")
                or tag.get("data-original")
                or ""
            )
            if not candidate and tag.get("srcset"):
                candidate = str(tag["srcset"]).split(",")[0].strip().split(" ")[0]
            if candidate:
                candidates.append(str(candidate))

    # Prefer goods / product paths over site-wide OGP logos.
    ranked: list[tuple[int, str]] = []
    for raw in candidates:
        absolute = _normalize_image_url(raw, page_url)
        if not absolute or _is_generic_site_image(absolute):
            continue
        score = 0
        lower = absolute.lower()
        if "/img/goods/" in lower or "/goods/" in lower or "imgz.jp" in lower:
            score += 50
        if "/l/" in lower or "/L/" in absolute:
            score += 10
        if "twitter" in lower:
            score += 5
        ranked.append((score, absolute))
    if not ranked:
        return ""
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def _clean_product_name(name: str) -> str:
    text = (name or "").strip()
    if not text:
        return ""
    # JumpCS title: "商品名: 分类|店名" or og title "商品詳細 | 店名"
    if ":" in text and "商品詳細" not in text:
        left, right = text.split(":", 1)
        if len(left.strip()) >= 4 and ("|" in right or "ストア" in right):
            text = left.strip()
    for sep in ("|", "｜"):
        if sep in text:
            head = text.split(sep, 1)[0].strip()
            if head and head not in ("商品詳細", "商品详情"):
                text = head
                break
    if text in ("商品詳細", "商品详情"):
        return ""
    return text


async def _scrape_html(client: httpx.AsyncClient, url: str) -> Optional[dict[str, Any]]:
    resp = await _fetch_retailer_html(client, url)
    if resp is None:
        return None

    from app.scrapers.zozo import (
        classify_fetch,
        fetch_failure_message,
        html_looks_gone,
        is_zozo_url,
    )

    body = resp.text or ""
    if is_zozo_url(url):
        kind = classify_fetch(
            status_code=resp.status_code, body=body, page_url=str(resp.url)
        )
        if kind != "ok":
            raise ValueError(
                fetch_failure_message(
                    kind, url=url, status_code=resp.status_code
                )
            )
        if html_looks_gone(body):
            raise ValueError(fetch_failure_message("gone", url=url))

    if resp.status_code != 200:
        return None
    return parse_product_html(body, str(resp.url))


def parse_product_html(html: str, page_url: str = "") -> Optional[dict[str, Any]]:
    """Parse a product from raw HTML (fetch result or staff paste)."""
    if not (html or "").strip():
        return None

    soup = BeautifulSoup(html, "html.parser")
    if not page_url:
        page_url = _meta(soup, "og:url") or ""
        if not page_url:
            link = soup.find("link", attrs={"rel": "canonical"})
            if link and link.get("href"):
                page_url = str(link["href"]).strip()
    page_url = _clean_url(page_url) if page_url else page_url

    ld_products = _json_ld_products(soup)
    ld = ld_products[0] if ld_products else {}

    name = _clean_product_name(str(ld.get("name") or ""))
    if not name:
        h1 = soup.find("h1")
        name = _clean_product_name(h1.get_text(strip=True) if h1 else "")
    if not name:
        name = _clean_product_name(
            (soup.title.string if soup.title else "") or ""
        )
    if not name:
        name = _clean_product_name(_meta(soup, "og:title"))

    # Prefer page gallery / twitter product shot (often /img/goods/L/) over
    # JSON-LD thumbnails (/img/goods/S/) or site-wide og:image logos.
    image_url = _pick_html_product_image(soup, page_url)
    if not image_url:
        image_url = _normalize_image_url(_first_json_ld_image(ld), page_url)
        if image_url and _is_generic_site_image(image_url):
            image_url = ""

    unit_cost = None
    offers = ld.get("offers")
    if isinstance(offers, list) and offers:
        offers = offers[0]
    if isinstance(offers, dict) and offers.get("price") is not None:
        try:
            unit_cost = float(str(offers["price"]).replace(",", ""))
        except ValueError:
            unit_cost = None
    if unit_cost is None:
        unit_cost = _parse_price_from_page(soup, html)

    # ZOZO: shop slug + CDN image fallback when meta image missing.
    from app.scrapers.zozo import (
        goods_id_from_url,
        image_url_from_goods_id,
        is_zozo_url,
        shop_slug_from_url,
    )

    shop = _shop_from_url(page_url) if page_url else ""
    if page_url and is_zozo_url(page_url):
        slug = shop_slug_from_url(page_url)
        if slug:
            shop = f"zozo.jp/{slug}"
        if not image_url:
            gid = goods_id_from_url(page_url)
            if gid:
                image_url = image_url_from_goods_id(gid)

    if not name:
        return None
    barcode = extract_jan_from_html(html, soup) or ""
    return _product_dict(
        name=name,
        source_url=page_url,
        shop=shop,
        unit_cost=unit_cost,
        image_url=image_url,
        barcode=barcode,
        search_text=soup.get_text(" ", strip=True)[:2000],
        release_date=_extract_release_from_text(html),
    )


async def scrape_html_document(html: str, source_url: str = "") -> dict[str, Any]:
    from app.scrapers.zozo import (
        gone_message,
        html_looks_gone,
        is_zozo_order_detail_html,
        is_zozo_order_list_html,
        is_zozo_url,
        orders_to_scrape_products,
        parse_zozo_order_detail_html,
    )

    # ZOZO 注文内容の詳細 — import as multi-line order (preferred over PDP parse).
    if is_zozo_order_detail_html(html):
        orders = parse_zozo_order_detail_html(html)
        if not orders or not orders[0].get("lines"):
            raise ValueError(
                "检测到 ZOZO 订单详情页，但未能解析出商品行。"
                "请确认复制的是「注文内容の詳細」整页源代码。"
            )
        order = orders[0]
        products = orders_to_scrape_products(orders)
        for product in products:
            if not product.get("ip"):
                product["ip"] = _guess_ip(product.get("name") or "")
        fee = order.get("shipping_fee")
        total = order.get("order_total")
        fee_text = f"，运费 ¥{int(fee)}" if fee is not None else ""
        total_text = f"，实付 ¥{int(total)}" if total is not None else ""
        return {
            "kind": "list",
            "products": products,
            "message": (
                f"已从 ZOZO 订单详情解析 {len(products)} 行"
                f"（注文番号 {order.get('order_ref')}{fee_text}{total_text}），请核对后导入"
            ),
            "order_ref": order.get("order_ref") or "",
            "shipping_fee": fee,
            "order_total": total,
        }

    if is_zozo_order_list_html(html):
        raise ValueError(
            "检测到 ZOZO 注文履歴列表页。请打开某一笔订单的「注文詳細・各種手続き」，"
            "再「查看网页源代码」全选复制粘贴（详情页含运费与分色明细）。"
        )

    page_hint = source_url or ""
    if html_looks_gone(html) and (
        is_zozo_url(page_hint) or "zozo.jp" in (html[:4000].lower())
    ):
        raise ValueError(gone_message(page_hint or "https://zozo.jp/"))

    product = parse_product_html(html, source_url)
    if not product:
        raise ValueError(
            "无法从粘贴的 HTML 解析商品。请确认复制的是整页源代码（含 og:title / 价格）。"
        )
    return {
        "kind": "list",
        "products": [product],
        "message": "已从粘贴的页面 HTML 解析 1 件，请核对后导入",
    }


async def scrape_url(url: str) -> dict[str, Any]:
    """
    Always returns a product list so every URL uses batch-import UI.
    """
    url = _clean_url(url)

    # HobbySearch / 1999.co.jp — dedicated parser (Cloudflare-hostile to httpx).
    from app.scrapers.hobbysearch import is_1999_url, scrape_1999_product
    from app.scrapers.asobistore import is_asobi_url, parse_asobi_product_html
    from app.scrapers.zozo import blocked_message, is_zozo_url

    if is_1999_url(url):
        product = await scrape_1999_product(url)
        if product:
            return {
                "kind": "list",
                "products": [product],
                "message": "已从 1999.co.jp（HobbySearch）抓取 1 件，勾选后批量导入",
            }
        raise ValueError(
            "1999.co.jp 抓取失败（可能被 Cloudflare 拦截）。可改用 curl 可访问的网络环境后重试。"
        )

    async with httpx.AsyncClient(headers=HEADERS) as client:
        if is_asobi_url(url) and "/products/detail/" in urlparse(url).path:
            try:
                resp = await _fetch(client, url)
                if resp.status_code == 200:
                    product = parse_asobi_product_html(resp.text, str(resp.url))
                    if product and product.get("unit_cost") is not None:
                        return {
                            "kind": "list",
                            "products": [product],
                            "message": "已从 asobi store 商品页抓取 1 件（主价 #selling_price）",
                        }
            except Exception:
                pass
        # Shop roots and /products use the Shopify catalog API, capped at 5 pages.
        shop_items = await _scrape_shopify_shop(client, url)
        if shop_items:
            return {
                "kind": "list",
                "products": shop_items,
                "message": f"已从店铺解析 {len(shop_items)} 件（最多 250 件），勾选后批量导入",
            }

        # Collection / series page (Shopify first — best for multi-character sets)
        if "/collections/" in urlparse(url).path:
            items = await _scrape_shopify_collection(client, url)
            if items:
                return {
                    "kind": "list",
                    "products": items,
                    "message": f"已从系列页解析 {len(items)} 件（Shopify），勾选后批量导入",
                }

        # Single product: Shopify JSON then HTML fallback
        product = await _scrape_shopify_product(client, url)
        if product:
            return {
                "kind": "list",
                "products": [product],
                "message": "已从 Shopify 商品页抓取 1 件，勾选后批量导入",
            }

        try:
            product = await _scrape_html(client, url)
        except RetailerAccessBlockedError as exc:
            if str(exc) == "HMV.co.jp":
                raise ValueError(
                    "HMV.co.jp 返回空白 NetFunnel 等候页（访问过频）。"
                    "已自动重试，请稍后 1–2 分钟再试。"
                ) from exc
            raise ValueError(
                "Bic Camera 暂时拒绝访问或响应过慢（可能访问过频）。"
                "已自动重试，请稍后 1–2 分钟再试。"
            ) from exc
        if product:
            return {
                "kind": "list",
                "products": [product],
                "message": "已从页面元数据抓取 1 件，价格/IP 可能不准，请核对后批量导入",
            }

    if is_zozo_url(url):
        raise ValueError(blocked_message(url))

    raise ValueError(
        "无法解析该链接。Shopify 店铺、商品/系列页最稳；其他站点依赖 og:title / og:image。"
        "若浏览器能打开，可复制整页源代码粘贴到抓取框。"
    )
