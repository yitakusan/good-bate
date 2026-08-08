export type CartItem = {
  id: number;
  product_name: string;
  display_name_zh?: string | null;
  shop: string;
  source_url: string;
  price: number | null;
  image_url: string | null;
  quantity: number;
  added_at: string;
};

export type CartExport = {
  v: 1;
  items: CartItem[];
};

const STORAGE_KEY = "animegood_cart_v1";
const MIN_QTY = 1;
const MAX_QTY = 99;
const MAX_ITEMS = 200;

function clampQuantity(quantity: number): number {
  return Math.min(MAX_QTY, Math.max(MIN_QTY, Math.floor(quantity)));
}

export function loadCart(): CartItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as CartItem[];
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .filter(isValidCartItem)
      .map((item) => ({ ...item, quantity: clampQuantity(item.quantity) }))
      .slice(0, MAX_ITEMS);
  } catch {
    return [];
  }
}

export function saveCart(items: CartItem[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, MAX_ITEMS)));
}

export function toCartItem(product: {
  id: number;
  product_name: string;
  display_name_zh?: string | null;
  shop: string;
  source_url: string;
  price: number | null;
  image_url: string | null;
}): CartItem {
  return {
    id: product.id,
    product_name: product.product_name,
    display_name_zh: product.display_name_zh ?? null,
    shop: product.shop,
    source_url: product.source_url,
    price: product.price,
    image_url: product.image_url,
    quantity: 1,
    added_at: new Date().toISOString(),
  };
}

export function addItem(
  items: CartItem[],
  product: Parameters<typeof toCartItem>[0],
): CartItem[] {
  const existing = items.find((item) => item.id === product.id);
  if (existing) {
    return items.map((item) =>
      item.id === product.id
        ? {
            ...item,
            quantity: clampQuantity(item.quantity + 1),
            display_name_zh: product.display_name_zh ?? item.display_name_zh ?? null,
          }
        : item,
    );
  }
  if (items.length >= MAX_ITEMS) {
    return items;
  }
  return [toCartItem(product), ...items];
}

export function updateQuantity(items: CartItem[], id: number, quantity: number): CartItem[] {
  if (quantity < MIN_QTY) {
    return removeItem(items, id);
  }
  return items.map((item) =>
    item.id === id ? { ...item, quantity: clampQuantity(quantity) } : item,
  );
}

export function removeItem(items: CartItem[], id: number): CartItem[] {
  return items.filter((item) => item.id !== id);
}

export function clearCart(): CartItem[] {
  return [];
}

export function getCartCount(items: CartItem[]): number {
  return items.reduce((sum, item) => sum + item.quantity, 0);
}

export function mergeCartItems(existing: CartItem[], incoming: CartItem[]): CartItem[] {
  const merged = new Map<number, CartItem>();
  for (const item of existing) {
    merged.set(item.id, { ...item });
  }
  for (const item of incoming) {
    const current = merged.get(item.id);
    if (current) {
      merged.set(item.id, {
        ...current,
        quantity: clampQuantity(current.quantity + item.quantity),
      });
    } else if (merged.size < MAX_ITEMS) {
      merged.set(item.id, { ...item, quantity: clampQuantity(item.quantity) });
    }
  }
  return [...merged.values()].slice(0, MAX_ITEMS);
}

export function exportCartBase64(items: CartItem[]): string {
  const payload: CartExport = { v: 1, items };
  return btoa(unescape(encodeURIComponent(JSON.stringify(payload))));
}

export function parseCartImport(
  input: string,
): { ok: true; items: CartItem[] } | { ok: false; error: string } {
  const trimmed = input.trim();
  if (!trimmed) {
    return { ok: false, error: "导入内容为空。" };
  }

  let jsonText: string;
  try {
    jsonText = decodeURIComponent(escape(atob(trimmed)));
  } catch {
    try {
      jsonText = trimmed;
    } catch {
      return { ok: false, error: "无法解析 Base64 或 JSON。" };
    }
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

  const items: CartItem[] = [];
  for (const entry of record.items) {
    if (!isValidCartItem(entry)) {
      return { ok: false, error: "购物车条目字段不完整或类型错误。" };
    }
    items.push({ ...entry, quantity: clampQuantity(entry.quantity) });
  }

  return { ok: true, items };
}

function isValidCartItem(value: unknown): value is CartItem {
  if (!value || typeof value !== "object") {
    return false;
  }
  const item = value as Record<string, unknown>;
  return (
    typeof item.id === "number" &&
    Number.isFinite(item.id) &&
    typeof item.product_name === "string" &&
    typeof item.shop === "string" &&
    typeof item.source_url === "string" &&
    (item.price === null || (typeof item.price === "number" && Number.isFinite(item.price))) &&
    (item.image_url === null || typeof item.image_url === "string") &&
    typeof item.quantity === "number" &&
    Number.isFinite(item.quantity) &&
    typeof item.added_at === "string"
  );
}
