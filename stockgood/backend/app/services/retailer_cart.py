"""FEATURE: RETAILER_CART — template import + per-shop cart open.

Does not checkout or pay. Shopify and FutureShop open a cart URL in the staff
browser. MakeShop and asobi store submit the shop's own add-to-cart form there.
Mixed shops stay split: one cart and one inventory order per host.
"""

from __future__ import annotations

import csv
import io
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, quote, unquote, urlparse

from openpyxl import load_workbook

# kind=shopify: /products/{handle} + /cart/{variant_id}:{qty}
# tax=exclusive: Shopify JSON is 税抜 (Bushiroad); display 税込 = * 1.1
# tax=inclusive: JSON price matches storefront 税込
SHOP_CATALOG: tuple[dict[str, str], ...] = (
    {
        "host": "bushiroad-store.com",
        "label": "Bushiroad Store",
        "kind": "shopify",
        "tax": "exclusive",
    },
    {
        "host": "lafary.shop",
        "label": "LAFARY",
        "kind": "shopify",
        "tax": "inclusive",
    },
    {
        "host": "animeshi.jp",
        "label": "Animeshi",
        "kind": "shopify",
        "tax": "inclusive",
    },
    {
        "host": "cocollabo.net",
        "label": "Cocollabo",
        "kind": "shopify",
        "tax": "inclusive",
    },
    {
        "host": "qinocop.com",
        "label": "Qinocop",
        "kind": "shopify",
        "tax": "inclusive",
    },
    {
        "host": "mono-mo.com",
        "label": "mono-mo",
        "kind": "shopify",
        "tax": "inclusive",
    },
    {
        "host": "cho-kaguyahime-officialstore.bookstores.jp",
        "label": "超かぐや姫 bookstores",
        "kind": "shopify",
        "tax": "inclusive",
    },
    {
        "host": "jumpcs.shueisha.co.jp",
        "label": "集英社 JUMP CS",
        "kind": "futureshop",
        "tax": "inclusive",
    },
    {
        "host": "store.kadokawa.co.jp",
        "label": "KADOKAWA",
        "kind": "futureshop",
        "tax": "inclusive",
    },
    {
        "host": "miraithings.com",
        "label": "miraithings",
        "kind": "makeshop",
        "tax": "inclusive",
    },
    {
        "host": "pricafe.shop",
        "label": "pricafe",
        "kind": "makeshop",
        "tax": "inclusive",
    },
    {
        "host": "store-gk.com",
        "label": "store-gk",
        "kind": "makeshop",
        "tax": "inclusive",
    },
    {
        "host": "shop.asobistore.jp",
        "label": "asobi store",
        "kind": "asobi",
        "tax": "inclusive",
    },
    {
        "host": "hmv.co.jp",
        "label": "HMV&BOOKS",
        "kind": "hmv",
        "tax": "inclusive",
    },
)
SHOP = SHOP_CATALOG[0]["host"]
ALLOWED_HOSTS = tuple(spec["host"] for spec in SHOP_CATALOG)
_SHOP_BY_HOST = {spec["host"]: spec for spec in SHOP_CATALOG}
_PRODUCT_RE = re.compile(r"/products/([^/?#]+)", re.I)
_FUTURESHOP_RE = re.compile(r"/shop/g/g([^/?#]+)", re.I)
_MAKESHOP_RE = re.compile(r"/(?:view/item|shopdetail)/([^/?#]+)", re.I)
_ASOBI_RE = re.compile(r"/products/detail/([^/?#]+)", re.I)
_HMV_ITEM_RE = re.compile(r"^item_.+_(\d+)$", re.I)
_URL_HEADERS = ("链接", "url", "source_url", "商品链接", "href")
_QTY_HEADERS = ("数量", "qty", "点数", "quantity")
MAX_BYTES = 2 * 1024 * 1024

TEMPLATE_CSV = (
    "链接,数量\n"
    "https://bushiroad-store.com/products/2000326637643,1\n"
)

FetchProduct = Callable[[str], dict[str, Any]]


class RetailerCartNotConnected(RuntimeError):
    """Raised when the shop has no cart adapter."""


def _canonical_host(host: str) -> str:
    h = (host or "").lower()
    if h.startswith("www."):
        h = h[4:]
    return h


def shop_spec_for_host(host: str) -> Optional[dict[str, str]]:
    h = _canonical_host(host)
    if not h:
        return None
    if h in _SHOP_BY_HOST:
        return _SHOP_BY_HOST[h]
    for spec in SHOP_CATALOG:
        allowed = spec["host"]
        if h == allowed or h.endswith("." + allowed):
            return spec
    return None


def shop_from_url(url: str) -> str:
    parsed = urlparse(url or "")
    spec = shop_spec_for_host(parsed.netloc)
    return spec["host"] if spec else ""


def shop_label(host: str) -> str:
    spec = shop_spec_for_host(host)
    return spec["label"] if spec else _canonical_host(host)


def _host_ok(host: str) -> bool:
    return shop_spec_for_host(host) is not None


def _shop_kind(host_or_url: str) -> str:
    text = host_or_url or ""
    if "://" in text:
        spec = shop_spec_for_host(urlparse(text).netloc)
    else:
        spec = shop_spec_for_host(text)
    return spec["kind"] if spec else ""


def product_id_from_url(url: str) -> str:
    parsed = urlparse(url or "")
    path = parsed.path or ""
    kind = _shop_kind(url)
    if kind == "futureshop":
        match = _FUTURESHOP_RE.search(path)
        return unquote(match.group(1)) if match else ""
    if kind == "makeshop":
        match = _MAKESHOP_RE.search(path)
        return unquote(match.group(1)).strip("/") if match else ""
    if kind == "asobi":
        match = _ASOBI_RE.search(path)
        return unquote(match.group(1)) if match else ""
    if kind == "hmv":
        query_sku = (parse_qs(parsed.query).get("sku") or [""])[0].strip()
        if query_sku.isdigit():
            return query_sku
        segment = unquote(path.rstrip("/").split("/")[-1])
        match = _HMV_ITEM_RE.match(segment)
        return match.group(1) if match else ""
    match = _PRODUCT_RE.search(path)
    if not match:
        return ""
    handle = unquote(match.group(1))
    if handle.lower().endswith(".json"):
        handle = handle[: -len(".json")]
    return handle


def variant_query_from_url(url: str) -> str:
    qs = parse_qs(urlparse(url or "").query)
    raw = (qs.get("variant") or [""])[0]
    return str(raw).strip()


def _merge_key(url: str, handle: str) -> str:
    shop = shop_from_url(url)
    variant = variant_query_from_url(url)
    base = f"{shop}|{handle}" if shop else handle
    return f"{base}|{variant}" if variant else base


def _clean_url(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    if not text.startswith(("http://", "https://")):
        if "." in text:
            text = "https://" + text
        else:
            return ""
    return text.split("#")[0].strip()


def _header_index(cells: list[str], names: tuple[str, ...]) -> Optional[int]:
    lowered = [str(c or "").strip().lower() for c in cells]
    for i, cell in enumerate(lowered):
        for name in names:
            if cell == name.lower():
                return i
    return None


def _parse_qty(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if not text:
        return None
    m = re.search(r"(\d+)", text)
    if not m:
        return None
    try:
        n = int(m.group(1))
    except ValueError:
        return None
    return n if n >= 1 else None


def _empty_line(
    *,
    source_url: str = "",
    qty: int = 1,
    product_id: str = "",
    shop: str = "",
    skip_reason: str = "",
) -> dict[str, Any]:
    return {
        "source_url": source_url,
        "qty": qty,
        "product_id": product_id,
        "shop": shop,
        "skip_reason": skip_reason,
        "name": "",
        "image_url": "",
        "unit_cost": None,
        "variant_id": "",
    }


def _classify_url(url: str) -> tuple[str, str, str, str]:
    """Return (status, product_id/handle, skip_reason, shop)."""
    if not url:
        return "skipped", "", "empty_url", ""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return "skipped", "", "invalid_url", ""
    shop = shop_from_url(url)
    if not shop:
        return "skipped", "", "host_not_allowed", ""
    handle = product_id_from_url(url)
    if not handle:
        return "skipped", "", "not_product_page", shop
    return "eligible", handle, "", shop


def _rows_from_table(table: list[list[Any]]) -> list[tuple[str, Any]]:
    if not table:
        return []
    header_idx = 0
    url_col = 0
    qty_col = 1 if table and len(table[0]) > 1 else 0
    found = False
    for i, row in enumerate(table[:8]):
        cells = [str(c or "").strip() for c in row]
        u = _header_index(cells, _URL_HEADERS)
        q = _header_index(cells, _QTY_HEADERS)
        if u is not None:
            header_idx = i
            url_col = u
            qty_col = q if q is not None else (u + 1 if len(row) > u + 1 else u)
            found = True
            break
    start = header_idx + 1 if found else 0
    out: list[tuple[str, Any]] = []
    for row in table[start:]:
        if not row:
            continue
        url = row[url_col] if url_col < len(row) else ""
        qty = row[qty_col] if qty_col < len(row) else ""
        if str(url or "").strip() == "" and str(qty or "").strip() == "":
            continue
        out.append((str(url or ""), qty))
    return out


def _decode_csv_text(raw: bytes) -> str:
    for enc in ("utf-8-sig", "gbk", "cp936"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8-sig", errors="replace")


def _read_csv(raw: bytes) -> list[list[Any]]:
    text = _decode_csv_text(raw)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    return [list(row) for row in reader]


def _read_xlsx(raw: bytes) -> list[list[Any]]:
    wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    try:
        ws = wb.active
        if ws is None:
            return []
        return [list(row) for row in ws.iter_rows(values_only=True)]
    finally:
        wb.close()


def _display_unit_cost(shop: str, raw_price: float) -> float:
    spec = shop_spec_for_host(shop)
    if spec and spec.get("tax") == "exclusive":
        from app.scrapers.preview import _bushiroad_tax_inclusive

        return _bushiroad_tax_inclusive(raw_price)
    return round(float(raw_price), 2)


def _apply_product_preview(line: dict[str, Any], product: dict[str, Any]) -> None:
    from app.scrapers.preview import _shopify_image_url

    handle = str(line.get("product_id") or "")
    line["name"] = str(product.get("title") or handle)
    line["image_url"] = _shopify_image_url(product) or ""
    variant: dict[str, Any] = {}
    try:
        variant = pick_variant(product, str(line.get("source_url") or ""))
    except ValueError:
        variants = [v for v in (product.get("variants") or []) if isinstance(v, dict)]
        variant = variants[0] if variants else {}
    if variant.get("id") is not None:
        line["variant_id"] = str(variant.get("id"))
    unit_cost = None
    raw_price = variant.get("price") if variant else None
    try:
        if raw_price is not None and str(raw_price).strip() != "":
            unit_cost = float(raw_price)
    except (TypeError, ValueError):
        unit_cost = None
    if unit_cost is not None:
        unit_cost = _display_unit_cost(str(line.get("shop") or ""), unit_cost)
    line["unit_cost"] = unit_cost


def _enrich_futureshop_lines(lines: list[dict[str, Any]], *, workers: int = 8) -> None:
    if not lines:
        return

    def _one(line: dict[str, Any]) -> None:
        from app.scrapers.futureshop import parse_futureshop_product_html
        from app.scrapers.preview import HEADERS

        url = str(line.get("source_url") or "")
        try:
            import httpx

            with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=25.0) as client:
                resp = client.get(url)
            if resp.status_code != 200:
                raise ValueError(f"HTTP {resp.status_code}")
            product = parse_futureshop_product_html(resp.text, str(resp.url))
            if not product or not product.get("name"):
                raise ValueError("empty product")
            line["name"] = str(product.get("name") or "")
            line["image_url"] = str(product.get("image_url") or "")
            line["unit_cost"] = product.get("unit_cost")
        except Exception:
            line["name"] = str(line.get("product_id") or "")
            line["image_url"] = ""
            line["unit_cost"] = None

    max_workers = max(1, min(int(workers), len(lines)))
    if max_workers == 1:
        _one(lines[0])
        return
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(_one, lines))


def _enrich_eligible_lines(
    lines: list[dict[str, Any]],
    fetch_product: FetchProduct,
    *,
    workers: int = 8,
) -> None:
    if not lines:
        return

    def _one(line: dict[str, Any]) -> None:
        try:
            product = fetch_product(str(line.get("source_url") or ""))
            if not isinstance(product, dict):
                raise ValueError("product is not a dict")
            _apply_product_preview(line, product)
        except Exception:
            line["name"] = str(line.get("product_id") or "")
            line["image_url"] = ""
            line["unit_cost"] = None

    max_workers = max(1, min(int(workers), len(lines)))
    if max_workers == 1:
        _one(lines[0])
        return
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(_one, lines))


def _shop_counts(lines: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, int] = {}
    order: list[str] = []
    for line in lines:
        shop = str(line.get("shop") or "") or "?"
        if shop not in counts:
            counts[shop] = 0
            order.append(shop)
        counts[shop] += 1
    return [f"{shop_label(shop)} {counts[shop]}种" for shop in order]


def parse_template(
    raw: bytes,
    filename: str = "",
    *,
    fetch_product: Optional[FetchProduct] = None,
    enrich: bool = False,
) -> dict[str, Any]:
    if not raw:
        raise ValueError("模板文件是空的")
    if len(raw) > MAX_BYTES:
        raise ValueError("模板文件过大（上限 2MB）")
    name = (filename or "").lower()
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        table = _read_xlsx(raw)
    else:
        table = _read_csv(raw)
    pairs = _rows_from_table(table)
    if not pairs:
        raise ValueError("模板里没有可解析的行。请用列：链接,数量")

    eligible: dict[str, dict[str, Any]] = {}
    eligible_order: list[str] = []
    skipped: list[dict[str, Any]] = []

    for url_raw, qty_raw in pairs:
        url = _clean_url(url_raw)
        qty = _parse_qty(qty_raw)
        status, handle, reason, shop = _classify_url(url)
        if qty is None:
            skipped.append(
                _empty_line(
                    source_url=url or str(url_raw).strip(),
                    qty=1,
                    product_id=handle,
                    shop=shop,
                    skip_reason="qty_invalid",
                )
            )
            continue
        if status != "eligible":
            skipped.append(
                _empty_line(
                    source_url=url or str(url_raw).strip(),
                    qty=qty,
                    product_id=handle,
                    shop=shop,
                    skip_reason=reason,
                )
            )
            continue
        key = _merge_key(url, handle)
        if key not in eligible:
            eligible[key] = _empty_line(
                source_url=url,
                qty=qty,
                product_id=handle,
                shop=shop,
            )
            eligible_order.append(key)
        else:
            eligible[key]["qty"] = int(eligible[key]["qty"]) + qty

    lines = [eligible[k] for k in eligible_order]
    should_enrich = enrich or fetch_product is not None
    if should_enrich and lines:
        getter = fetch_product or _fetch_product_json
        shopify_lines = [
            line for line in lines if _shop_kind(str(line.get("shop") or "")) == "shopify"
        ]
        _enrich_eligible_lines(shopify_lines, getter)
    if enrich and lines:
        futureshop_lines = [
            line
            for line in lines
            if _shop_kind(str(line.get("shop") or "")) == "futureshop"
        ]
        _enrich_futureshop_lines(futureshop_lines)
    for line in lines:
        if str(line.get("name") or "").strip():
            continue
        if _shop_kind(str(line.get("shop") or "")) == "shopify":
            continue
        line["name"] = str(line.get("product_id") or "")
    shop_text = "、".join(_shop_counts(lines)) if lines else "无"
    return {
        "eligible": lines,
        "skipped": skipped,
        "allowed_hosts": list(ALLOWED_HOSTS),
        "shops": [dict(spec) for spec in SHOP_CATALOG],
        "message": (
            f"白名单 {len(ALLOWED_HOSTS)} 店：可加购 {len(lines)} 种"
            f"（{shop_text}；跳过 {len(skipped)} 行）。"
            "按店铺分类加购，不会结算、不会付款。"
        ),
    }


def _fetch_product_json(page_url: str) -> dict[str, Any]:
    from app.scrapers.preview import HEADERS, _shopify_product_json_url

    json_url = _shopify_product_json_url(page_url)
    if not json_url:
        raise ValueError("不是 Shopify 商品页")
    import httpx

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=25.0) as client:
        resp = client.get(json_url)
    if resp.status_code != 200:
        raise ValueError(f"商品 JSON 失败 HTTP {resp.status_code}: {page_url}")
    try:
        data = resp.json()
    except Exception as exc:
        raise ValueError(f"商品 JSON 无法解析: {page_url}") from exc
    product = data.get("product") if isinstance(data, dict) else None
    if not isinstance(product, dict):
        raise ValueError(f"商品 JSON 无 product: {page_url}")
    return product


def pick_variant(product: dict[str, Any], page_url: str) -> dict[str, Any]:
    variants = [v for v in (product.get("variants") or []) if isinstance(v, dict)]
    if not variants:
        raise ValueError("商品没有 variants")
    wanted = variant_query_from_url(page_url)
    if wanted.isdigit():
        vid = int(wanted)
        for variant in variants:
            try:
                if int(variant.get("id")) == vid:
                    return variant
            except (TypeError, ValueError):
                continue
        raise ValueError(f"链接中的 variant={wanted} 不在该商品上")
    for variant in variants:
        if variant.get("available") is True:
            return variant
    return variants[0]


def build_cart_permalink(host: str, pairs: list[tuple[int, int]]) -> str:
    merged: dict[int, int] = {}
    order: list[int] = []
    for variant_id, qty in pairs:
        if variant_id not in merged:
            merged[variant_id] = 0
            order.append(variant_id)
        merged[variant_id] += max(1, int(qty))
    if not order:
        raise ValueError("没有可加购的 variant")
    body = ",".join(f"{vid}:{merged[vid]}" for vid in order)
    canon = _canonical_host(host)
    spec = shop_spec_for_host(canon)
    shop = spec["host"] if spec else canon
    if not shop:
        raise ValueError("没有店铺域名")
    return f"https://{shop}/cart/{body}"


def group_items_by_shop(items: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for item in items:
        url = _clean_url(str(item.get("source_url") or ""))
        shop = str(item.get("shop") or "").strip() or shop_from_url(url)
        if not shop:
            shop = _canonical_host(urlparse(url).netloc)
        spec = shop_spec_for_host(shop)
        shop = spec["host"] if spec else shop
        if shop not in groups:
            groups[shop] = []
            order.append(shop)
        groups[shop].append(item)
    return [(shop, groups[shop]) for shop in order]


def _resolved_line(
    item: dict[str, Any],
    *,
    url: str,
    shop: str,
    handle: str,
    qty: int,
    name: str = "",
    variant_id: str = "",
) -> dict[str, Any]:
    return {
        "source_url": url,
        "qty": qty,
        "product_id": handle,
        "shop": shop,
        "skip_reason": "",
        "variant_id": variant_id,
        "name": name or str(item.get("name") or handle),
        "image_url": str(item.get("image_url") or ""),
        "unit_cost": item.get("unit_cost"),
    }


def build_futureshop_urls(shop: str, pairs: list[tuple[str, int]]) -> list[str]:
    host = shop_spec_for_host(shop)
    canon = host["host"] if host else _canonical_host(shop)
    urls: list[str] = []
    for goods, qty in pairs:
        urls.append(
            f"https://{canon}/shop/cart/cart.aspx?goods={quote(goods, safe='')}&qty={qty}"
        )
    if not urls:
        raise ValueError("没有可加购的商品号")
    return urls


def build_hmv_urls(pairs: list[tuple[str, int]]) -> list[str]:
    """HMV inbasket adds one unit per visit. quantity= does not change the cart qty."""
    urls: list[str] = []
    for sku, qty in pairs:
        if not re.fullmatch(r"\d+", sku):
            raise ValueError(f"HMV SKU 无效: {sku}")
        urls.extend(
            [f"https://www.hmv.co.jp/basket/inbasket/?sku={sku}"] * max(1, int(qty))
        )
    if not urls:
        raise ValueError("没有可加购的 HMV SKU")
    if len(urls) > 30:
        raise ValueError("HMV 一次最多打开 30 次加购（每条链接加 1 件）")
    return urls


def build_makeshop_brand_info(pairs: list[tuple[str, int]]) -> str:
    parts: list[str] = []
    for code, qty in pairs:
        kind_code = "1" if re.fullmatch(r"\d{12}", code) else "0"
        parts.append(f"{kind_code},{code},{qty},N")
    if not parts:
        raise ValueError("没有可加购的商品码")
    if len(parts) > 50:
        raise ValueError("MakeShop 一次最多 50 件")
    return "||".join(parts)


def _cart_payload(
    *,
    shop: str,
    kind: str,
    resolved: list[dict[str, Any]],
    cart_url: str = "",
    cart_urls: Optional[list[str]] = None,
    method: str = "get",
    posts: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    return {
        "shop": shop,
        "label": shop_label(shop),
        "kind": kind,
        "cart_url": cart_url,
        "cart_urls": cart_urls or ([cart_url] if cart_url else []),
        "method": method,
        "posts": posts or [],
        "items": resolved,
    }


def add_to_cart(
    items: list[dict[str, Any]],
    *,
    fetch_product: Optional[FetchProduct] = None,
) -> dict[str, Any]:
    """Resolve Shopify variants and return cart permalinks split by shop."""
    if not items:
        raise ValueError("没有可加购的行。请先解析模板并确认白名单链接。")
    getter = fetch_product or _fetch_product_json
    carts: list[dict[str, Any]] = []
    all_resolved: list[dict[str, Any]] = []
    for shop, shop_items in group_items_by_shop(items):
        kind = _shop_kind(shop) or "shopify"
        resolved: list[dict[str, Any]] = []
        if kind == "shopify":
            pairs: list[tuple[int, int]] = []
            for item in shop_items:
                url = _clean_url(str(item.get("source_url") or ""))
                status, handle, reason, line_shop = _classify_url(url)
                qty = _parse_qty(item.get("qty"))
                if qty is None or status != "eligible" or not handle:
                    raise ValueError(
                        f"含有非白名单或不完整行（{reason or 'qty_invalid'}），已拒绝加购。"
                    )
                host = line_shop or shop
                product = getter(url)
                variant = pick_variant(product, url)
                try:
                    variant_id = int(variant.get("id"))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"variant id 无效: {url}") from exc
                pairs.append((variant_id, qty))
                resolved.append(
                    _resolved_line(
                        item,
                        url=url,
                        shop=host,
                        handle=handle,
                        qty=qty,
                        name=str(product.get("title") or handle),
                        variant_id=str(variant_id),
                    )
                )
            cart_url = build_cart_permalink(shop, pairs)
            carts.append(
                _cart_payload(
                    shop=shop,
                    kind="shopify",
                    resolved=resolved,
                    cart_url=cart_url,
                )
            )
        elif kind == "futureshop":
            goods_pairs: list[tuple[str, int]] = []
            for item in shop_items:
                url = _clean_url(str(item.get("source_url") or ""))
                status, handle, reason, line_shop = _classify_url(url)
                qty = _parse_qty(item.get("qty"))
                if qty is None or status != "eligible" or not handle:
                    raise ValueError(
                        f"含有非白名单或不完整行（{reason or 'qty_invalid'}），已拒绝加购。"
                    )
                goods_pairs.append((handle, qty))
                resolved.append(
                    _resolved_line(
                        item,
                        url=url,
                        shop=line_shop or shop,
                        handle=handle,
                        qty=qty,
                    )
                )
            urls = build_futureshop_urls(shop, goods_pairs)
            carts.append(
                _cart_payload(
                    shop=shop,
                    kind="futureshop",
                    resolved=resolved,
                    cart_url=urls[0],
                    cart_urls=urls,
                )
            )
        elif kind == "makeshop":
            code_pairs: list[tuple[str, int]] = []
            for item in shop_items:
                url = _clean_url(str(item.get("source_url") or ""))
                status, handle, reason, line_shop = _classify_url(url)
                qty = _parse_qty(item.get("qty"))
                if qty is None or status != "eligible" or not handle:
                    raise ValueError(
                        f"含有非白名单或不完整行（{reason or 'qty_invalid'}），已拒绝加购。"
                    )
                code_pairs.append((handle, qty))
                resolved.append(
                    _resolved_line(
                        item,
                        url=url,
                        shop=line_shop or shop,
                        handle=handle,
                        qty=qty,
                    )
                )
            action = f"https://{shop}/api/basket/add.html"
            carts.append(
                _cart_payload(
                    shop=shop,
                    kind="makeshop",
                    resolved=resolved,
                    cart_url=action,
                    cart_urls=[],
                    method="post",
                    posts=[
                        {
                            "action": action,
                            "fields": {
                                "brand_info": build_makeshop_brand_info(code_pairs)
                            },
                        }
                    ],
                )
            )
        elif kind == "hmv":
            sku_pairs: list[tuple[str, int]] = []
            for item in shop_items:
                url = _clean_url(str(item.get("source_url") or ""))
                status, handle, reason, line_shop = _classify_url(url)
                qty = _parse_qty(item.get("qty"))
                if qty is None or status != "eligible" or not handle:
                    raise ValueError(
                        f"含有非白名单或不完整行（{reason or 'qty_invalid'}），已拒绝加购。"
                    )
                sku_pairs.append((handle, qty))
                resolved.append(
                    _resolved_line(
                        item,
                        url=url,
                        shop=line_shop or shop,
                        handle=handle,
                        qty=qty,
                    )
                )
            urls = build_hmv_urls(sku_pairs)
            carts.append(
                _cart_payload(
                    shop=shop,
                    kind="hmv",
                    resolved=resolved,
                    cart_url=urls[0],
                    cart_urls=urls,
                )
            )
        elif kind == "asobi":
            posts: list[dict[str, Any]] = []
            for item in shop_items:
                url = _clean_url(str(item.get("source_url") or ""))
                status, handle, reason, line_shop = _classify_url(url)
                qty = _parse_qty(item.get("qty"))
                if qty is None or status != "eligible" or not handle:
                    raise ValueError(
                        f"含有非白名单或不完整行（{reason or 'qty_invalid'}），已拒绝加购。"
                    )
                posts.append(
                    {
                        "action": f"https://{shop}/cart",
                        "fields": {"ec_number": handle, "num": str(qty)},
                    }
                )
                resolved.append(
                    _resolved_line(
                        item,
                        url=url,
                        shop=line_shop or shop,
                        handle=handle,
                        qty=qty,
                    )
                )
            carts.append(
                _cart_payload(
                    shop=shop,
                    kind="asobi",
                    resolved=resolved,
                    cart_url=f"https://{shop}/cart",
                    cart_urls=[],
                    method="post",
                    posts=posts,
                )
            )
        else:
            raise RetailerCartNotConnected(f"{shop} 还没有购物车适配")
        all_resolved.extend(resolved)
    first = carts[0] if carts else {}
    first_url = str(first.get("cart_url") or "")
    labels = "、".join(str(c["label"]) for c in carts)
    return {
        "cart_url": first_url,
        "carts": carts,
        "items": all_resolved,
        "message": (
            f"已按店铺生成购物车（{labels}，共 {len(all_resolved)} 种）。"
            "将在浏览器打开对方购物车，请自行核对。不会结算、不会付款。"
        ),
    }


def build_order_payload(
    eligible: list[dict[str, Any]],
    order_ref: str,
    total_jpy: float,
) -> dict[str, Any]:
    """Map preview lines + staff-pasted shop order_ref/total to OrderCreate.

    There is no orders.order_total column. OrderOut.order_total is
    goods_total + shipping_fee. Store the residual as shipping_fee so the
    computed total matches the pasted 总价, and keep the exact figure in note.
    Mixed shops must be split first (one inventory order per host).
    """
    ref = (order_ref or "").strip()
    if not ref:
        raise ValueError("请填写订单号")
    try:
        total = float(total_jpy)
    except (TypeError, ValueError) as exc:
        raise ValueError("请填写总价") from exc
    if total < 0:
        raise ValueError("总价不能为负数")
    if not eligible:
        raise ValueError("没有可加购行，无法生成库存订单")

    grouped = group_items_by_shop(eligible)
    if len(grouped) != 1:
        names = "、".join(shop_label(shop) for shop, _ in grouped)
        raise ValueError(f"请按店铺分别生成库存订单（当前混有：{names}）")
    shop = grouped[0][0]

    lines: list[dict[str, Any]] = []
    goods = 0.0
    priced = False
    qty_sum = 0
    for row in grouped[0][1]:
        qty = _parse_qty(row.get("qty")) or 1
        qty_sum += qty
        name = str(row.get("name") or row.get("product_id") or "").strip()
        if not name:
            raise ValueError("可加购行缺少商品名")
        unit_cost = row.get("unit_cost")
        try:
            if unit_cost is not None and str(unit_cost).strip() != "":
                unit_cost = float(unit_cost)
                goods += unit_cost * qty
                priced = True
            else:
                unit_cost = None
        except (TypeError, ValueError):
            unit_cost = None
        lines.append(
            {
                "name": name,
                "shop": shop,
                "qty": qty,
                "unit_cost": unit_cost,
                "image_url": str(row.get("image_url") or ""),
                "source_url": str(row.get("source_url") or ""),
            }
        )
    shipping_fee = (
        max(0.0, round(total - goods, 2)) if priced else round(total, 2)
    )
    return {
        "order_ref": ref,
        "shop": shop,
        "order_qty": qty_sum,
        "shipping_fee": shipping_fee,
        "note": f"对方总价 JPY {total:g}",
        "lines": lines,
    }
