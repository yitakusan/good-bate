// ============================================================
// SHARED MODULE
//
// [用途] 浏览器 fetch 封装；几乎所有页面经此调用后端
// [类型] 请求/响应模型来自 api-types.generated.ts（python scripts/gen-api-types.py）
// [文件] frontend/src/api.ts
// [后端] backend/app/main.py
// [代码索引] docs/CODE_INDEX.md#shared-modules
// ============================================================
import type {
  ActionLogOut,
  FinanceMonthBucket,
  FinanceOutboundBucket,
  FinanceSummaryOut,
  ItemCreate as GeneratedItemCreate,
  ItemOut,
  LineCreate as GeneratedLineCreate,
  LineOut,
  OrderCreate as GeneratedOrderCreate,
  OrderGroupOut,
  OrderOut,
  OrderRequestCreate as GeneratedOrderRequestCreate,
  OrderRequestOut,
  OrderRequestPublicOut,
  OutboundBatchOut,
  OutboundBoxOut,
  ScrapeProduct as GeneratedScrapeProduct,
  ScrapeResult as GeneratedScrapeResult,
  ShipmentItemOut,
  ShipmentOut,
  StatsOut,
  StockBoxChildOut,
  StockBoxLineOut,
  StockBoxOrderOut,
  StockBoxOut,
  UserOut,
} from "./api-types.generated";

export type ItemStatus = LineOut["status"];
export type OrderStatus = OrderOut["status"];
export type ShipmentStatus = ShipmentOut["status"];
export type ShipmentDirection = ShipmentOut["direction"];
export type Carrier = ShipmentOut["carrier"];
export type ExpectedShipPeriod = NonNullable<LineOut["expected_ship_period"]>;

export type Line = LineOut;
/** @deprecated alias for Line */
export type Item = ItemOut;
export type Order = OrderOut;
export type OrderGroupInBox = OrderGroupOut;
export type ShipmentItem = ShipmentItemOut;
export type Shipment = ShipmentOut;
export type OutboundBox = OutboundBoxOut;
export type PaymentStatus = OutboundBatchOut["payment_status"];
export type OutboundBatch = OutboundBatchOut;
export type { FinanceMonthBucket, FinanceOutboundBucket };
export type FinanceSummary = FinanceSummaryOut;
export type StockBoxLine = StockBoxLineOut;
export type StockBoxOrder = StockBoxOrderOut;
export type StockBoxChild = StockBoxChildOut;
export type StockBox = StockBoxOut;
export type Stats = StatsOut;
export type LineCreate = GeneratedLineCreate;
export type OrderCreate = GeneratedOrderCreate;
export type ItemCreate = GeneratedItemCreate;
export type ScrapeProduct = GeneratedScrapeProduct;
export type ScrapeResult = GeneratedScrapeResult;

export interface AppMeta {
  db_mode: "production" | "shadow";
  is_shadow: boolean;
  database: string;
  label: string;
  auth_required?: boolean;
  version?: string;
  user?: AuthUser | null;
  deposit_rate?: number;
}

export type UserRole = UserOut["role"];
export type AuthUser = UserOut;
export type OrderRequestStatus = OrderRequestOut["status"];
export type OrderRequestPublic = OrderRequestPublicOut;
export type OrderRequest = OrderRequestOut;
export type OrderRequestCreate = GeneratedOrderRequestCreate;

// ============================================================
// FEATURE: AUTH
// [API函数] getAdminToken / setAdminToken
// [用途] 遗留 X-Admin-Token（与 Cookie 会话并存）
// [代码索引] docs/CODE_INDEX.md#feature-auth
// ============================================================
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

export type ActionLog = ActionLogOut;

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
    credentials: "include",
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
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

// ============================================================
// FEATURE: TUNNEL
// [API函数] fetchTunnelStatus / startTunnel / stopTunnel
// [调用页面] frontend/src/App.tsx（页头）
// [后端接口] GET /api/tunnel  POST /api/tunnel/start  POST /api/tunnel/stop
// [代码索引] docs/CODE_INDEX.md#feature-tunnel
// ============================================================
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

// ============================================================
// FEATURE: SYSTEM
// [API函数] fetchMeta
// [后端接口] GET /api/meta
// [代码索引] docs/CODE_INDEX.md#feature-system
// ============================================================
export function fetchMeta() {
  return request<AppMeta>("/api/meta");
}

// ============================================================
// FEATURE: AUTH
// [API函数] login / logout / registerCustomer / fetchMe
// [调用页面] AuthPanel.tsx, App.tsx, ApplyPage.tsx, MePage.tsx
// [后端接口] POST /api/auth/login | logout | register  GET /api/auth/me
// [代码索引] docs/CODE_INDEX.md#feature-auth
// ============================================================
export function login(email: string, password: string) {
  return request<AuthUser>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function logout() {
  return request<{ ok: boolean }>("/api/auth/logout", { method: "POST" });
}

export function registerCustomer(
  email: string,
  password: string,
  display_name = "",
) {
  return request<AuthUser>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, display_name }),
  });
}

export function fetchMe() {
  return request<AuthUser | null>("/api/auth/me");
}

// ============================================================
// FEATURE: CUSTOMER_PORTAL
// [API函数] fetchMyOrderRequests / confirmDeposit
// [调用页面] MePage.tsx（ApplyPage 也调用 confirmDeposit）
// [后端接口] GET /api/me/order-requests
//            POST /api/me/order-requests/{code}/confirm-deposit
// [代码索引] docs/CODE_INDEX.md#feature-customer_portal
// ============================================================
export function fetchMyOrderRequests(status?: string) {
  const qs = new URLSearchParams();
  if (status) qs.set("status", status);
  const suffix = qs.toString() ? `?${qs}` : "";
  return request<OrderRequestPublic[]>(`/api/me/order-requests${suffix}`);
}

export function confirmDeposit(code: string, payment_ref = "") {
  return request<OrderRequestPublic>(
    `/api/me/order-requests/${encodeURIComponent(code)}/confirm-deposit`,
    {
      method: "POST",
      body: JSON.stringify({ payment_ref }),
    },
  );
}

// ============================================================
// FEATURE: ORDER_REQUEST
// [API函数] staffConfirmDeposit / createOrderRequest / fetchPublicOrderRequests /
//   fetchOrderRequestByCode / fetchOrderRequests / confirmOrderRequest / rejectOrderRequest
// [调用页面] App.tsx 申请单 Tab；ApplyPage.tsx（公开提交）
// [说明] fetchOrderRequestByCode 前端页面未调用（仅封装）
// [代码索引] docs/CODE_INDEX.md#feature-order_request
// ============================================================
export function staffConfirmDeposit(requestId: number, payment_ref = "") {
  return request<OrderRequest>(
    `/api/order-requests/${requestId}/confirm-deposit`,
    {
      method: "POST",
      body: JSON.stringify({ payment_ref }),
    },
  );
}

// ============================================================
// FEATURE: USER_MANAGEMENT
// [API函数] fetchUsers / createUser / setUserActive
// [调用页面] App.tsx Tab 用户
// [后端接口] GET|POST /api/users  PATCH /api/users/{id}/active
// [代码索引] docs/CODE_INDEX.md#feature-user_management
// ============================================================
export function fetchUsers() {
  return request<AuthUser[]>("/api/users");
}

export function createUser(payload: {
  email: string;
  password: string;
  role: UserRole;
  display_name?: string;
}) {
  return request<AuthUser>("/api/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function setUserActive(userId: number, is_active: boolean) {
  return request<AuthUser>(`/api/users/${userId}/active`, {
    method: "PATCH",
    body: JSON.stringify({ is_active }),
  });
}

// ============================================================
// FEATURE: SYSTEM
// [API函数] fetchProductKinds
// [后端接口] GET /api/product-kinds
// [代码索引] docs/CODE_INDEX.md#feature-system
// ============================================================
export function fetchProductKinds() {
  return request<{ labels: string[]; aliases: Record<string, string[]> }>(
    "/api/product-kinds",
  );
}

export function fetchStats() {
  return request<Stats>("/api/stats");
}

export function fetchShops() {
  return request<string[]>("/api/shops");
}

// ============================================================
// FEATURE: ORDER
// [API函数] fetchOrders / createOrder / updateOrder / fetchItems / createItem / updateItem / fetchStats
// [调用页面] App.tsx Tab 订单
// [说明] createItem 前端页面未调用（仅封装）
// [后端接口] /api/orders*  /api/items*  GET /api/stats
// [代码索引] docs/CODE_INDEX.md#feature-order
// ============================================================
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

// ============================================================
// FEATURE: INBOUND
// [API函数] createOrderInbound / fetchShipments / confirmShipment
// [调用页面] App.tsx Tab 进库
// [后端接口] POST /api/orders/{id}/inbound  GET /api/shipments  POST /api/shipments/{id}/confirm
// [代码索引] docs/CODE_INDEX.md#feature-inbound
// ============================================================
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

// ============================================================
// FEATURE: ORDER_IMPORT
// [API函数] createItemsBatch / scrapeUrl
// [调用页面] App.tsx Tab 抓取
// [后端接口] POST /api/items/batch  POST /api/scrape
// [代码索引] docs/CODE_INDEX.md#feature-order_import
// ============================================================
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

// FEATURE: ORDER_REQUEST — 公开抓取（顾客申请页）
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
    exchange_rate?: number | null;
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

// ============================================================
// FEATURE: INVENTORY
// [API函数] fetchStockBoxes / createStockBox / combineStockBox / addStockBoxOrders /
//   updateStockBox / removeStockBoxOrders / deleteStockBox / mergeStockBoxChild / detachStockBoxChild
// [调用页面] App.tsx Tab 库存
// [后端接口] /api/stock-boxes*
// [代码索引] docs/CODE_INDEX.md#feature-inventory
// ============================================================
export function fetchStockBoxes() {
  return request<StockBox[]>("/api/stock-boxes");
}

export function createStockBox(payload: {
  order_ids: number[];
  note?: string;
  box_no?: number;
}) {
  return request<StockBox>("/api/stock-boxes", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function combineStockBox(payload: {
  order_ids: number[];
  note?: string;
}) {
  return request<StockBox>("/api/stock-boxes/combine", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function addStockBoxOrders(boxId: number, orderIds: number[]) {
  return request<StockBox>(`/api/stock-boxes/${boxId}/orders`, {
    method: "POST",
    body: JSON.stringify({ order_ids: orderIds }),
  });
}

export function updateStockBox(
  boxId: number,
  payload: { note?: string; box_no?: number },
) {
  return request<StockBox>(`/api/stock-boxes/${boxId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function removeStockBoxOrders(boxId: number, orderIds: number[]) {
  return request<StockBox | null>(`/api/stock-boxes/${boxId}/remove-orders`, {
    method: "POST",
    body: JSON.stringify({ order_ids: orderIds }),
  });
}

export function deleteStockBox(boxId: number) {
  return request<{ ok: boolean }>(`/api/stock-boxes/${boxId}`, {
    method: "DELETE",
  });
}

export function mergeStockBoxChild(parentId: number, childBoxId: number) {
  return request<StockBox>(`/api/stock-boxes/${parentId}/merge-child`, {
    method: "POST",
    body: JSON.stringify({ child_box_id: childBoxId }),
  });
}

export function detachStockBoxChild(childId: number) {
  return request<StockBox>(`/api/stock-boxes/${childId}/detach-parent`, {
    method: "POST",
  });
}

// ============================================================
// FEATURE: OUTBOUND_BATCH
// [API函数] fetchOutboundBatches / createOutboundBatch / updateOutboundBatch / confirmOutboundBatch
// [调用页面] App.tsx Tab 出库
// [后端接口] GET|POST /api/outbound-batches  PUT .../{id}  POST .../{id}/confirm
// [代码索引] docs/CODE_INDEX.md#feature-outbound_batch
// ============================================================
export function fetchOutboundBatches(limit = 50) {
  return request<OutboundBatch[]>(`/api/outbound-batches?limit=${limit}`);
}

export function createOutboundBatch(payload: {
  note?: string;
  boxes: {
    box_no?: number;
    carrier: Carrier;
    tracking_no: string;
    note?: string;
    item_ids: number[];
    net_weight?: number | null;
    gross_weight?: number | null;
    length_cm?: number | null;
    width_cm?: number | null;
    height_cm?: number | null;
  }[];
  allow_missing_barcode?: boolean;
  missing_barcode_note?: string;
  freight_exchange_rate?: number | null;
  freight_unit_price_jpy?: number | null;
  chargeable_weight?: number | null;
  invoice_ship_date?: string | null;
}) {
  return request<OutboundBatch>("/api/outbound-batches", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateOutboundBatch(
  id: number,
  payload: {
    note?: string | null;
    boxes: {
      box_no: number;
      carrier: Carrier;
      tracking_no: string;
      note?: string;
      items: { item_id: number; qty?: number }[];
      net_weight?: number | null;
      gross_weight?: number | null;
      length_cm?: number | null;
      width_cm?: number | null;
      height_cm?: number | null;
    }[];
    allow_missing_barcode?: boolean;
    missing_barcode_note?: string;
    invoice_ship_date?: string | null;
  },
) {
  return request<OutboundBatch>(`/api/outbound-batches/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function confirmOutboundBatch(id: number) {
  return request<OutboundBatch>(`/api/outbound-batches/${id}/confirm`, {
    method: "POST",
  });
}

// ============================================================
// FEATURE: FINANCE
// [API函数] updateOutboundBatchFinance
// [调用页面] App.tsx Tab 出库（运费/收款表单）
// [后端接口] PATCH /api/outbound-batches/{id}/finance
// [代码索引] docs/CODE_INDEX.md#feature-finance
// ============================================================
export function updateOutboundBatchFinance(
  id: number,
  payload: {
    freight_exchange_rate?: number | null;
    freight_unit_price_jpy?: number | null;
    chargeable_weight?: number | null;
    amount_received_cny?: number | null;
    payment_note?: string;
    invoice_ship_date?: string | null;
  },
) {
  return request<OutboundBatch>(`/api/outbound-batches/${id}/finance`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

// ============================================================
// FEATURE: FEE_DETAIL
// [API函数] downloadOutboundFeeDetail
// [调用页面] App.tsx 出库 Tab 按钮「费用明细 Excel」
// [后端接口] GET /api/outbound-batches/{id}/fee-detail.xlsx
// [代码索引] docs/CODE_INDEX.md#feature-fee_detail
// ============================================================
export function downloadOutboundFeeDetail(id: number) {
  const headers: Record<string, string> = {};
  const adminToken = getAdminToken();
  if (adminToken) headers["X-Admin-Token"] = adminToken;
  return fetch(`/api/outbound-batches/${id}/fee-detail.xlsx`, {
    headers,
    credentials: "include",
  }).then(async (res) => {
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || res.statusText);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `fee-detail-batch-${id}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  });
}

function detailFromErrorBody(text: string, fallback: string): string {
  const raw = (text || "").trim();
  if (!raw) return fallback;
  try {
    const body = JSON.parse(raw) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail.trim()) {
      return body.detail;
    }
    if (Array.isArray(body.detail)) {
      const parts = body.detail
        .map((item) => {
          if (typeof item === "string") return item;
          if (item && typeof item === "object" && "msg" in item) {
            return String((item as { msg: unknown }).msg);
          }
          return "";
        })
        .filter(Boolean);
      if (parts.length) return parts.join("；");
    }
    if (body.detail != null) return String(body.detail);
  } catch {
    /* not JSON */
  }
  return raw;
}

function filenameFromContentDisposition(
  header: string | null,
  fallback: string,
): string {
  if (!header) return fallback;
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (utf8?.[1]) {
    try {
      return decodeURIComponent(utf8[1].trim());
    } catch {
      /* ignore */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  if (plain?.[1]) return plain[1].trim();
  return fallback;
}

async function downloadXlsxBlob(
  path: string,
  filename: string,
  init?: RequestInit,
) {
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string> | undefined),
  };
  const adminToken = getAdminToken();
  if (adminToken) headers["X-Admin-Token"] = adminToken;
  const res = await fetch(path, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(detailFromErrorBody(text, res.statusText));
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filenameFromContentDisposition(
    res.headers.get("Content-Disposition"),
    filename,
  );
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ============================================================
// FEATURE: INV_EXPORT
// [API函数] downloadOutboundInv / downloadOutboundInvPreview
// [调用页面] App.tsx 出库 Tab 按钮「导出 INV」
// [后端接口] GET .../inv.xlsx  POST .../preview-inv.xlsx
// [代码索引] docs/CODE_INDEX.md#feature-inv_export
// ============================================================
export function downloadOutboundInv(id: number) {
  return downloadXlsxBlob(
    `/api/outbound-batches/${id}/inv.xlsx`,
    `INV-batch-${id}.xlsx`,
  );
}

export function downloadOutboundInvPreview(payload: {
  note?: string;
  boxes: {
    box_no?: number;
    carrier: Carrier;
    tracking_no: string;
    note?: string;
    item_ids: number[];
    net_weight?: number | null;
    gross_weight?: number | null;
    length_cm?: number | null;
    width_cm?: number | null;
    height_cm?: number | null;
  }[];
  freight_exchange_rate?: number | null;
  freight_unit_price_jpy?: number | null;
  chargeable_weight?: number | null;
  invoice_ship_date?: string | null;
}) {
  return downloadXlsxBlob(
    "/api/outbound-batches/preview-inv.xlsx",
    "INV-draft-preview.xlsx",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

// ============================================================
// FEATURE: FINANCE
// [API函数] fetchFinanceSummary
// [调用页面] App.tsx Tab 财务
// [后端接口] GET /api/finance/summary
// [代码索引] docs/CODE_INDEX.md#feature-finance
// ============================================================
export function fetchFinanceSummary(month?: string) {
  const q = month ? `?month=${encodeURIComponent(month)}` : "";
  return request<FinanceSummary>(`/api/finance/summary${q}`);
}

export interface ApplyReport {
  period: "day" | "month";
  label: string;
  start: string;
  end: string;
  order_count: number;
  by_status: Record<string, number>;
  goods_jpy: number;
  deposit_jpy: number;
  top_links: {
    source_url: string;
    name: string;
    count: number;
    goods_jpy: number;
  }[];
  top_users: {
    user_id: number | null;
    email: string;
    display_name: string;
    count: number;
    goods_jpy: number;
  }[];
  top_ips: { ip: string; count: number; goods_jpy: number }[];
}

// ============================================================
// FEATURE: APPLY_STATS
// [API函数] fetchApplyReport
// [调用页面] App.tsx Tab 统计
// [后端接口] GET /api/reports/apply
// [代码索引] docs/CODE_INDEX.md#feature-apply_stats
// ============================================================
export function fetchApplyReport(params: {
  period?: "day" | "month";
  day?: string;
  month?: string;
  limit?: number;
} = {}) {
  const qs = new URLSearchParams();
  if (params.period) qs.set("period", params.period);
  if (params.day) qs.set("day", params.day);
  if (params.month) qs.set("month", params.month);
  if (params.limit) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs}` : "";
  return request<ApplyReport>(`/api/reports/apply${suffix}`);
}

// ============================================================
// FEATURE: ACTION_LOG
// [API函数] fetchActionLogs / fetchLatestActionLog / undoActionLog
// [调用页面] App.tsx 页头撤回条 + Tab 日志
// [后端接口] GET /api/action-logs  GET /api/action-logs/latest  POST /api/action-logs/{id}/undo
// [代码索引] docs/CODE_INDEX.md#feature-action_log
// ============================================================
export function fetchActionLogs(limit = 50) {
  return request<ActionLog[]>(`/api/action-logs?limit=${limit}`);
}

export async function fetchLatestActionLog() {
  return request<ActionLog | null>("/api/action-logs/latest");
}

export function undoActionLog(id: number) {
  return request<ActionLog>(`/api/action-logs/${id}/undo`, { method: "POST" });
}
