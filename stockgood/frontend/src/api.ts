export type ItemStatus =
  | "ordered"
  | "inbound_shipped"
  | "in_stock"
  | "outbound_shipped"
  | "delivered"
  | "cancelled";
export type OrderStatus = ItemStatus;
export type ShipmentStatus = "shipped" | "delivered";
export type ShipmentDirection = "inbound" | "outbound";
export type Carrier = "yamato" | "sagawa" | "other";
export type ExpectedShipPeriod = "early" | "mid" | "late";

export interface Line {
  id: number;
  order_id: number;
  name: string;
  shop: string;
  order_ref: string;
  qty: number;
  unit_cost: number | null;
  status: ItemStatus;
  ordered_at: string;
  arrived_at: string | null;
  expected_ship_at: string | null;
  expected_ship_period: ExpectedShipPeriod | null;
  barcode: string;
  note: string;
  animegood_product_id: number | null;
  ip: string;
  image_url: string;
  source_url: string;
  inbound_tracking_no: string | null;
  inbound_carrier: Carrier | null;
  inbound_tracking_url: string | null;
  inbound_shipment_id: number | null;
  outbound_tracking_no: string | null;
  outbound_carrier: Carrier | null;
  outbound_tracking_url: string | null;
  outbound_shipment_id: number | null;
  outbound_box_no: number | null;
}

/** @deprecated alias for Line */
export type Item = Line & {
  order_qty?: number | null;
  order_image_url?: string;
};

export interface Order {
  id: number;
  order_ref: string;
  shop: string;
  status: OrderStatus;
  ordered_at: string;
  order_qty: number | null;
  shipping_fee: number | null;
  order_image_url: string;
  note: string;
  expected_ship_at: string | null;
  expected_ship_period: ExpectedShipPeriod | null;
  line_count: number;
  total_qty: number;
  goods_total: number | null;
  order_total: number | null;
  lines: Line[];
}

export interface OrderGroupInBox {
  order_id: number | null;
  order_ref: string;
  items: ShipmentItem[];
}

export interface ShipmentItem {
  id: number;
  order_id?: number | null;
  order_ref?: string;
  name: string;
  shop: string;
  qty: number;
  status: ItemStatus;
  barcode: string;
}

export interface Shipment {
  id: number;
  direction: ShipmentDirection;
  carrier: Carrier;
  tracking_no: string;
  tracking_url: string | null;
  shipped_at: string;
  delivered_at: string | null;
  status: ShipmentStatus;
  order_id?: number | null;
  batch_id?: number | null;
  box_no?: number | null;
  items: ShipmentItem[];
  order_groups?: OrderGroupInBox[];
}

export interface OutboundBox {
  id: number;
  batch_id: number;
  box_no: number;
  carrier: Carrier;
  tracking_no: string;
  tracking_url: string | null;
  status: ShipmentStatus;
  shipped_at: string;
  delivered_at: string | null;
  items: ShipmentItem[];
  order_groups: OrderGroupInBox[];
}

export interface OutboundBatch {
  id: number;
  note: string;
  created_at: string;
  boxes: OutboundBox[];
  box_count: number;
  item_count: number;
}

export interface Stats {
  ordered: number;
  inbound_shipped: number;
  in_stock: number;
  outbound_shipped: number;
  delivered: number;
  cancelled: number;
  inbound_shipments_shipped: number;
  outbound_shipments_shipped: number;
  shipments_delivered: number;
  orders_total: number;
}

export interface LineCreate {
  name: string;
  shop?: string;
  qty?: number;
  unit_cost?: number | null;
  note?: string;
  animegood_product_id?: number | null;
  ip?: string;
  image_url?: string;
  source_url?: string;
  expected_ship_at?: string | null;
  expected_ship_period?: ExpectedShipPeriod | null;
  barcode?: string;
}

export interface OrderCreate {
  order_ref?: string;
  shop?: string;
  order_qty?: number | null;
  shipping_fee?: number | null;
  order_image_url?: string;
  note?: string;
  expected_ship_at?: string | null;
  expected_ship_period?: ExpectedShipPeriod | null;
  lines: LineCreate[];
}

export interface ItemCreate extends LineCreate {
  order_ref?: string;
  order_qty?: number | null;
  order_image_url?: string;
}

export interface ScrapeProduct {
  name: string;
  shop: string;
  unit_cost: number | null;
  image_url: string;
  source_url: string;
  ip: string;
  barcode?: string;
  qty?: number | null;
  expected_ship_at?: string | null;
  expected_ship_period?: ExpectedShipPeriod | null;
  release_date?: string | null;
}

export interface ScrapeResult {
  kind: "list";
  products: ScrapeProduct[];
  message: string;
  order_ref?: string;
  shipping_fee?: number | null;
  order_total?: number | null;
}

export interface AppMeta {
  db_mode: "production" | "shadow";
  is_shadow: boolean;
  database: string;
  label: string;
  auth_required?: boolean;
}

export type OrderRequestStatus = "submitted" | "ordered" | "rejected";

export interface OrderRequestPublic {
  request_code: string;
  status: OrderRequestStatus;
  status_label: string;
  name: string;
  shop: string;
  unit_cost: number | null;
  amount?: number | null;
  image_url: string;
  source_url: string;
  qty: number;
  shop_order_ref: string;
  ordered_at: string | null;
  staff_note: string;
  reject_reason: string;
  created_at: string;
  updated_at: string;
}

export interface OrderRequest {
  id: number;
  request_code: string;
  status: OrderRequestStatus;
  name: string;
  shop: string;
  unit_cost: number | null;
  image_url: string;
  source_url: string;
  ip: string;
  barcode: string;
  qty: number;
  contact: string;
  note: string;
  shop_order_ref: string;
  ordered_at: string | null;
  staff_note: string;
  reject_reason: string;
  stock_order_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface OrderRequestCreate {
  name: string;
  shop?: string;
  unit_cost?: number | null;
  image_url?: string;
  source_url: string;
  ip?: string;
  barcode?: string;
  qty?: number;
  contact?: string;
  note?: string;
}

const ADMIN_TOKEN_KEY = "stockgood_admin_token";

export function getAdminToken(): string {
  try {
    return localStorage.getItem(ADMIN_TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setAdminToken(token: string) {
  try {
    if (token) localStorage.setItem(ADMIN_TOKEN_KEY, token);
    else localStorage.removeItem(ADMIN_TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

export interface TunnelStatus {
  running: boolean;
  url: string;
  stale: boolean;
}

export interface ActionLog {
  id: number;
  action_type: string;
  summary: string;
  created_at: string;
  undone_at: string | null;
  undoable: boolean;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const adminToken = getAdminToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (adminToken) headers["X-Admin-Token"] = adminToken;
  const res = await fetch(path, {
    ...init,
    headers,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ? JSON.stringify(body.detail) : detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function fetchTunnelStatus() {
  return request<TunnelStatus>("/api/tunnel");
}

export function startTunnel() {
  return request<TunnelStatus & { ok?: boolean; message?: string }>(
    "/api/tunnel/start",
    { method: "POST" },
  );
}

export function stopTunnel() {
  return request<TunnelStatus & { ok?: boolean; message?: string }>(
    "/api/tunnel/stop",
    { method: "POST" },
  );
}

export function fetchMeta() {
  return request<AppMeta>("/api/meta");
}

export function fetchStats() {
  return request<Stats>("/api/stats");
}

export function fetchShops() {
  return request<string[]>("/api/shops");
}

export function fetchOrders(params: {
  status?: string;
  shop?: string;
  q?: string;
  expected_ship_month?: string;
} = {}) {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.shop) qs.set("shop", params.shop);
  if (params.q) qs.set("q", params.q);
  if (params.expected_ship_month) {
    qs.set("expected_ship_month", params.expected_ship_month);
  }
  const suffix = qs.toString() ? `?${qs}` : "";
  return request<Order[]>(`/api/orders${suffix}`);
}

export function createOrder(payload: OrderCreate) {
  return request<Order>("/api/orders", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateOrder(
  id: number,
  payload: Partial<OrderCreate> & { status?: OrderStatus },
) {
  return request<Order>(`/api/orders/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function createOrderInbound(
  orderId: number,
  payload: { tracking_no: string; carrier: Carrier; item_ids: number[] },
) {
  return request<Shipment>(`/api/orders/${orderId}/inbound`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchItems(params: {
  status?: string;
  shop?: string;
  q?: string;
  expected_ship_month?: string;
} = {}) {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.shop) qs.set("shop", params.shop);
  if (params.q) qs.set("q", params.q);
  if (params.expected_ship_month) {
    qs.set("expected_ship_month", params.expected_ship_month);
  }
  const suffix = qs.toString() ? `?${qs}` : "";
  return request<Item[]>(`/api/items${suffix}`);
}

export function createItem(payload: ItemCreate) {
  return request<Item>("/api/items", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createItemsBatch(items: ItemCreate[]) {
  return request<Item[]>("/api/items/batch", {
    method: "POST",
    body: JSON.stringify({ items }),
  });
}

export function scrapeUrl(url: string, html?: string) {
  return request<ScrapeResult>("/api/scrape", {
    method: "POST",
    body: JSON.stringify(html ? { url, html } : { url }),
  });
}

export function publicScrapeUrl(url: string) {
  return request<ScrapeResult>("/api/public/scrape", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export function createOrderRequest(payload: OrderRequestCreate) {
  return request<OrderRequestPublic>("/api/public/order-requests", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchPublicOrderRequests(status?: string) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return request<OrderRequestPublic[]>(`/api/public/order-requests${qs}`);
}

export function fetchOrderRequestByCode(code: string) {
  return request<OrderRequestPublic>(
    `/api/public/order-requests/${encodeURIComponent(code.trim())}`,
  );
}

export function fetchOrderRequests(status?: string) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return request<OrderRequest[]>(`/api/order-requests${qs}`);
}

export function confirmOrderRequest(
  id: number,
  payload: {
    shop_order_ref: string;
    staff_note?: string;
    create_stock_order?: boolean;
    shipping_fee?: number | null;
  },
) {
  return request<OrderRequest>(`/api/order-requests/${id}/confirm-ordered`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function rejectOrderRequest(id: number, reject_reason: string) {
  return request<OrderRequest>(`/api/order-requests/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ reject_reason }),
  });
}

export function updateItem(
  id: number,
  payload: Partial<ItemCreate> & { status?: ItemStatus },
) {
  return request<Item>(`/api/items/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function fetchShipments(params: {
  status?: string;
  tracking_no?: string;
  direction?: ShipmentDirection;
} = {}) {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.tracking_no) qs.set("tracking_no", params.tracking_no);
  if (params.direction) qs.set("direction", params.direction);
  const suffix = qs.toString() ? `?${qs}` : "";
  return request<Shipment[]>(`/api/shipments${suffix}`);
}

export function confirmShipment(id: number) {
  return request<Shipment>(`/api/shipments/${id}/confirm`, { method: "POST" });
}

export function fetchOutboundBatches(limit = 50) {
  return request<OutboundBatch[]>(`/api/outbound-batches?limit=${limit}`);
}

export function createOutboundBatch(payload: {
  note?: string;
  boxes: {
    box_no?: number;
    carrier: Carrier;
    tracking_no: string;
    item_ids: number[];
  }[];
}) {
  return request<OutboundBatch>("/api/outbound-batches", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function confirmOutboundBatch(id: number) {
  return request<OutboundBatch>(`/api/outbound-batches/${id}/confirm`, {
    method: "POST",
  });
}

export function fetchActionLogs(limit = 50) {
  return request<ActionLog[]>(`/api/action-logs?limit=${limit}`);
}

export async function fetchLatestActionLog() {
  const res = await fetch("/api/action-logs/latest");
  if (!res.ok) {
    throw new Error(res.statusText);
  }
  return (await res.json()) as ActionLog | null;
}

export function undoActionLog(id: number) {
  return request<ActionLog>(`/api/action-logs/${id}/undo`, { method: "POST" });
}
