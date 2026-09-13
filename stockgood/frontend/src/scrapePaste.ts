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
      const eeoPd = path.match(/\/products\/detail\/(\d+)/i);
      if (eeoPd && host.includes("eeo.today")) {
        return `eeo:product:${eeoPd[1]}`;
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
