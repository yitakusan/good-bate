/** Shared helpers: detect URL list vs HTML/JSON paste for scrape import. */

/** Strip accidental `https://` before raw HTML (causes Invalid IPv6 URL). */
export function normalizeHtmlPaste(raw: string): string {
  let text = raw.trim();
  if (/^https?:\/\/\s*</i.test(text)) {
    text = text.replace(/^https?:\/\//i, "").trim();
  }
  return text;
}

/** True when paste should go to scrape-html path (not URL fetch). */
export function looksLikeHtmlOrJsonPaste(raw: string): boolean {
  const text = normalizeHtmlPaste(raw);
  if (text.length < 80) return false;
  const head = text.slice(0, 12000);
  const lower = head.toLowerCase();
  const trimmed = text.trimStart();

  // &mall / zozo Network JSON
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    if (
      /mallskuid|itemname|shop-order-skus|mall_sku_id/i.test(head) &&
      /quantity|itemname|mallproductcodeid/i.test(head)
    ) {
      return true;
    }
  }

  if (
    lower.startsWith("<!doctype html") ||
    lower.startsWith("<html") ||
    (lower.includes("<html") && lower.includes("</html")) ||
    (lower.includes("<head") && lower.includes("<body") && lower.includes("og:title"))
  ) {
    return true;
  }

  // Elements outerHTML (&mall 注文履歴 after もっと見る)
  if (
    lower.includes("order-history-list") ||
    lower.includes("order-history-product") ||
    (lower.includes("mallskuid=") && (lower.includes("数量") || lower.includes("quantity")))
  ) {
    return true;
  }

  // Generic HTML fragment
  if (
    trimmed.startsWith("<") &&
    (lower.includes("</") || lower.includes("/>")) &&
    /<[a-z][\s\S]{40,}/i.test(head)
  ) {
    return true;
  }

  return false;
}

/** Parse URL list; never treat HTML/JSON paste as URLs. */
export function parseScrapeUrls(raw: string): string[] {
  if (looksLikeHtmlOrJsonPaste(raw)) return [];
  const seen = new Set<string>();
  const urls: string[] = [];
  for (const part of raw.split(/[\n\r,;\t]+/)) {
    let text = part.trim();
    if (!text) continue;
    text = text.replace(/^\d+[\.\)、]\s*/, "").replace(/^[-*•]\s*/, "");
    // Do not prefix https:// onto HTML/markup blobs.
    if (text.startsWith("<") || text.includes("</") || /mallskuid=/i.test(text)) {
      continue;
    }
    if (!/^https?:\/\//i.test(text) && text.includes(".")) {
      text = `https://${text}`;
    }
    if (!/^https?:\/\//i.test(text)) continue;
    if (/^https?:\/\/\s*</i.test(text)) continue;
    const key = text.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    urls.push(text);
  }
  return urls;
}

/**
 * Match key for scrape-collection merge (dedupe / JAN backfill).
 * vvstore product detail URLs collapse to product id so order HTML and PDP match.
 */
export function scrapeProductMatchKey(product: {
  source_url?: string | null;
  name?: string | null;
}): string {
  const rawUrl = (product.source_url || "").trim();
  if (rawUrl) {
    try {
      const withScheme = /^https?:\/\//i.test(rawUrl)
        ? rawUrl
        : `https://${rawUrl}`;
      const u = new URL(withScheme);
      const host = u.hostname.replace(/^www\./i, "").toLowerCase();
      const path = (u.pathname || "").replace(/\/+$/, "");
      const amnibusPd = path.match(/\/products\/detail\/(\d+)/i);
      if (amnibusPd && host.includes("amnibus.com")) {
        return `amnibus:product:${amnibusPd[1]}`;
      }
      const vv = path.match(/\/products\/detail\/(\d+)$/i);
      if (vv && host.includes("vvstore")) {
        return `vvstore:product:${vv[1]}`;
      }
      const sku = u.searchParams.get("sku");
      if (
        sku &&
        host.includes("sofmap") &&
        /product_detail/i.test(path)
      ) {
        return `sofmap:product:${sku}`;
      }
      const cystorePid =
        u.searchParams.get("pid") || u.searchParams.get("product_id");
      if (
        cystorePid &&
        host.includes("cystore") &&
        /ProductDetail/i.test(path)
      ) {
        return `cystore:product:${cystorePid}`;
      }
      const animatePd = path.match(/\/pd\/(\d+)/i);
      if (animatePd && host.includes("animate-onlineshop")) {
        return `animate:product:${animatePd[1]}`;
      }
      if (animatePd && host.includes("gamers.co.jp")) {
        return `gamers:product:${animatePd[1]}`;
      }
      const eeoPd = path.match(/\/products\/detail\/(\d+)/i);
      if (eeoPd && host.includes("eeo.today")) {
        return `eeo:product:${eeoPd[1]}`;
      }
      const lafaryPd = path.match(/\/products\/([^/?#]+)/i);
      if (lafaryPd && host.includes("lafary.shop")) {
        return `lafary:product:${lafaryPd[1]}`;
      }
      const medicosPd = path.match(/\/products\/detail\/(\d+)/i);
      if (
        medicosPd &&
        (host.includes("medicos-e-shop.net") || host.includes("medicos-e.net"))
      ) {
        return `medicos:product:${medicosPd[1]}`;
      }
      const yostarPd = path.match(/\/products\/detail\/(\d+)/i);
      if (yostarPd && host.includes("yostar.co.jp")) {
        return `yostar:product:${yostarPd[1]}`;
      }
      const storesItem = path.match(/\/items\/([0-9a-f]+)/i);
      if (storesItem && host.endsWith("stores.jp")) {
        return `stores:item:${storesItem[1]}`;
      }
      // BASE custom-domain receipts use /items/{numeric id}. The same id can
      // be two variations, so the name stays in the key.
      const baseItem = path.match(/\/items\/(\d{6,})$/i);
      if (baseItem && !host.endsWith("stores.jp")) {
        const name = (product.name || "").trim().toLowerCase();
        return name
          ? `base:${host}:item:${baseItem[1]}:${name}`
          : `base:${host}:item:${baseItem[1]}`;
      }
      // ZOZO: same goods id can have multiple color variants via ?did=
      // (dropping query would collapse その他7 / その他8 into one row).
      const makeshopId = path.match(/\/shopdetail\/(\d+)/i);
      if (makeshopId && host.includes("the-chara.com")) {
        return `thechara:goods:${makeshopId[1]}`;
      }
      if (makeshopId && host.includes("store-gk.com")) {
        return `storegk:goods:${makeshopId[1]}`;
      }
      if (makeshopId && host.includes("shop.twincre.com")) {
        return `twincre:goods:${makeshopId[1]}`;
      }
      const movicGoods = path.match(/\/shop\/g\/g([^/]+)/i);
      if (movicGoods && host.includes("movic.jp")) {
        return `movic:goods:${movicGoods[1].toLowerCase()}`;
      }
      if (movicGoods && host.includes("kadokawa.co.jp")) {
        return `kadokawa:goods:${movicGoods[1].toLowerCase()}`;
      }
      const yahooItem = path.match(/^\/([^/]+)\/([^/]+)\.html$/i);
      if (yahooItem && host === "store.shopping.yahoo.co.jp") {
        const name = (product.name || "").trim().toLowerCase();
        return name
          ? `yahoo:${yahooItem[1]}:${yahooItem[2]}:${name}`
          : `yahoo:${yahooItem[1]}:${yahooItem[2]}`;
      }
      const zozoGoods = path.match(/\/shop\/[^/]+\/goods\/(\d+)/i);
      if (zozoGoods && host.includes("zozo.jp")) {
        const did = u.searchParams.get("did") || "";
        return did
          ? `zozo:goods:${zozoGoods[1]}:did:${did}`
          : `zozo:goods:${zozoGoods[1]}`;
      }
      return `${host}${path}`.toLowerCase();
    } catch {
      return rawUrl
        .toLowerCase()
        .replace(/\/+$/, "")
        .split("?")[0]
        .split("#")[0];
    }
  }
  return (product.name || "").trim().toLowerCase();
}

/** Scrape-tab help: one row per site, listing accepted paste types. */
export type ScrapeSiteGuide = {
  id: string;
  name: string;
  supports: string[];
  note: string;
};

export const SCRAPE_SITE_GUIDE: ScrapeSiteGuide[] = [
  {
    id: "shopify",
    name: "Shopify 商品",
    supports: ["商品 URL", "系列 URL", "店铺 URL", "商品页源代码"],
    note: "链接可批量。bushiroad-store 单价按税抜再乘 1.1。",
  },
  {
    id: "shopify-order",
    name: "Shopify 新版顾客订单",
    supports: ["已渲染订单 HTML"],
    note: "检查元素复制「注文アイテム」。查看源代码是空壳。单价为税込。",
  },
  {
    id: "lafary",
    name: "lafary.shop",
    supports: ["订单页源代码"],
    note: "旧版「注文 #」整页源代码。含单价、数量、运费、注文番号。通常无 JAN。",
  },
  {
    id: "the-chara",
    name: "the-chara.com",
    supports: ["订单页源代码"],
    note: "THEキャラ「注文履歴」整页源代码。单价按税抜再乘 1.1。一页多笔时只勾选同一注文番号。",
  },
  {
    id: "twincre",
    name: "shop.twincre.com",
    supports: ["订单页源代码"],
    note: "ツインクル「注文履歴」整页源代码。小计标税込，单价不再乘 1.1。不读取送付先。",
  },
  {
    id: "storegk",
    name: "store-gk.com",
    supports: ["订单页源代码"],
    note: "注文履歴整页源代码。单价按税抜再乘 1.1。一页多笔时只勾选同一注文番号。",
  },
  {
    id: "zozo",
    name: "zozo.jp",
    supports: ["商品页源代码", "订单详情源代码"],
    note: "用「注文内容の詳細」。订单列表页不行。商品链接常被拦，改贴源代码。",
  },
  {
    id: "mall",
    name: "&mall",
    supports: ["Elements HTML", "订单 JSON"],
    note: "不要用查看源代码。点完もっと見る后复制列表，或贴 shop-order-skus JSON。",
  },
  {
    id: "vvstore",
    name: "vvstore.jp",
    supports: ["订单页源代码", "商品 URL"],
    note: "「ご注文履歴詳細」整页源代码。导入后可贴商品页回填 JAN。",
  },
  {
    id: "sofmap",
    name: "sofmap.com",
    supports: ["商品 URL", "商品页源代码", "订单页源代码"],
    note: "商品页含 JAN。订单用「お取引の詳細」整页源代码。",
  },
  {
    id: "cystore",
    name: "cystore.com",
    supports: ["订单页源代码"],
    note: "「購入履歴詳細」整页源代码。含单价、数量、运费、注文番号。通常无 JAN。",
  },
  {
    id: "amnibus",
    name: "amnibus.com",
    supports: ["订单卡片 HTML"],
    note: "粘贴一笔注文的 historyCard。价格是税込单价。无标价的景品按 0。订单页无条形码。多笔卡片请分开贴。",
  },
  {
    id: "aniplex",
    name: "online.aniplex.co.jp",
    supports: ["订单详情源代码"],
    note: "「購入履歴」里打开一笔注文后，粘贴整页源代码。単価（税込）是单价。商品代码不是条形码。",
  },
  {
    id: "movic",
    name: "movic.jp",
    supports: ["订单详情源代码"],
    note: "「購入履歴詳細」整页源代码。行内合计除以数量得到税込单价。購入履歴列表没有数量和单价。订单页无条形码。会再打开商品页，取主图。",
  },
  {
    id: "yahoo-shopping",
    name: "Yahoo!购物",
    supports: ["订单页源代码"],
    note: "「注文履歴詳細」整页源代码。单价为税込。同链接不同规格分开。订单页无条形码。",
  },
  {
    id: "animate",
    name: "animate-onlineshop.jp",
    supports: ["订单页源代码"],
    note: "「注文履歴」整页源代码。行内金额是小计，单价=小计除以数量。特典行跳过。商品图文件名校验通过时填入条形码。",
  },
  {
    id: "gamers",
    name: "gamers.co.jp",
    supports: ["订单页源代码"],
    note: "「注文履歴」里展开一笔注文后粘贴。N点旁边的金额是小计。会再打开商品页，取店舗予約用バーコード作为条形码。",
  },
  {
    id: "eeo",
    name: "eeo.today",
    supports: ["订单页源代码"],
    note: "「ご注文履歴詳細」整页源代码。邮件里的商品コード可回填 JAN。",
  },
  {
    id: "medicos",
    name: "medicos-e-shop.net",
    supports: ["订单页源代码"],
    note: "「購入履歴詳細」整页源代码。邮件 BOXJAN 可回填 JAN。",
  },
  {
    id: "yostar",
    name: "shop.yostar.co.jp",
    supports: ["商品 URL", "订单页已渲染 HTML", "订单 JSON", "商品 JSON"],
    note: "商品链接可直接抓。查看源代码是空壳。已打开的订单详情可整页复制。也可贴 Network 的 order/detail JSON。单价是单价行，小计不是单价。",
  },
  {
    id: "base",
    name: "BASE 购买确认",
    supports: ["收据页源代码"],
    note: "c.thebase.in 的「ご注文情報照会」整页源代码。单价为税込。同链接不同规格分开。不读取购买者和运单号。",
  },
  {
    id: "stores",
    name: "*.stores.jp",
    supports: ["商品 URL", "商品页源代码", "已渲染订单 HTML", "订单 JSON"],
    note: "注文用已渲染「購入詳細」，或 Network 的订单 JSON。行金额是小计。",
  },
  {
    id: "futureshop",
    name: "KADOKAWA / JUMP CS",
    supports: ["商品 URL"],
    note: "商品页直接抓取，单价税込。購入履歴詳細可粘贴源代码，行合计除以数量。13位商品代码校验通过时填入条形码。",
  },
  {
    id: "miraithings",
    name: "miraithings.com",
    supports: ["商品 URL", "商品页源代码"],
    note: "商品页直接抓取。",
  },
  {
    id: "asobi",
    name: "asobi store",
    supports: ["商品 URL"],
    note: "商品页直接抓取。订单页尚未接入。",
  },
  {
    id: "hobbysearch",
    name: "1999.co.jp",
    supports: ["商品 URL"],
    note: "商品链接直接抓取，含 JAN。",
  },
  {
    id: "hmv",
    name: "HMV / Bic Camera",
    supports: ["商品 URL", "商品页源代码"],
    note: "走通用商品页解析。访问过频时稍后重试。",
  },
];
