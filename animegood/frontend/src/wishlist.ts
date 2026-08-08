export type WishlistItem = {
  id: number;
  product_name: string;
  display_name_zh?: string | null;
  ip: string;
  shop: string;
  source_url: string;
  price: number | null;
  stock_status: string;
  release_date: string | null;
  image_url: string | null;
  saved_at: string;
};

export type WishlistExport = {
  v: 1;
  items: WishlistItem[];
};

const STORAGE_KEY = "animegood:wishlist";
const MAX_ITEMS = 200;

export function loadWishlist(): WishlistItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as WishlistItem[];
    return Array.isArray(parsed) ? parsed.filter(isValidWishlistItem).slice(0, MAX_ITEMS) : [];
  } catch {
    return [];
  }
}

export function saveWishlist(items: WishlistItem[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, MAX_ITEMS)));
}

export function toWishlistItem(product: {
  id: number;
  product_name: string;
  display_name_zh?: string | null;
  ip: string;
  shop: string;
  source_url: string;
  price: number | null;
  stock_status: string;
  release_date: string | null;
  image_url: string | null;
}): WishlistItem {
  return {
    id: product.id,
    product_name: product.product_name,
    display_name_zh: product.display_name_zh ?? null,
    ip: product.ip,
    shop: product.shop,
    source_url: product.source_url,
    price: product.price,
    stock_status: product.stock_status,
    release_date: product.release_date,
    image_url: product.image_url,
    saved_at: new Date().toISOString(),
  };
}

export function toggleWishlist(items: WishlistItem[], product: WishlistItem): WishlistItem[] {
  const exists = items.some((item) => item.id === product.id);
  if (exists) {
    return items.filter((item) => item.id !== product.id);
  }
  return [product, ...items].slice(0, MAX_ITEMS);
}

export function mergeWishlistItems(existing: WishlistItem[], incoming: WishlistItem[]): WishlistItem[] {
  const merged = new Map<number, WishlistItem>();
  for (const item of existing) {
    merged.set(item.id, { ...item });
  }
  for (const item of incoming) {
    if (!merged.has(item.id) && merged.size >= MAX_ITEMS) {
      continue;
    }
    const current = merged.get(item.id);
    merged.set(item.id, {
      ...item,
      saved_at: current?.saved_at ?? item.saved_at,
    });
  }
  return [...merged.values()].slice(0, MAX_ITEMS);
}

export function exportWishlistBase64(items: WishlistItem[]): string {
  const payload: WishlistExport = { v: 1, items };
  return btoa(unescape(encodeURIComponent(JSON.stringify(payload))));
}

export function parseWishlistImport(
  input: string,
): { ok: true; items: WishlistItem[] } | { ok: false; error: string } {
  const trimmed = input.trim();
  if (!trimmed) {
    return { ok: false, error: "导入内容为空。" };
  }

  let jsonText: string;
  try {
    jsonText = decodeURIComponent(escape(atob(trimmed)));
  } catch {
    jsonText = trimmed;
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(jsonText);
  } catch {
    return { ok: false, error: "JSON 格式无效。" };
  }

  if (!parsed || typeof parsed !== "object") {
    return { ok: false, error: "数据格式无效。" };
  }

  const record = parsed as { v?: unknown; items?: unknown };
  if (record.v !== 1) {
    return { ok: false, error: "版本字段 v 必须为 1。" };
  }
  if (!Array.isArray(record.items)) {
    return { ok: false, error: "items 必须是数组。" };
  }
  if (record.items.length > MAX_ITEMS) {
    return { ok: false, error: `商品数量不能超过 ${MAX_ITEMS} 条。` };
  }

  const items: WishlistItem[] = [];
  for (const entry of record.items) {
    if (!isValidWishlistItem(entry)) {
      return { ok: false, error: "收藏条目字段不完整或类型错误。" };
    }
    items.push(entry);
  }

  return { ok: true, items };
}

export function applyProductRefresh(
  items: WishlistItem[],
  products: Array<{
    id: number;
    product_name: string;
    display_name_zh?: string | null;
    ip: string;
    shop: string;
    source_url: string;
    price: number | null;
    stock_status: string;
    release_date: string | null;
    image_url: string | null;
  }>,
): WishlistItem[] {
  const byId = new Map(products.map((product) => [product.id, product]));
  return items.map((item) => {
    const fresh = byId.get(item.id);
    if (!fresh) {
      return item;
    }
    return {
      ...item,
      product_name: fresh.product_name,
      display_name_zh: fresh.display_name_zh ?? item.display_name_zh ?? null,
      ip: fresh.ip,
      shop: fresh.shop,
      source_url: fresh.source_url,
      price: fresh.price,
      stock_status: fresh.stock_status,
      release_date: fresh.release_date,
      image_url: fresh.image_url,
    };
  });
}

function isValidWishlistItem(value: unknown): value is WishlistItem {
  if (!value || typeof value !== "object") {
    return false;
  }
  const item = value as Record<string, unknown>;
  return (
    typeof item.id === "number" &&
    Number.isFinite(item.id) &&
    typeof item.product_name === "string" &&
    typeof item.ip === "string" &&
    typeof item.shop === "string" &&
    typeof item.source_url === "string" &&
    (item.price === null || (typeof item.price === "number" && Number.isFinite(item.price))) &&
    typeof item.stock_status === "string" &&
    (item.release_date === null || typeof item.release_date === "string") &&
    (item.image_url === null || typeof item.image_url === "string") &&
    typeof item.saved_at === "string"
  );
}
