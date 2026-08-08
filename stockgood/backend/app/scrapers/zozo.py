"""ZOZOTOWN (zozo.jp) helpers.

- Product pages: often Akamai-blocked for bots; paste HTML or classify blocked vs gone.
- Order detail pages: paste 「注文内容の詳細」 HTML to import lines + shipping.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Optional
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

_GOODS_RE = re.compile(r"/goods(?:-sale)?/(\d{6,})(?:/|$|\?)", re.I)
_GID_DID_RE = re.compile(r"[?&]gid=(\d+).*?[?&]did=(\d+)|[?&]did=(\d+).*?[?&]gid=(\d+)", re.I)
_YEN_RE = re.compile(r"[\d,]+")

_GONE_MARKERS = (
    "お探しの商品は見つかりませんでした",
    "お探しのページは見つかりませんでした",
    "お探しの商品が見つかりません",
    "この商品は取扱いを終了",
    "取扱いを終了いたしました",
    "取扱いを終了しました",
    "販売を終了しました",
    "ページが見つかりません",
    "指定されたページは存在しません",
    "goods not found",
    "product not found",
)

ZozoFetchKind = Literal["blocked", "gone", "http_error", "ok"]


def is_zozo_url(url: str) -> bool:
    host = urlparse(url or "").netloc.lower()
    return host == "zozo.jp" or host.endswith(".zozo.jp")


def goods_id_from_url(url: str) -> Optional[str]:
    path = urlparse(url or "").path
    m = _GOODS_RE.search(path)
    return m.group(1) if m else None


def shop_slug_from_url(url: str) -> str:
    path = urlparse(url or "").path
    m = re.search(r"/shop/([^/]+)/", path, re.I)
    if not m:
        return ""
    slug = m.group(1).strip()
    return "" if slug.lower() in ("", "www") else slug


def color_did_from_url(url: str) -> Optional[str]:
    qs = parse_qs(urlparse(url or "").query)
    did = (qs.get("did") or [None])[0]
    return str(did) if did else None


def image_url_from_goods_id(goods_id: str, color_index: int = 1) -> str:
    gid = (goods_id or "").strip()
    if not gid.isdigit():
        return ""
    shard = gid[-3:]
    idx = max(1, int(color_index))
    return f"https://c.imgz.jp/{shard}/{gid}/{gid}_{idx}_d_500.jpg"


def is_akamai_block(status_code: int, body: str = "") -> bool:
    text = body or ""
    if status_code == 403 and (
        "Access Denied" in text
        or "edgesuite.net" in text
        or "Reference#" in text
        or "Reference&#32;" in text
    ):
        return True
    if status_code in (403, 429) and "Access Denied" in text:
        return True
    return False


def html_looks_gone(html: str) -> bool:
    if not html:
        return False
    head = html[:12000]
    lower_head = head.lower()
    if "access denied" in lower_head and "edgesuite" in lower_head:
        return False
    if any(m in head for m in _GONE_MARKERS):
        return True
    title_m = re.search(r"<title[^>]*>(.*?)</title>", head, re.I | re.S)
    if title_m:
        title = re.sub(r"\s+", " ", title_m.group(1)).strip()
        if any(m in title for m in _GONE_MARKERS) or re.search(r"\b404\b", title):
            return True
    return False


def goods_cdn_exists(goods_id: str, *, timeout: float = 8.0) -> Optional[bool]:
    """True if CDN still has an image; False if missing; None if probe failed."""
    image = image_url_from_goods_id(goods_id, 1)
    if not image:
        return None
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            resp = client.head(image)
            if resp.status_code == 200:
                return True
            if resp.status_code in (403, 405):
                resp = client.get(image, headers={"Range": "bytes=0-0"})
                if resp.status_code in (200, 206):
                    return True
            if resp.status_code in (403, 404):
                alt = image_url_from_goods_id(goods_id, 8)
                resp2 = client.head(alt)
                if resp2.status_code == 200:
                    return True
                return False
            return False
    except httpx.HTTPError:
        return None


def classify_fetch(*, status_code: int, body: str, page_url: str = "") -> ZozoFetchKind:
    if is_akamai_block(status_code, body):
        return "blocked"
    if status_code == 404 or html_looks_gone(body):
        return "gone"
    if status_code != 200:
        return "http_error"
    if html_looks_gone(body):
        return "gone"
    return "ok"


def fetch_failure_message(
    kind: ZozoFetchKind,
    *,
    url: str = "",
    status_code: int | None = None,
) -> str:
    gid = goods_id_from_url(url) if url else None
    listed: Optional[bool] = None
    if kind == "blocked" and gid:
        listed = goods_cdn_exists(gid)

    if kind == "blocked":
        base = (
            "zozo.jp 商品页被 Akamai 拦截（自动化请求 403），通常不是下架。"
            "请用浏览器打开 →「查看网页源代码」全选复制 → 粘贴到抓取框再解析。"
        )
        if listed is True:
            return (
                base
                + f" CDN 图仍在（goods {gid}），商品多半未下架，只是抓取被拦。"
            )
        if listed is False:
            return (
                base
                + f" 且 CDN 图不存在（goods {gid}），浏览器里也请确认是否已下架/删除。"
            )
        return base

    if kind == "gone":
        extra = f"（goods {gid}）" if gid else ""
        return (
            f"zozo.jp 商品可能已下架或不存在{extra}。"
            "页面返回 404/「見つかりません」类提示；请换有效链接，或粘贴浏览器里仍能打开的源码。"
        )

    code = f" HTTP {status_code}" if status_code is not None else ""
    return f"zozo.jp 抓取失败{code}。可粘贴浏览器整页 HTML 再试。"


def blocked_message(url: str = "") -> str:
    return fetch_failure_message("blocked", url=url)


def gone_message(url: str = "") -> str:
    return fetch_failure_message("gone", url=url)


# --- Order detail HTML (会員 注文内容の詳細) ---


def is_zozo_order_detail_html(html: str) -> bool:
    text = html or ""
    if "注文内容の詳細" not in text:
        return False
    return (
        'name="oid"' in text
        or "thumbBox detail" in text
        or "orderhistory/detail" in text.lower()
        or "Pages-member-orderhistory-detail" in text
    )


def is_zozo_order_list_html(html: str) -> bool:
    """Detect 注文履歴 list page.

    Must NOT match product PDP / order-detail pages that only share the global
    header link to `/_member/orderhistory/` (substring ``orderhistory`` is common).
    """
    text = html or ""
    if is_zozo_order_detail_html(text):
        return False
    if 'id="orderListWrapper"' in text:
        return True
    if "Pages-member-orderhistory-index" in text:
        return True
    if 'name="ohtype"' in text and 'name="ohterm"' in text:
        # List-page search form (期間 / 発送前|発送済み) — not present on PDP.
        return True
    if 'class="orderList"' in text and "注文詳細・各種手続き" in text:
        return True
    return False



def _parse_yen(text: str) -> Optional[float]:
    cleaned = (text or "").replace("\xa0", " ").replace(",", "")
    if cleaned.strip() in ("", "-", "—"):
        return None
    m = _YEN_RE.search(cleaned)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _table_cell_text(soup: BeautifulSoup, label: str) -> str:
    for th in soup.select("th"):
        if th.get_text(" ", strip=True) != label:
            continue
        td = th.find_next_sibling("td")
        if td:
            return td.get_text(" ", strip=True)
    return ""


def _table_amount(soup: BeautifulSoup, label: str) -> Optional[float]:
    for th in soup.select(".bottomTbl th, table.resist th"):
        if th.get_text(" ", strip=True) != label and label not in th.get_text(
            " ", strip=True
        ):
            continue
        # Prefer exact header match for 送料 / 支払い金額 / 商品合計
        if th.get_text(" ", strip=True) != label:
            continue
        td = th.find_next_sibling("td")
        if td:
            return _parse_yen(td.get_text(" ", strip=True))
    return None


def _gid_did_from_href(href: str) -> tuple[Optional[str], Optional[str]]:
    qs = parse_qs(urlparse(href or "").query)
    gid = (qs.get("gid") or [None])[0]
    did = (qs.get("did") or [None])[0]
    if gid or did:
        return (str(gid) if gid else None, str(did) if did else None)
    m = _GID_DID_RE.search(href or "")
    if not m:
        return None, None
    if m.group(1) and m.group(2):
        return m.group(1), m.group(2)
    return m.group(4), m.group(3)


def _shop_slug_from_image_href(href: str) -> str:
    m = re.search(r"/shop/([^/]+)/image\.html", href or "", re.I)
    return m.group(1) if m else ""


def _qty_from_tax_text(text: str) -> int:
    m = re.search(r"数量\s*[：:]\s*(\d+)", text or "")
    if m:
        return max(1, int(m.group(1)))
    return 1


def _line_from_thumb_row(row: Tag) -> Optional[dict[str, Any]]:
    detail = row.select_one(".thumbDetail")
    if not detail:
        return None
    name_el = detail.select_one(".itemName")
    name = name_el.get_text(" ", strip=True) if name_el else ""
    if not name:
        return None
    color = ""
    color_el = detail.select_one(".colorName")
    if color_el:
        color = color_el.get_text(" ", strip=True)
    unit_cost = None
    price_el = detail.select_one(".priceNum")
    if price_el:
        unit_cost = _parse_yen(price_el.get_text(" ", strip=True))
    tax_el = detail.select_one(".tax")
    qty = _qty_from_tax_text(tax_el.get_text(" ", strip=True) if tax_el else "")

    gid = did = None
    shop_slug = ""
    image_url = ""
    for a in row.select("a[href]"):
        href = str(a.get("href") or "")
        g, d = _gid_did_from_href(href)
        if g:
            gid = g
        if d:
            did = d
        slug = _shop_slug_from_image_href(href)
        if slug:
            shop_slug = slug
    img = row.select_one("img[src*='imgz.jp'], .thumb img[src]")
    if img and img.get("src"):
        image_url = str(img["src"]).strip()
        if image_url.startswith("//"):
            image_url = "https:" + image_url

    source_url = ""
    if gid:
        slug = shop_slug or "zozotown"
        source_url = f"https://zozo.jp/shop/{slug}/goods/{gid}/"
        if did:
            source_url += f"?did={did}"
        if not image_url:
            image_url = image_url_from_goods_id(gid)

    display = f"{name}（{color}）" if color else name
    shop = f"zozo.jp/{shop_slug}" if shop_slug else "zozo.jp"
    return {
        "name": display,
        "shop": shop,
        "qty": qty,
        "unit_cost": unit_cost,
        "image_url": image_url,
        "source_url": source_url,
        "barcode": "",
        "ip": "",
    }


def parse_zozo_order_detail_html(html: str) -> list[dict[str, Any]]:
    """Parse one ZOZO member order-detail page into [{order_ref, shipping_fee, order_total, lines}]."""
    if not html or not is_zozo_order_detail_html(html):
        return []
    soup = BeautifulSoup(html, "html.parser")

    order_ref = ""
    oid = soup.select_one('input[name="oid"]')
    if oid and oid.get("value"):
        order_ref = str(oid["value"]).strip()
    if not order_ref:
        for th in soup.select("th"):
            if "注文番号" in th.get_text(" ", strip=True):
                td = th.find_next_sibling("td")
                if td:
                    order_ref = td.get_text(" ", strip=True)
                    break

    shipping_fee = _table_amount(soup, "送料")
    order_total = _table_amount(soup, "支払い金額")
    goods_total = _table_amount(soup, "商品合計")
    if order_total is None:
        ttl = soup.select_one(".ttlPrice, span.ttlPrice")
        if ttl:
            order_total = _parse_yen(ttl.get_text(" ", strip=True))

    ordered_at = _table_cell_text(soup, "注文日")
    tracking_raw = _table_cell_text(soup, "伝票番号")
    tracking_no = re.sub(r"\D", "", tracking_raw) if tracking_raw else ""
    status = ""
    current = soup.select_one(
        '[data-phase-item-status="current"] .c-phase-indicator-complete-item__label, '
        '[data-phase-item-status="current"] .c-phase-indicator-item__label'
    )
    if current:
        status = current.get_text(" ", strip=True)

    lines: list[dict[str, Any]] = []
    for row in soup.select("tr.thumbBox.detail"):
        line = _line_from_thumb_row(row)
        if line:
            lines.append(line)

    if not lines:
        return []
    shop = lines[0].get("shop") or "zozo.jp"
    return [
        {
            "order_ref": order_ref,
            "shipping_fee": shipping_fee,
            "order_total": order_total,
            "goods_total": goods_total,
            "ordered_at": ordered_at,
            "tracking_no": tracking_no or None,
            "status_text": status,
            "shop": shop,
            "lines": lines,
        }
    ]


def orders_to_scrape_products(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten order lines into scrape-product dicts (one row per line)."""
    products: list[dict[str, Any]] = []
    for order in orders:
        for line in order.get("lines") or []:
            products.append(
                {
                    "name": line.get("name") or "",
                    "shop": line.get("shop") or order.get("shop") or "zozo.jp",
                    "unit_cost": line.get("unit_cost"),
                    "image_url": line.get("image_url") or "",
                    "source_url": line.get("source_url") or "",
                    "ip": line.get("ip") or "",
                    "barcode": line.get("barcode") or "",
                    "expected_ship_at": None,
                    "expected_ship_period": None,
                    "release_date": None,
                    "qty": line.get("qty") or 1,
                }
            )
    return products
