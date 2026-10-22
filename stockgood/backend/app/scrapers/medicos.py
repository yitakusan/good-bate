"""medicos-e-shop.net（MEDICOS ONLINE SHOP）購入履歴詳細 HTML 解析。

粘贴マイページ「購入履歴詳細」整页源代码 → 多行商品 + 注文番号/送料/合计。
EC-CUBE：`ec-orderDelivery__item` / `ec-imageGrid`；主列表通常无商品链接、无 JAN。
メール配信履歴正文含「商品コード：【BOXJAN:…】」时可回填 barcode。
商品 ID 优先取自 `/products/detail/{id}`，否则取图片文件名。相同 pid / 品名自动合并数量。

样例：templates/medicos-e-shop.mypage-history.fixture.html
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag  # type: ignore[import-untyped]

SHOP = "medicos-e-shop.net"
BASE = "https://medicos-e-shop.net"

_YEN_RE = re.compile(r"[¥￥]\s*([\d,]+)")
_QTY_RE = re.compile(r"[×xX]\s*([\d,]+)")
_NAME_QTY_RE = re.compile(r"\s*[×xX]\s*[\d,]+\s*$")
_DETAIL_RE = re.compile(r"/products/detail/(\d+)", re.I)
_IMG_ID_RE = re.compile(
    r"(?:/html)?/upload/save_image/([^/?#]+?)\.(?:jpe?g|png|webp|gif)",
    re.I,
)
_ORDER_NO_RE = re.compile(r"ご注文番号\s*[:：]?\s*([0-9]{6,})")
_MAIL_CODE_RE = re.compile(
    r"商品コード[：:]\s*【?\s*(?:BOXJAN[:：])?\s*([0-9]{8,14})\s*】?\s*"
    r"商品名[：:]\s*(.+?)\s*"
    r"単価[：:]\s*[¥￥]?\s*([\d,]+)\s*"
    r"数量[：:]\s*([\d,]+)",
    re.S,
)


def is_medicos_url(url: str) -> bool:
    host = urlparse(url or "").netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return (
        host == "medicos-e-shop.net"
        or host.endswith(".medicos-e-shop.net")
        or host == "medicos-e.net"
        or host.endswith(".medicos-e.net")
    )


def is_medicos_order_detail_html(html: str) -> bool:
    """Detect MEDICOS ONLINE SHOP 購入履歴詳細 page."""
    text = html or ""
    if not text:
        return False
    lower = text.lower()
    has_site = (
        "medicos-e-shop.net" in lower
        or "medicos-e.net" in lower
        or "medicos online shop" in lower
        or "メディコス" in text
    )
    has_page = (
        "購入履歴詳細" in text
        or "ご注文履歴詳細" in text
        or "page_mypage_history" in lower
        or "mypage/history" in lower
        or "ec-orderdelivery" in lower
    )
    has_items = (
        ("ec-orderdelivery__item" in lower or "ec-imagegrid" in lower)
        and ("￥" in text or "¥" in text or "円" in text)
    )
    if has_items and has_site:
        return True
    return bool(has_site and has_page and has_items)


def _text(el: Optional[Tag]) -> str:
    if not el:
        return ""
    return el.get_text(" ", strip=True)


def _parse_yen(text: str) -> Optional[float]:
    m = _YEN_RE.search(text or "")
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_qty(text: str) -> int:
    m = _QTY_RE.search(text or "")
    if not m:
        return 1
    try:
        return max(1, int(m.group(1).replace(",", "")))
    except ValueError:
        return 1


def _abs_url(src: str) -> str:
    src = (src or "").strip()
    if not src:
        return ""
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return urljoin(BASE + "/", src.lstrip("/"))
    return src


def _product_id_from_href(href: str) -> str:
    m = _DETAIL_RE.search(href or "")
    return m.group(1) if m else ""


def _product_id_from_img(src: str) -> str:
    m = _IMG_ID_RE.search(src or "")
    return m.group(1) if m else ""


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", (name or "").strip())


def _clean_name(name: str) -> str:
    return _NAME_QTY_RE.sub("", (name or "").strip()).strip()


def extract_medicos_order_ref(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for dt in soup.find_all("dt"):
        label = _text(dt)
        if "ご注文番号" in label or label == "注文番号":
            dd = dt.find_next_sibling("dd")
            digits = re.sub(r"\D", "", _text(dd))
            if len(digits) >= 6:
                return digits
    m = _ORDER_NO_RE.search(html or "")
    if m:
        return m.group(1)
    m = re.search(r"ご注文番号</dt>\s*<dd[^>]*>\s*([0-9]{6,})", html or "", re.I)
    return m.group(1) if m else ""


def _total_box_amount(soup: BeautifulSoup, labels: tuple[str, ...]) -> Optional[float]:
    for dl in soup.select(".ec-totalBox__spec, .ec-totalBox dl, dl"):
        dt = dl.find("dt")
        dd = dl.find("dd")
        if not dt or not dd:
            continue
        label = _text(dt)
        if any(lb == label or lb in label for lb in labels):
            value = _parse_yen(_text(dd))
            if value is not None:
                return value
    return None


def extract_medicos_shipping_fee(html: str) -> Optional[float]:
    soup = BeautifulSoup(html or "", "html.parser")
    value = _total_box_amount(soup, ("送料", "配送料"))
    if value is not None:
        return value
    m = re.search(r"送料[^\d¥￥]{0,40}[¥￥]\s*([\d,]+)", html or "")
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def extract_medicos_order_total(html: str) -> Optional[float]:
    soup = BeautifulSoup(html or "", "html.parser")
    price = soup.select_one(
        ".ec-totalBox__price, .ec-totalBox__total .ec-totalBox__price"
    )
    if price:
        value = _parse_yen(_text(price))
        if value is not None:
            return value
    value = _total_box_amount(soup, ("合計", "お支払い合計"))
    if value is not None:
        return value
    m = re.search(
        r"(?:お支払い合計|合計)[^\d¥￥]{0,40}[¥￥]\s*([\d,]+)",
        html or "",
    )
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def _mail_jan_by_name(html: str) -> dict[str, str]:
    """Parse BOXJAN / 商品コード from メール配信履歴 → normalized name → JAN."""
    mapping: dict[str, str] = {}
    soup = BeautifulSoup(html or "", "html.parser")
    bodies: list[str] = []
    for node in soup.select(".ec-orderMail__body, .ec-orderMail"):
        bodies.append(node.get_text("\n", strip=True))
    blob = "\n".join(bodies) if bodies else (html or "")
    sources = (
        blob,
        (html or "").replace("<br />", "\n").replace("<br>", "\n"),
    )
    for src in sources:
        for m in _MAIL_CODE_RE.finditer(src):
            code = m.group(1).strip()
            name = BeautifulSoup(m.group(2), "html.parser").get_text(" ", strip=True)
            key = _normalize_name(name)
            if key and code and key not in mapping:
                mapping[key] = code
    return mapping


def _line_from_item(item: Tag, jan_map: dict[str, str]) -> Optional[dict[str, Any]]:
    content = item.select_one(".ec-imageGrid__content") or item
    link = content.select_one("a[href*='/products/detail/']")
    if not link:
        link = item.select_one("a[href*='/products/detail/']")
    href = str(link.get("href") or "") if link else ""
    name = _clean_name(_text(link)) if link else ""

    qty = 1
    unit_cost: Optional[float] = None
    paragraphs = content.find_all("p")
    for p in paragraphs:
        raw = _text(p)
        if not raw:
            continue
        if "￥" in raw or "¥" in raw:
            unit_cost = _parse_yen(raw)
            qty_from_price = _parse_qty(raw)
            if qty_from_price > 1:
                qty = qty_from_price
        elif not name:
            name = _clean_name(raw)
            if "×" in raw or re.search(r"[xX]\s*\d", raw):
                qty = _parse_qty(raw)
        elif "×" in raw or re.search(r"[xX]\s*\d", raw):
            qty = _parse_qty(raw)

    if not name and paragraphs:
        name = _clean_name(_text(paragraphs[0]))
        qty = _parse_qty(_text(paragraphs[0]))

    if not name:
        return None

    if unit_cost is None:
        unit_cost = _parse_yen(_text(content))

    img = item.select_one("img[src], img[data-src]")
    image_src = ""
    if img:
        image_src = str(img.get("src") or img.get("data-src") or "")
    image_url = _abs_url(image_src)
    product_id = _product_id_from_href(href) or _product_id_from_img(image_src)
    source_url = _abs_url(href) if href else ""
    if product_id and not source_url and product_id.isdigit():
        source_url = f"{BASE}/products/detail/{product_id}"

    barcode = jan_map.get(_normalize_name(name), "")

    return {
        "name": name,
        "shop": SHOP,
        "unit_cost": unit_cost,
        "image_url": image_url,
        "source_url": source_url,
        "ip": "",
        "barcode": barcode,
        "expected_ship_at": None,
        "expected_ship_period": None,
        "release_date": None,
        "qty": qty,
        "product_id": product_id,
    }


def parse_medicos_order_detail_lines(html: str) -> list[dict[str, Any]]:
    """Parse raw order lines from MEDICOS 購入履歴詳細 HTML (before merge)."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    jan_map = _mail_jan_by_name(html)
    lines: list[dict[str, Any]] = []
    items = soup.select(".ec-orderDelivery__item")
    if not items:
        items = soup.select(".ec-imageGrid")
    for item in items:
        line = _line_from_item(item, jan_map)
        if line:
            lines.append(line)
    return lines


def merge_medicos_products(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge duplicate SKUs by product_id / source_url / name → sum qty."""
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for line in lines:
        key = (
            (line.get("product_id") or "").strip()
            or (line.get("source_url") or "").strip()
            or (line.get("name") or "").strip()
        )
        if not key:
            continue
        if key not in merged:
            merged[key] = {
                "name": line.get("name") or "",
                "shop": line.get("shop") or SHOP,
                "unit_cost": line.get("unit_cost"),
                "image_url": line.get("image_url") or "",
                "source_url": line.get("source_url") or "",
                "ip": line.get("ip") or "",
                "barcode": line.get("barcode") or "",
                "expected_ship_at": line.get("expected_ship_at"),
                "expected_ship_period": line.get("expected_ship_period"),
                "release_date": line.get("release_date"),
                "qty": int(line.get("qty") or 1),
                "product_id": line.get("product_id") or "",
            }
            order.append(key)
            continue
        cur = merged[key]
        cur["qty"] = int(cur.get("qty") or 0) + int(line.get("qty") or 1)
        if cur.get("unit_cost") is None and line.get("unit_cost") is not None:
            cur["unit_cost"] = line["unit_cost"]
        if not cur.get("image_url") and line.get("image_url"):
            cur["image_url"] = line["image_url"]
        if not cur.get("barcode") and line.get("barcode"):
            cur["barcode"] = line["barcode"]
        if not cur.get("product_id") and line.get("product_id"):
            cur["product_id"] = line["product_id"]
        if not cur.get("source_url") and line.get("source_url"):
            cur["source_url"] = line["source_url"]
    return [merged[k] for k in order]


def parse_medicos_order_detail_html(html: str) -> dict[str, Any]:
    """Parse MEDICOS 購入履歴詳細 HTML → products + order meta."""
    lines = parse_medicos_order_detail_lines(html)
    products = merge_medicos_products(lines)
    return {
        "products": products,
        "order_ref": extract_medicos_order_ref(html),
        "shipping_fee": extract_medicos_shipping_fee(html),
        "order_total": extract_medicos_order_total(html),
        "raw_line_count": len(lines),
    }
