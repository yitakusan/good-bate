import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  ActionLog,
  AppMeta,
  Carrier,
  ExpectedShipPeriod,
  FinanceSummary,
  ItemStatus,
  Line,
  Order,
  OrderRequest,
  OrderRequestStatus,
  OutboundBatch,
  ScrapeProduct,
  Shipment,
  Stats,
  StockBox,
  TunnelStatus,
  combineStockBox,
  confirmOrderRequest,
  confirmOutboundBatch,
  confirmShipment,
  createOrder,
  createOrderInbound,
  createOutboundBatch,
  deleteStockBox,
  detachStockBoxChild,
  downloadOutboundFeeDetail,
  fetchActionLogs,
  fetchFinanceSummary,
  fetchItems,
  fetchLatestActionLog,
  fetchMeta,
  fetchOrderRequests,
  fetchOrders,
  fetchOutboundBatches,
  fetchProductKinds,
  fetchShipments,
  fetchShops,
  fetchStats,
  fetchStockBoxes,
  fetchTunnelStatus,
  startTunnel,
  stopTunnel,
  getAdminToken,
  mergeStockBoxChild,
  rejectOrderRequest,
  removeStockBoxOrders,
  scrapeUrl,
  setAdminToken,
  undoActionLog,
  updateItem,
  updateOrder,
  updateOutboundBatchFinance,
  updateStockBox,
} from "./api";
import { batchScrapeDelayMs, waitForBatchScrape } from "./scrapeDelay";

type Tab =
  | "orders"
  | "finance"
  | "requests"
  | "scrape"
  | "inbound"
  | "inventory"
  | "outbound"
  | "logs";
const REQUEST_STATUS_LABEL: Record<OrderRequestStatus, string> = {
  submitted: "已提交",
  ordered: "已下单",
  rejected: "已拒绝",
};
type DraftBox = {
  uid: string;
  box_no: number;
  carrier: Carrier;
  tracking_no: string;
  item_ids: number[];
};

function newDraftBoxUid() {
  return `draft-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}
const STATUS_LABEL: Record<ItemStatus, string> = {
  ordered: "已下单",
  inbound_shipped: "已发往仓库",
  in_stock: "在库",
  outbound_shipped: "已发往用户",
  delivered: "已签收",
  cancelled: "已取消",
};
const CARRIER_LABEL: Record<Carrier, string> = {
  yamato: "Yamato",
  sagawa: "佐川急便",
  other: "其他",
};
const PERIOD_LABEL: Record<ExpectedShipPeriod, string> = {
  early: "上旬",
  mid: "中旬",
  late: "下旬",
};
type DraftLine = {
  name: string;
  qty: string;
  unit_cost: string;
  ip: string;
  image_url: string;
  source_url: string;
};

const EMPTY_LINE = (): DraftLine => ({
  name: "",
  qty: "1",
  unit_cost: "",
  ip: "",
  image_url: "",
  source_url: "",
});

const EMPTY_FORM = {
  order_ref: "",
  shop: "",
  order_qty: "",
  shipping_fee: "0",
  exchange_rate: "",
  order_image_url: "",
  note: "",
  expected_ship_at: "",
  expected_ship_period: "" as "" | ExpectedShipPeriod,
  lines: [EMPTY_LINE()] as DraftLine[],
};

const PAYMENT_LABEL: Record<string, string> = {
  unpaid: "未收款",
  partial: "部分收款",
  paid: "已收款",
};

function parsePositiveRate(raw: string): number | null {
  const text = raw.trim();
  if (!text) return null;
  const n = Number(text);
  if (Number.isNaN(n) || n <= 0) return null;
  return n;
}

function moneyText(value: number | null | undefined, empty = "—") {
  if (value == null || Number.isNaN(Number(value))) return empty;
  return String(value);
}

function currentYearMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function formatDate(value: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function formatExpectedShip(
  value: string | null,
  period?: ExpectedShipPeriod | null,
) {
  if (!value) return "—";
  const match = value.match(/^(\d{4})-(\d{2})/);
  const month = match ? `${match[1]}年${Number(match[2])}月` : value;
  return period ? `${month}${PERIOD_LABEL[period]}` : `${month}発送予定`;
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

/** Public apply page URL to share via tunnel (falls back to local /apply). */
function applyShareUrl(tunnelUrl?: string | null) {
  const base = (tunnelUrl || "").replace(/\/+$/, "");
  if (base) return `${base}/apply`;
  if (typeof window !== "undefined") {
    return `${window.location.origin}/apply`;
  }
  return "/apply";
}

function groupLines(lines: Line[]) {
  const groups = new Map<number, { orderRef: string; lines: Line[] }>();
  for (const line of lines) {
    const current = groups.get(line.order_id);
    if (current) current.lines.push(line);
    else {
      groups.set(line.order_id, {
        orderRef: line.order_ref || `订单 #${line.order_id}`,
        lines: [line],
      });
    }
  }
  return [...groups.entries()];
}

export default function App() {
  const [tab, setTab] = useState<Tab>("orders");
  const [meta, setMeta] = useState<AppMeta | null>(null);
  const [tunnel, setTunnel] = useState<TunnelStatus | null>(null);
  const [tunnelCopied, setTunnelCopied] = useState(false);
  const [tunnelBusy, setTunnelBusy] = useState(false);
  const [stats, setStats] = useState<Stats | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [shops, setShops] = useState<string[]>([]);
  const [productKinds, setProductKinds] = useState<string[]>([]);
  const [shipments, setShipments] = useState<Shipment[]>([]);
  const [stockLines, setStockLines] = useState<Line[]>([]);
  const [batches, setBatches] = useState<OutboundBatch[]>([]);
  const [logs, setLogs] = useState<ActionLog[]>([]);
  const [latestLog, setLatestLog] = useState<ActionLog | null>(null);
  const [orderRequests, setOrderRequests] = useState<OrderRequest[]>([]);
  const [requestStatusFilter, setRequestStatusFilter] = useState("");
  const [confirmDraft, setConfirmDraft] = useState<
    Record<
      number,
      {
        shop_order_ref: string;
        staff_note: string;
        create_stock: boolean;
        exchange_rate: string;
      }
    >
  >({});
  const [rejectDraft, setRejectDraft] = useState<Record<number, string>>({});
  const [adminTokenInput, setAdminTokenInput] = useState(() => getAdminToken());
  const [loading, setLoading] = useState(false);
  const [undoBusy, setUndoBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const [statusFilter, setStatusFilter] = useState("");
  const [shopFilter, setShopFilter] = useState("");
  const [shipMonthFilter, setShipMonthFilter] = useState("");
  const [q, setQ] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [selectedOrderIds, setSelectedOrderIds] = useState<number[]>([]);
  const [expandedOrderIds, setExpandedOrderIds] = useState<number[]>([]);

  const [scrapeUrlValue, setScrapeUrlValue] = useState("");
  const [scrapeOrderRef, setScrapeOrderRef] = useState("");
  const [scrapeOrderQty, setScrapeOrderQty] = useState("");
  const [scrapeShippingFee, setScrapeShippingFee] = useState("0");
  const [scrapeExchangeRate, setScrapeExchangeRate] = useState("");
  const [financeMonth, setFinanceMonth] = useState(currentYearMonth);
  const [financeSummary, setFinanceSummary] = useState<FinanceSummary | null>(
    null,
  );
  const [scrapeBusy, setScrapeBusy] = useState(false);
  const [collection, setCollection] = useState<ScrapeProduct[]>([]);
  const [collectionPick, setCollectionPick] = useState<number[]>([]);
  const [collectionQty, setCollectionQty] = useState<Record<number, string>>({});
  const [collectionBarcode, setCollectionBarcode] = useState<
    Record<number, string>
  >({});
  const [collectionPrice, setCollectionPrice] = useState<Record<number, string>>(
    {},
  );
  const [batchExpectedShip, setBatchExpectedShip] = useState("");
  const [batchExpectedPeriod, setBatchExpectedPeriod] = useState<
    "" | ExpectedShipPeriod
  >("");

  const [selectedInboundIds, setSelectedInboundIds] = useState<number[]>([]);
  const [expandedInboundOrderIds, setExpandedInboundOrderIds] = useState<
    number[]
  >([]);
  const [inboundCarrier, setInboundCarrier] = useState<Carrier>("other");
  const [inboundTrackingNo, setInboundTrackingNo] = useState("");
  const [preferredInboundOrderIds, setPreferredInboundOrderIds] = useState<
    number[]
  >([]);

  const [selectedStockIds, setSelectedStockIds] = useState<number[]>([]);
  const [expandedOutboundOrderIds, setExpandedOutboundOrderIds] = useState<
    number[]
  >([]);
  const [expandedDraftBoxUids, setExpandedDraftBoxUids] = useState<string[]>(
    [],
  );
  const [expandedDraftOrderKeys, setExpandedDraftOrderKeys] = useState<
    string[]
  >([]);
  const [stockBoxes, setStockBoxes] = useState<StockBox[]>([]);
  const [inventoryBoxFilter, setInventoryBoxFilter] = useState<string>("all");
  const [inventoryQ, setInventoryQ] = useState("");
  const [mergeParentBoxId, setMergeParentBoxId] = useState("");
  const [stockBoxNoteDraft, setStockBoxNoteDraft] = useState("");
  const [selectedInventoryOrderIds, setSelectedInventoryOrderIds] = useState<
    number[]
  >([]);
  const [expandedInventoryOrderIds, setExpandedInventoryOrderIds] = useState<
    number[]
  >([]);
  const [draftBoxes, setDraftBoxes] = useState<DraftBox[]>([]);
  const [batchNote, setBatchNote] = useState("");
  const [freightExchangeRate, setFreightExchangeRate] = useState("");
  const [freightUnitPrice, setFreightUnitPrice] = useState("");
  const [chargeableWeight, setChargeableWeight] = useState("");
  const [batchReceivedDraft, setBatchReceivedDraft] = useState<
    Record<number, string>
  >({});
  const [outboundAllowMissingBarcode, setOutboundAllowMissingBarcode] =
    useState(false);
  const [outboundMissingBarcodeNote, setOutboundMissingBarcodeNote] =
    useState("");

  const inboundLines = useMemo(
    () =>
      orders.flatMap((order) =>
        order.lines.filter((line) => line.status === "ordered"),
      ),
    [orders],
  );
  const assignedIds = useMemo(
    () => new Set(draftBoxes.flatMap((box) => box.item_ids)),
    [draftBoxes],
  );
  const stockBoxByOrderId = useMemo(() => {
    const map = new Map<number, StockBox>();
    for (const box of stockBoxes) {
      for (const oid of box.order_ids) map.set(oid, box);
    }
    return map;
  }, [stockBoxes]);

  async function loadChrome() {
    const [nextStats, nextMeta, nextLog, kinds] = await Promise.all([
      fetchStats(),
      fetchMeta(),
      fetchLatestActionLog(),
      fetchProductKinds().catch(() => ({ labels: [] as string[], aliases: {} })),
    ]);
    setStats(nextStats);
    setMeta(nextMeta);
    setLatestLog(nextLog);
    setProductKinds(kinds.labels || []);
  }

  async function loadOrders() {
    const [list, shopList] = await Promise.all([
      fetchOrders({
        status: statusFilter || undefined,
        shop: shopFilter || undefined,
        q: q.trim() || undefined,
        expected_ship_month: shipMonthFilter || undefined,
      }),
      fetchShops(),
    ]);
    setOrders(list);
    setShops(shopList);
  }

  async function loadInbound() {
    const [list, pending] = await Promise.all([
      fetchOrders({ status: "ordered" }),
      fetchShipments({ direction: "inbound", status: "shipped" }),
    ]);
    const available = list.filter((order) =>
      order.lines.some((line) => line.status === "ordered"),
    );
    setOrders(available);
    setShipments(pending);
  }

  async function loadInventory() {
    const [lines, boxes] = await Promise.all([
      fetchItems({ status: "in_stock" }),
      fetchStockBoxes(),
    ]);
    setStockLines(lines);
    setStockBoxes(boxes);
  }

  async function loadOutbound() {
    const [lines, existing, boxes] = await Promise.all([
      fetchItems({ status: "in_stock" }),
      fetchOutboundBatches(),
      fetchStockBoxes(),
    ]);
    setStockLines(lines);
    setBatches(existing);
    setStockBoxes(boxes);
    const drafts: Record<number, string> = {};
    for (const batch of existing) {
      drafts[batch.id] = String(batch.amount_received_cny ?? 0);
    }
    setBatchReceivedDraft(drafts);
  }

  async function loadOrderRequests() {
    const list = await fetchOrderRequests(requestStatusFilter || undefined);
    setOrderRequests(list);
  }

  async function loadFinance() {
    setFinanceSummary(await fetchFinanceSummary(financeMonth));
  }

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      await loadChrome();
      if (tab === "orders") await loadOrders();
      if (tab === "finance") await loadFinance();
      if (tab === "requests") await loadOrderRequests();
      if (tab === "inbound") await loadInbound();
      if (tab === "inventory") await loadInventory();
      if (tab === "outbound") await loadOutbound();
      if (tab === "logs") setLogs(await fetchActionLogs(80));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    tab,
    statusFilter,
    shopFilter,
    shipMonthFilter,
    requestStatusFilter,
    financeMonth,
  ]);

  useEffect(() => {
    let cancelled = false;
    async function pollTunnel() {
      try {
        const status = await fetchTunnelStatus();
        if (!cancelled) setTunnel(status);
      } catch {
        if (!cancelled) {
          setTunnel({ running: false, url: "", stale: false });
        }
      }
    }
    void pollTunnel();
    const timer = window.setInterval(() => void pollTunnel(), 8000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (tab !== "inbound" || !preferredInboundOrderIds.length) return;
    const preferred = new Set(preferredInboundOrderIds);
    const ids = inboundLines
      .filter((line) => preferred.has(line.order_id))
      .map((line) => line.id);
    if (ids.length) setSelectedInboundIds(ids);
    setPreferredInboundOrderIds([]);
  }, [tab, preferredInboundOrderIds, inboundLines]);

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      await loadOrders();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }

  function updateDraftLine(index: number, patch: Partial<DraftLine>) {
    setForm((current) => ({
      ...current,
      lines: current.lines.map((line, i) =>
        i === index ? { ...line, ...patch } : line,
      ),
    }));
  }

  async function onCreateOrder(event: FormEvent) {
    event.preventDefault();
    setError("");
    setMessage("");
    const lines = form.lines
      .map((line) => ({
        name: line.name.trim(),
        shop: form.shop.trim(),
        qty: Math.max(1, Number(line.qty) || 1),
        unit_cost: line.unit_cost ? Number(line.unit_cost) : null,
        ip: line.ip.trim(),
        image_url: line.image_url.trim(),
        source_url: line.source_url.trim(),
      }))
      .filter((line) => line.name);
    if (!lines.length) {
      setError("请至少填写一行货品名称");
      return;
    }
    const lineQtySum = lines.reduce((sum, line) => sum + line.qty, 0);
    try {
      const shippingRaw = form.shipping_fee.trim();
      const shippingFee = shippingRaw === "" ? 0 : Number(shippingRaw);
      const rate = parsePositiveRate(form.exchange_rate);
      if (form.exchange_rate.trim() && rate == null) {
        setError("下单汇率须为大于 0 的数字");
        return;
      }
      await createOrder({
        order_ref: form.order_ref.trim(),
        shop: form.shop.trim(),
        order_qty: form.order_qty
          ? Math.max(1, Number(form.order_qty) || 1)
          : lineQtySum,
        shipping_fee: Number.isNaN(shippingFee) ? 0 : Math.max(0, shippingFee),
        exchange_rate: rate,
        order_image_url: form.order_image_url.trim(),
        note: form.note.trim(),
        expected_ship_at: form.expected_ship_at || null,
        expected_ship_period: form.expected_ship_at
          ? form.expected_ship_period || null
          : null,
        lines,
      });
      setForm({ ...EMPTY_FORM, lines: [EMPTY_LINE()] });
      setShowCreate(false);
      setMessage(`已登记订单（${lines.length} 行）`);
      await refresh();
    } catch (err) {
      setError(errorText(err));
    }
  }

  function toggleOrderSelected(orderId: number) {
    setSelectedOrderIds((ids) =>
      ids.includes(orderId) ? ids.filter((id) => id !== orderId) : [...ids, orderId],
    );
  }

  function toggleOrderExpanded(orderId: number) {
    setExpandedOrderIds((ids) =>
      ids.includes(orderId) ? ids.filter((id) => id !== orderId) : [...ids, orderId],
    );
  }

  async function onCancelSelectedOrders() {
    const targets = orders.filter(
      (order) =>
        selectedOrderIds.includes(order.id) &&
        order.status !== "cancelled" &&
        order.status !== "delivered",
    );
    if (!targets.length) {
      setError("没有可取消的已选订单");
      return;
    }
    const refs = targets
      .map((order) => order.order_ref || `#${order.id}`)
      .slice(0, 8)
      .join("、");
    const more =
      targets.length > 8 ? ` 等 ${targets.length} 笔` : `（共 ${targets.length} 笔）`;
    if (!confirm(`确认取消已选订单？\n${refs}${more}`)) return;
    if (
      !confirm(
        `再次确认：将取消 ${targets.length} 笔订单及其未完结明细，此操作请谨慎。\n确定继续？`,
      )
    ) {
      return;
    }
    try {
      for (const order of targets) {
        await updateOrder(order.id, { status: "cancelled" });
      }
      setSelectedOrderIds([]);
      setMessage(`已取消 ${targets.length} 笔订单`);
      await refresh();
    } catch (err) {
      setError(errorText(err));
    }
  }

  function sendSelectedToInbound() {
    const targets = orders.filter(
      (order) =>
        selectedOrderIds.includes(order.id) &&
        order.status !== "cancelled" &&
        order.status !== "delivered" &&
        order.lines.some((line) => line.status === "ordered"),
    );
    if (!targets.length) {
      setError("请勾选至少 1 笔仍有「已下单」行的订单");
      return;
    }
    setPreferredInboundOrderIds(targets.map((order) => order.id));
    setTab("inbound");
    setMessage(
      targets.length === 1
        ? `已带入订单 ${targets[0].order_ref || `#${targets[0].id}`} 到进库`
        : `已带入 ${targets.length} 笔订单到进库（可一次登记多个包裹）`,
    );
  }

  async function onUpdateLine(
    id: number,
    patch: { barcode?: string; status?: ItemStatus; qty?: number },
  ) {
    try {
      await updateItem(id, patch);
      await refresh();
    } catch (err) {
      setError(errorText(err));
    }
  }

  function looksLikeHtmlDocument(raw: string): boolean {
    const text = raw.trim();
    if (text.length < 200) return false;
    const lower = text.slice(0, 4000).toLowerCase();
    return (
      lower.startsWith("<!doctype html") ||
      lower.startsWith("<html") ||
      (lower.includes("<html") && lower.includes("</html")) ||
      (lower.includes("<head") && lower.includes("<body") && lower.includes("og:title"))
    );
  }

  function parseScrapeUrls(raw: string): string[] {
    const seen = new Set<string>();
    const urls: string[] = [];
    for (const part of raw.split(/[\n\r,;\t]+/)) {
      let text = part.trim();
      if (!text) continue;
      // allow "1. https://..." / "- https://..."
      text = text.replace(/^\d+[\.\)、]\s*/, "").replace(/^[-*•]\s*/, "");
      if (!/^https?:\/\//i.test(text) && text.includes(".")) {
        text = `https://${text}`;
      }
      if (!/^https?:\/\//i.test(text)) continue;
      const key = text.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      urls.push(text);
    }
    return urls;
  }

  function appendScrapeProducts(
    products: ScrapeProduct[],
    existing: ScrapeProduct[],
  ) {
    if (!products.length) return { next: existing, added: [] as ScrapeProduct[] };
    const seen = new Set(
      existing.map((p) => (p.source_url || p.name).trim().toLowerCase()),
    );
    const added: ScrapeProduct[] = [];
    for (const product of products) {
      const key = (product.source_url || product.name).trim().toLowerCase();
      if (key && seen.has(key)) continue;
      if (key) seen.add(key);
      added.push(product);
    }
    if (!added.length) return { next: existing, added };
    const base = existing.length;
    const next = [...existing, ...added];
    const newIndexes = added.map((_, i) => base + i);
    setCollection(next);
    setCollectionPick((pick) => [...pick, ...newIndexes]);
    setCollectionQty((qtyMap) => {
      const copy = { ...qtyMap };
      for (const index of newIndexes) {
        const product = next[index];
        const fromProduct =
          product.qty != null && product.qty >= 1 ? String(product.qty) : "";
        copy[index] = copy[index] || fromProduct || "1";
      }
      return copy;
    });
    setCollectionPrice((priceMap) => {
      const copy = { ...priceMap };
      for (const index of newIndexes) {
        const product = next[index];
        copy[index] =
          copy[index] ||
          (product.unit_cost != null ? String(product.unit_cost) : "");
      }
      return copy;
    });
    setCollectionBarcode((barcodeMap) => {
      const copy = { ...barcodeMap };
      for (const index of newIndexes) {
        const product = next[index];
        copy[index] = copy[index] || (product.barcode || "").trim();
      }
      return copy;
    });
    const withShip = products.find((product) => product.expected_ship_at);
    if (withShip?.expected_ship_at && !batchExpectedShip) {
      setBatchExpectedShip(withShip.expected_ship_at);
      setBatchExpectedPeriod(withShip.expected_ship_period || "");
    }
    return { next, added };
  }

  async function onScrape() {
    const raw = scrapeUrlValue;
    if (looksLikeHtmlDocument(raw)) {
      setScrapeBusy(true);
      setError("");
      setMessage("正在解析粘贴的页面 HTML…");
      try {
        const result = await scrapeUrl("", raw);
        const { added } = appendScrapeProducts(result.products || [], collection);
        if (result.order_ref?.trim()) {
          setScrapeOrderRef(result.order_ref.trim());
        }
        if (result.shipping_fee != null && !Number.isNaN(Number(result.shipping_fee))) {
          setScrapeShippingFee(String(result.shipping_fee));
        }
        setMessage(
          result.message ||
            `已从 HTML 解析，新增 ${added.length} 条商品`,
        );
        if (added.length) setScrapeUrlValue("");
      } catch (err) {
        setError(errorText(err));
      } finally {
        setScrapeBusy(false);
      }
      return;
    }

    const urls = parseScrapeUrls(raw);
    if (!urls.length) {
      setError(
        "请粘贴网址（每行一个），或粘贴浏览器「查看网页源代码」的整页 HTML（zozo.jp 等被拦截站点用）",
      );
      return;
    }
    setScrapeBusy(true);
    setError("");
    setMessage("");
    let addedTotal = 0;
    let ok = 0;
    let working = collection;
    const failures: string[] = [];
    let previousFailed = false;
    try {
      for (let i = 0; i < urls.length; i += 1) {
        const url = urls[i];
        if (i > 0) {
          const delayMs = batchScrapeDelayMs(
            urls[i - 1],
            url,
            previousFailed,
          );
          setMessage(`等待 ${Math.ceil(delayMs / 1000)} 秒后继续抓取 ${i + 1}/${urls.length}…`);
          await waitForBatchScrape(delayMs);
        }
        setMessage(`正在抓取 ${i + 1}/${urls.length}…`);
        previousFailed = false;
        try {
          const result = await scrapeUrl(url);
          ok += 1;
          const { next, added } = appendScrapeProducts(
            result.products || [],
            working,
          );
          working = next;
          addedTotal += added.length;
        } catch (err) {
          failures.push(`${url} → ${errorText(err)}`);
          previousFailed = true;
        }
      }
      const failText = failures.length
        ? `；失败 ${failures.length} 条`
        : "";
      setMessage(
        `抓取完成：成功 ${ok}/${urls.length} 个链接，新增 ${addedTotal} 条商品${failText}`,
      );
      if (failures.length) {
        setError(failures.slice(0, 5).join("\n"));
      }
      if (ok > 0) {
        setScrapeUrlValue("");
      }
    } finally {
      setScrapeBusy(false);
    }
  }

  async function onBatchCreate() {
    if (!collectionPick.length) {
      setError("请至少勾选一件");
      return;
    }
    const sharedRef =
      scrapeOrderRef.trim() || `SCRAPE-${new Date().toISOString().slice(0, 10)}`;
    try {
      const picked = collectionPick
        .slice()
        .sort((a, b) => a - b)
        .map((index) => {
          const product = collection[index];
          const shipAt =
            product.expected_ship_at || batchExpectedShip.trim() || null;
          const priceText = (collectionPrice[index] || "").trim();
          const unitCost = priceText
            ? Number(priceText)
            : product.unit_cost;
          return {
            name: product.name,
            shop: product.shop,
            qty: Math.max(1, Number(collectionQty[index]) || 1),
            unit_cost:
              unitCost != null && !Number.isNaN(Number(unitCost))
                ? Number(unitCost)
                : null,
            ip: product.ip,
            image_url: product.image_url,
            source_url: product.source_url,
            barcode: (collectionBarcode[index] || product.barcode || "").trim(),
            expected_ship_at: shipAt,
            expected_ship_period: product.expected_ship_at
              ? product.expected_ship_period || null
              : shipAt
                ? batchExpectedPeriod || null
                : null,
          };
        });
      const shop =
        picked.find((line) => line.shop)?.shop ||
        collection[collectionPick[0]]?.shop ||
        "";
      const lineQtySum = picked.reduce((sum, line) => sum + line.qty, 0);
      const shippingRaw = scrapeShippingFee.trim();
      const shippingFee = shippingRaw === "" ? 0 : Number(shippingRaw);
      const rate = parsePositiveRate(scrapeExchangeRate);
      if (scrapeExchangeRate.trim() && rate == null) {
        setError("下单汇率须为大于 0 的数字");
        return;
      }
      await createOrder({
        order_ref: sharedRef,
        shop,
        order_qty: scrapeOrderQty
          ? Math.max(1, Number(scrapeOrderQty) || 1)
          : lineQtySum,
        shipping_fee: Number.isNaN(shippingFee) ? 0 : Math.max(0, shippingFee),
        exchange_rate: rate,
        expected_ship_at: batchExpectedShip.trim() || null,
        expected_ship_period: batchExpectedShip.trim()
          ? batchExpectedPeriod || null
          : null,
        lines: picked,
      });
      setCollection([]);
      setCollectionPick([]);
      setCollectionQty({});
      setCollectionPrice({});
      setCollectionBarcode({});
      setScrapeUrlValue("");
      setScrapeOrderRef("");
      setScrapeOrderQty("");
      setScrapeShippingFee("0");
      setScrapeExchangeRate("");
      setBatchExpectedShip("");
      setBatchExpectedPeriod("");
      setMessage(`已导入 1 笔订单「${sharedRef}」，含 ${picked.length} 行明细`);
      setTab("orders");
      await refresh();
    } catch (err) {
      setError(errorText(err));
    }
  }

  function toggleInboundLine(lineId: number) {
    setSelectedInboundIds((current) =>
      current.includes(lineId)
        ? current.filter((id) => id !== lineId)
        : [...current, lineId],
    );
  }

  function toggleInboundOrderAll(orderId: number) {
    const ids = inboundLines
      .filter((line) => line.order_id === orderId)
      .map((line) => line.id);
    setSelectedInboundIds((current) => {
      const allSelected = ids.length > 0 && ids.every((id) => current.includes(id));
      return allSelected
        ? current.filter((id) => !ids.includes(id))
        : [...new Set([...current, ...ids])];
    });
  }

  function toggleInboundOrderExpanded(orderId: number) {
    setExpandedInboundOrderIds((ids) =>
      ids.includes(orderId) ? ids.filter((id) => id !== orderId) : [...ids, orderId],
    );
  }

  async function onConfirmInboundToStock() {
    const selected = inboundLines.filter((line) =>
      selectedInboundIds.includes(line.id),
    );
    if (!selected.length) {
      setError("请先勾选要进库的行");
      return;
    }
    const byOrder = new Map<number, Line[]>();
    for (const line of selected) {
      const list = byOrder.get(line.order_id) || [];
      list.push(line);
      byOrder.set(line.order_id, list);
    }
    const tracking = inboundTrackingNo.trim();
    if (tracking && byOrder.size > 1) {
      setError("填写快递单号时请只勾选一笔订单；多笔订单请留空单号或分开进库");
      return;
    }
    if (
      !confirm(
        `确认进库？将把已选 ${selected.length} 行直接变为在库（${byOrder.size} 笔订单）。`,
      )
    ) {
      return;
    }
    try {
      for (const [orderId, lines] of byOrder) {
        const shipment = await createOrderInbound(orderId, {
          tracking_no: tracking,
          carrier: inboundCarrier,
          item_ids: lines.map((line) => line.id),
        });
        await confirmShipment(shipment.id);
      }
      setSelectedInboundIds([]);
      setInboundTrackingNo("");
      setInboundCarrier("other");
      setMessage(`已进库 ${selected.length} 行，现为在库`);
      await refresh();
    } catch (err) {
      setError(errorText(err));
      await refresh();
    }
  }

  function toggleStockOrder(line: Line) {
    const ids = stockLines
      .filter((candidate) => candidate.order_id === line.order_id)
      .map((candidate) => candidate.id)
      .filter((id) => !assignedIds.has(id));
    setSelectedStockIds((current) => {
      const allSelected = ids.every((id) => current.includes(id));
      return allSelected
        ? current.filter((id) => !ids.includes(id))
        : [...new Set([...current, ...ids])];
    });
  }

  function toggleOutboundOrderExpanded(orderId: number) {
    setExpandedOutboundOrderIds((ids) =>
      ids.includes(orderId) ? ids.filter((id) => id !== orderId) : [...ids, orderId],
    );
  }

  function toggleDraftBoxExpanded(uid: string) {
    setExpandedDraftBoxUids((uids) =>
      uids.includes(uid) ? uids.filter((id) => id !== uid) : [...uids, uid],
    );
  }

  function toggleDraftOrderExpanded(boxUid: string, orderId: number) {
    const key = `${boxUid}:${orderId}`;
    setExpandedDraftOrderKeys((keys) =>
      keys.includes(key) ? keys.filter((k) => k !== key) : [...keys, key],
    );
  }

  function toggleInventoryOrderExpanded(orderId: number) {
    setExpandedInventoryOrderIds((ids) =>
      ids.includes(orderId) ? ids.filter((id) => id !== orderId) : [...ids, orderId],
    );
  }

  function toggleInventoryOrderSelected(orderId: number) {
    setSelectedInventoryOrderIds((ids) =>
      ids.includes(orderId) ? ids.filter((id) => id !== orderId) : [...ids, orderId],
    );
  }

  async function onCombineInventoryOrders() {
    const note = stockBoxNoteDraft.trim();
    const viewingBoxId = Number(inventoryBoxFilter);
    const viewingBox =
      inventoryBoxFilter !== "all" &&
      inventoryBoxFilter !== "unboxed" &&
      Number.isFinite(viewingBoxId) &&
      viewingBoxId > 0
        ? viewingBoxId
        : null;

    // No new orders: if viewing a box, just save its note
    if (selectedInventoryOrderIds.length < 1) {
      if (viewingBox != null) {
        try {
          const box = await updateStockBox(viewingBox, { note });
          setMessage(`已更新库存箱 #${box.box_no} 备注`);
          setStockBoxes(await fetchStockBoxes());
          setStockBoxNoteDraft(box.note || "");
        } catch (err) {
          setError(errorText(err));
        }
        return;
      }
      setError("请先勾选要合箱的在库订单");
      return;
    }
    try {
      const box = await combineStockBox({
        order_ids: selectedInventoryOrderIds,
        note,
      });
      setSelectedInventoryOrderIds([]);
      setMessage(
        `已合箱：库存箱 #${box.box_no}（${box.order_count} 单 / ${box.item_count} 行）`
          + (note ? ` · 备注已保存` : ""),
      );
      setStockBoxes(await fetchStockBoxes());
      setInventoryBoxFilter(String(box.id));
      setStockBoxNoteDraft(box.note || "");
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function onRemoveInventoryOrder(boxId: number, orderId: number) {
    try {
      await removeStockBoxOrders(boxId, [orderId]);
      setMessage("已从库存箱移出订单");
      setStockBoxes(await fetchStockBoxes());
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function onDissolveStockBox(boxId: number) {
    if (!confirm("解散该库存合箱？订单仍保持在库，仅取消合箱关系。")) return;
    try {
      await deleteStockBox(boxId);
      setMessage("已解散库存合箱");
      setStockBoxes(await fetchStockBoxes());
      if (inventoryBoxFilter === String(boxId)) {
        setInventoryBoxFilter("all");
        setStockBoxNoteDraft("");
      }
    } catch (err) {
      setError(errorText(err));
    }
  }

  function onInventoryBoxFilterChange(value: string) {
    setInventoryBoxFilter(value);
    setMergeParentBoxId("");
    if (value === "all" || value === "unboxed") {
      setStockBoxNoteDraft("");
      return;
    }
    const box = stockBoxes.find((b) => String(b.id) === value);
    setStockBoxNoteDraft(box?.note || "");
  }

  async function onMergeChildIntoMain() {
    if (!selectedInventoryBox) {
      setError("请先在箱号筛选中选中要作为子箱的 B 箱");
      return;
    }
    if (selectedInventoryBox.parent_id != null) {
      setError("当前箱已是子箱，请先拆出后再并入其他主箱");
      return;
    }
    if ((selectedInventoryBox.child_boxes?.length ?? 0) > 0) {
      setError("当前箱下还有子箱，不能再作为子箱并入主箱");
      return;
    }
    const parentId = Number(mergeParentBoxId);
    if (!Number.isFinite(parentId) || parentId < 1) {
      setError("请选择要并入的主箱 A");
      return;
    }
    try {
      const childId = selectedInventoryBox.id;
      const childNo = selectedInventoryBox.box_no;
      const parent = await mergeStockBoxChild(parentId, childId);
      setMessage(`已将箱 #${childNo} 作为子箱并入主箱 #${parent.box_no}`);
      setMergeParentBoxId("");
      const refreshed = await fetchStockBoxes();
      setStockBoxes(refreshed);
      setInventoryBoxFilter(String(childId));
      const current = refreshed.find((b) => b.id === childId);
      setStockBoxNoteDraft(current?.note || "");
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function onDetachChildBox(childId: number) {
    try {
      const box = await detachStockBoxChild(childId);
      setMessage(`已拆出子箱 #${box.box_no}，现为独立箱`);
      setStockBoxes(await fetchStockBoxes());
    } catch (err) {
      setError(errorText(err));
    }
  }

  function applyStockBoxSuggestions() {
    const unassigned = stockLines.filter((line) => !assignedIds.has(line.id));
    if (!unassigned.length) {
      setError("没有可分配的在库行");
      return;
    }
    const groups = new Map<string, number[]>();
    const orderKeys: string[] = [];
    for (const line of unassigned) {
      const box = stockBoxByOrderId.get(line.order_id);
      const key = box ? `box:${box.id}` : `order:${line.order_id}`;
      if (!groups.has(key)) {
        groups.set(key, []);
        orderKeys.push(key);
      }
      groups.get(key)!.push(line.id);
    }
    const startNo = draftBoxes.length
      ? Math.max(...draftBoxes.map((box) => box.box_no)) + 1
      : 1;
    const suggested: DraftBox[] = orderKeys.map((key, index) => ({
      uid: newDraftBoxUid(),
      box_no: startNo + index,
      carrier: "other" as Carrier,
      tracking_no: "",
      item_ids: groups.get(key) || [],
    }));
    setDraftBoxes((current) => [...current, ...suggested]);
    setExpandedDraftBoxUids((uids) => [
      ...uids,
      ...suggested.map((box) => box.uid),
    ]);
    setSelectedStockIds([]);
    setMessage(
      `已按库存合箱建议生成 ${suggested.length} 箱（可再改分箱/运单号）`,
    );
    setError("");
  }

  function addDraftBox() {
    if (!selectedStockIds.length) {
      setError("请先选择至少一个完整订单的在库行");
      return;
    }
    const uid = newDraftBoxUid();
    setDraftBoxes((current) => [
      ...current,
      {
        uid,
        box_no: current.length
          ? Math.max(...current.map((box) => box.box_no)) + 1
          : 1,
        carrier: "other",
        tracking_no: "",
        item_ids: selectedStockIds,
      },
    ]);
    setExpandedDraftBoxUids((uids) =>
      uids.includes(uid) ? uids : [...uids, uid],
    );
    setSelectedStockIds([]);
    setError("");
  }

  function updateDraftBox(index: number, patch: Partial<DraftBox>) {
    setDraftBoxes((current) =>
      current.map((box, boxIndex) =>
        boxIndex === index ? { ...box, ...patch } : box,
      ),
    );
  }

  function removeDraftLine(boxIndex: number, id: number) {
    const next = draftBoxes
      .map((box, index) =>
        index === boxIndex
          ? { ...box, item_ids: box.item_ids.filter((itemId) => itemId !== id) }
          : box,
      )
      .filter((box) => box.item_ids.length);
    const keep = new Set(next.map((box) => box.uid));
    setDraftBoxes(next);
    setExpandedDraftBoxUids((uids) => uids.filter((uid) => keep.has(uid)));
    setExpandedDraftOrderKeys((keys) =>
      keys.filter((key) => keep.has(key.split(":")[0] || "")),
    );
    setSelectedStockIds((current) => [...new Set([...current, id])]);
  }

  async function onCreateOutbound() {
    const included = new Set(draftBoxes.flatMap((box) => box.item_ids));
    const includedOrderIds = new Set(
      stockLines
        .filter((line) => included.has(line.id))
        .map((line) => line.order_id),
    );
    const missing = stockLines.filter(
      (line) => includedOrderIds.has(line.order_id) && !included.has(line.id),
    );
    if (!draftBoxes.length || missing.length) {
      setError(
        missing.length
          ? "出库批次不能部分出库：请把所选订单的全部在库行分配到箱子。"
          : "请至少创建一个箱子",
      );
      return;
    }
    if (draftBoxes.some((box) => !box.tracking_no.trim())) {
      setError("请填写每个箱子的快递单号");
      return;
    }
    const noBarcode = stockLines.filter(
      (line) => included.has(line.id) && !(line.barcode || "").trim(),
    );
    if (noBarcode.length && !outboundAllowMissingBarcode) {
      setError(
        `出库必须登记条形码：还有 ${noBarcode.length} 行未填写。请补条码，或勾选特殊情况并备注。`,
      );
      return;
    }
    if (
      noBarcode.length &&
      outboundAllowMissingBarcode &&
      !outboundMissingBarcodeNote.trim()
    ) {
      setError("勾选特殊情况时必须填写无条形码备注");
      return;
    }
    const freightRate = parsePositiveRate(freightExchangeRate);
    if (freightExchangeRate.trim() && freightRate == null) {
      setError("运费汇率须为大于 0 的数字");
      return;
    }
    const unitRaw = freightUnitPrice.trim();
    const weightRaw = chargeableWeight.trim();
    const unitPrice = unitRaw === "" ? null : Number(unitRaw);
    const weight = weightRaw === "" ? null : Number(weightRaw);
    if (unitRaw && (unitPrice == null || Number.isNaN(unitPrice) || unitPrice < 0)) {
      setError("运费单价无效");
      return;
    }
    if (weightRaw && (weight == null || Number.isNaN(weight) || weight < 0)) {
      setError("计费重量无效");
      return;
    }
    try {
      await createOutboundBatch({
        note: batchNote.trim(),
        boxes: draftBoxes.map((box) => ({
          box_no: box.box_no,
          carrier: box.carrier,
          tracking_no: box.tracking_no.trim(),
          item_ids: box.item_ids,
        })),
        allow_missing_barcode: outboundAllowMissingBarcode && noBarcode.length > 0,
        missing_barcode_note:
          outboundAllowMissingBarcode && noBarcode.length > 0
            ? outboundMissingBarcodeNote.trim()
            : "",
        freight_exchange_rate: freightRate,
        freight_unit_price_jpy: unitPrice,
        chargeable_weight: weight,
      });
      setDraftBoxes([]);
      setExpandedDraftBoxUids([]);
      setExpandedDraftOrderKeys([]);
      setSelectedStockIds([]);
      setBatchNote("");
      setFreightExchangeRate("");
      setFreightUnitPrice("");
      setChargeableWeight("");
      setOutboundAllowMissingBarcode(false);
      setOutboundMissingBarcodeNote("");
      setMessage("出库批次已创建（货款应收已锁定）");
      await refresh();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function onSaveBatchReceived(batch: OutboundBatch) {
    const raw = (batchReceivedDraft[batch.id] ?? "").trim();
    const amount = raw === "" ? 0 : Number(raw);
    if (Number.isNaN(amount) || amount < 0) {
      setError("已收款金额无效");
      return;
    }
    try {
      await updateOutboundBatchFinance(batch.id, {
        amount_received_cny: amount,
      });
      setMessage(`批次 #${batch.id} 已更新收款`);
      await loadOutbound();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function onSaveBatchFreight(batch: OutboundBatch, formEl: HTMLFormElement) {
    const fd = new FormData(formEl);
    const rateRaw = String(fd.get("freight_rate") || "").trim();
    const unitRaw = String(fd.get("freight_unit") || "").trim();
    const weightRaw = String(fd.get("freight_weight") || "").trim();
    const rate = parsePositiveRate(rateRaw);
    if (rateRaw && rate == null) {
      setError("运费汇率须为大于 0 的数字");
      return;
    }
    const unit = unitRaw === "" ? null : Number(unitRaw);
    const weight = weightRaw === "" ? null : Number(weightRaw);
    if (unitRaw && (unit == null || Number.isNaN(unit) || unit < 0)) {
      setError("运费单价无效");
      return;
    }
    if (weightRaw && (weight == null || Number.isNaN(weight) || weight < 0)) {
      setError("计费重量无效");
      return;
    }
    try {
      await updateOutboundBatchFinance(batch.id, {
        freight_exchange_rate: rate,
        freight_unit_price_jpy: unit,
        chargeable_weight: weight,
      });
      setMessage(`批次 #${batch.id} 国际运费已更新`);
      await loadOutbound();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function onConfirmInbound(id: number) {
    if (!confirm("确认整包到仓？包裹内全部货品将变为在库。")) return;
    try {
      await confirmShipment(id);
      setMessage("已确认到仓");
      await refresh();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function onConfirmAllInbound() {
    if (!shipments.length) {
      setError("没有待确认的进库包裹");
      return;
    }
    if (
      !confirm(
        `确认一键到仓？将确认全部 ${shipments.length} 个包裹，货品将变为在库。`,
      )
    ) {
      return;
    }
    try {
      for (const shipment of shipments) {
        await confirmShipment(shipment.id);
      }
      setMessage(`已确认 ${shipments.length} 个包裹到仓`);
      await refresh();
    } catch (err) {
      setError(errorText(err));
      await refresh();
    }
  }

  async function onConfirmBatch(id: number) {
    if (!confirm("确认整个批次签收？批次内全部箱子将被确认。")) return;
    try {
      await confirmOutboundBatch(id);
      setMessage("已确认批次签收");
      await refresh();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function onUndo(id: number) {
    if (!confirm("撤回该操作？仅可撤回最近一步。")) return;
    setUndoBusy(true);
    try {
      await undoActionLog(id);
      setMessage("已撤回");
      await refresh();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setUndoBusy(false);
    }
  }

  async function onTunnelStart() {
    setTunnelBusy(true);
    setError("");
    try {
      const status = await startTunnel();
      setTunnel({
        running: !!status.running,
        url: status.url || "",
        stale: !!status.stale,
      });
      setMessage(status.message || "隧道已启动");
      for (let i = 0; i < 8; i += 1) {
        await new Promise((r) => window.setTimeout(r, 800));
        const next = await fetchTunnelStatus();
        setTunnel(next);
        if (next.url) break;
      }
    } catch (err) {
      setError(errorText(err));
    } finally {
      setTunnelBusy(false);
    }
  }

  async function onTunnelStop() {
    setTunnelBusy(true);
    setError("");
    try {
      const status = await stopTunnel();
      setTunnel({
        running: !!status.running,
        url: status.url || "",
        stale: !!status.stale,
      });
      setMessage(status.message || "隧道已关闭");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setTunnelBusy(false);
    }
  }

  async function onConfirmRequest(req: OrderRequest) {
    const draft = confirmDraft[req.id] || {
      shop_order_ref: "",
      staff_note: "",
      create_stock: true,
      exchange_rate: "",
    };
    if (!draft.shop_order_ref.trim()) {
      setError("请填写店铺注文番号");
      return;
    }
    const rate = parsePositiveRate(draft.exchange_rate || "");
    if ((draft.exchange_rate || "").trim() && rate == null) {
      setError("下单汇率须为大于 0 的数字");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await confirmOrderRequest(req.id, {
        shop_order_ref: draft.shop_order_ref.trim(),
        staff_note: draft.staff_note.trim(),
        create_stock_order: draft.create_stock,
        shipping_fee: 0,
        exchange_rate: rate,
      });
      setMessage(
        draft.create_stock
          ? `申请 ${req.request_code} 已确认下单，并已生成库存订单`
          : `申请 ${req.request_code} 已确认下单`,
      );
      await loadOrderRequests();
      if (draft.create_stock) await loadOrders();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }

  async function onRejectRequest(req: OrderRequest) {
    const reason = (rejectDraft[req.id] || "").trim();
    if (!reason) {
      setError("请填写拒绝原因");
      return;
    }
    if (!confirm(`拒绝申请 ${req.request_code}？`)) return;
    setLoading(true);
    setError("");
    try {
      await rejectOrderRequest(req.id, reason);
      setMessage(`申请 ${req.request_code} 已拒绝`);
      await loadOrderRequests();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }

  const filteredInventoryGroups = useMemo(() => {
    let groups = groupLines(stockLines);
    if (inventoryBoxFilter === "unboxed") {
      groups = groups.filter(([orderId]) => !stockBoxByOrderId.has(orderId));
    } else if (inventoryBoxFilter !== "all") {
      const boxId = Number(inventoryBoxFilter);
      const selectedBox = stockBoxes.find((b) => b.id === boxId);
      const childIds = new Set(
        (selectedBox?.child_boxes || []).map((c) => c.id),
      );
      groups = groups.filter(([orderId]) => {
        const box = stockBoxByOrderId.get(orderId);
        if (!box) return false;
        return box.id === boxId || childIds.has(box.id);
      });
    }
    const q = inventoryQ.trim().toLowerCase();
    if (!q) return groups;
    return groups.filter(([orderId, group]) => {
      const box = stockBoxByOrderId.get(orderId);
      const boxHay = box
        ? [
            box.box_no,
            box.note || "",
            `#${box.id}`,
            box.parent_box_no != null ? `主箱 ${box.parent_box_no}` : "",
            box.parent_id == null && (box.child_boxes?.length ?? 0) > 0
              ? "主箱"
              : "",
            ...(box.child_boxes || []).map((c) => `#${c.box_no} ${c.note}`),
          ].join(" ")
        : "未合箱";
      if (boxHay.toLowerCase().includes(q)) return true;
      if (group.orderRef.toLowerCase().includes(q)) return true;
      return group.lines.some((line) => {
        const hay = [
          line.shop,
          line.ip,
          line.product_kind,
          line.name,
          line.order_ref,
          line.barcode,
          line.note,
          line.source_url,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return hay.includes(q);
      });
    });
  }, [stockLines, inventoryBoxFilter, stockBoxByOrderId, inventoryQ, stockBoxes]);

  const selectedInventoryBox = useMemo(() => {
    if (inventoryBoxFilter === "all" || inventoryBoxFilter === "unboxed") {
      return null;
    }
    return stockBoxes.find((b) => String(b.id) === inventoryBoxFilter) || null;
  }, [inventoryBoxFilter, stockBoxes]);

  /** Main boxes first; each child listed indented under its parent. */
  const inventoryBoxSelectOptions = useMemo(() => {
    const mains = stockBoxes
      .filter((b) => b.parent_id == null)
      .slice()
      .sort((a, b) => a.box_no - b.box_no || a.id - b.id);
    const byParent = new Map<number, typeof stockBoxes>();
    for (const box of stockBoxes) {
      if (box.parent_id == null) continue;
      const list = byParent.get(box.parent_id) || [];
      list.push(box);
      byParent.set(box.parent_id, list);
    }
    for (const list of byParent.values()) {
      list.sort((a, b) => a.box_no - b.box_no || a.id - b.id);
    }
    const rows: { box: (typeof stockBoxes)[number]; kind: "main" | "child" }[] =
      [];
    const seen = new Set<number>();
    for (const main of mains) {
      rows.push({ box: main, kind: "main" });
      seen.add(main.id);
      for (const child of byParent.get(main.id) || []) {
        rows.push({ box: child, kind: "child" });
        seen.add(child.id);
      }
    }
    // Orphan children (parent missing) — still show, indented
    for (const box of stockBoxes) {
      if (seen.has(box.id)) continue;
      rows.push({
        box,
        kind: box.parent_id != null ? "child" : "main",
      });
    }
    return rows;
  }, [stockBoxes]);

  const missingBarcodeLines = useMemo(
    () => stockLines.filter((line) => !(line.barcode || "").trim()),
    [stockLines],
  );

  const draftMissingBarcodeLines = useMemo(() => {
    const included = new Set(draftBoxes.flatMap((box) => box.item_ids));
    return stockLines.filter(
      (line) => included.has(line.id) && !(line.barcode || "").trim(),
    );
  }, [draftBoxes, stockLines]);

  return (
    <div className="app">
      {meta?.is_shadow && (
        <div className="shadow-banner">
          测试影子库 · 不参与实际库存
          <span className="muted"> · {meta.database}</span>
        </div>
      )}
      <header className="top">
        <div className="brand">
          <h1>Stockgood{meta?.is_shadow ? " · 测试" : ""}</h1>
          <p className="brand-flow">订单 → 进库 → 库存 → 出库 → 签收</p>
          <div className="tunnel-panel">
            <div className="tunnel-controls" aria-label="隧道开关">
              <button
                type="button"
                className="btn tunnel-toggle"
                disabled={tunnelBusy || !!tunnel?.running}
                onClick={() => void onTunnelStart()}
                title="开启 Cloudflare 临时隧道"
              >
                {tunnelBusy && !tunnel?.running ? "开启中…" : "开启"}
              </button>
              <button
                type="button"
                className="btn tunnel-toggle"
                disabled={
                  tunnelBusy || (!tunnel?.running && !tunnel?.stale && !tunnel?.url)
                }
                onClick={() => void onTunnelStop()}
                title="关闭隧道"
              >
                {tunnelBusy && tunnel?.running ? "关闭中…" : "关闭"}
              </button>
            </div>
            <div className="tunnel-stack">
              <div
                className={`tunnel-badge${tunnel?.running ? " on" : " off"}${tunnel?.stale ? " stale" : ""}`}
                title={
                  tunnel?.running
                    ? "Cloudflare 临时隧道运行中"
                    : tunnel?.stale
                      ? "隧道已断开（仍保留上次链接）"
                      : "隧道未开启"
                }
              >
                <span className="tunnel-dot" aria-hidden />
                <span className="tunnel-label">
                  {tunnel == null
                    ? "隧道检测中…"
                    : tunnel.running
                      ? "隧道开启"
                      : tunnel.stale
                        ? "隧道已断开"
                        : "隧道关闭"}
                </span>
                {tunnel?.url ? (
                  <a
                    className="tunnel-url"
                    href={tunnel.url}
                    target="_blank"
                    rel="noreferrer"
                    title="隧道入口"
                  >
                    {tunnel.url.replace(/^https:\/\//, "").replace(/\/+$/, "")}
                  </a>
                ) : null}
              </div>
              <div className="tunnel-apply-row">
                <span className="tunnel-apply-label">顾客申请页</span>
                <a
                  className="tunnel-url"
                  href={applyShareUrl(tunnel?.url)}
                  target="_blank"
                  rel="noreferrer"
                  title="发给朋友的申请页链接"
                >
                  {tunnel?.url
                    ? applyShareUrl(tunnel.url).replace(/^https:\/\//, "")
                    : "/apply"}
                </a>
                {tunnel?.url ? (
                  <button
                    type="button"
                    className="btn tunnel-copy"
                    onClick={() => {
                      void navigator.clipboard
                        .writeText(applyShareUrl(tunnel.url))
                        .then(() => {
                          setTunnelCopied(true);
                          window.setTimeout(() => setTunnelCopied(false), 1500);
                        });
                    }}
                  >
                    {tunnelCopied ? "已复制" : "复制"}
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        </div>
        {stats && (
          <div className="stats">
            {(
              [
                "ordered",
                "inbound_shipped",
                "in_stock",
                "outbound_shipped",
                "delivered",
              ] as ItemStatus[]
            ).map(
              (status) => (
                <div className="stat" key={status}>
                  <b>{stats[status]}</b>
                  <span>{STATUS_LABEL[status]}</span>
                </div>
              ),
            )}
          </div>
        )}
      </header>

      {meta?.auth_required ? (
        <div className="admin-token-bar panel">
          <label>
            管理口令
            <input
              type="password"
              value={adminTokenInput}
              onChange={(e) => setAdminTokenInput(e.target.value)}
              placeholder="X-Admin-Token"
              autoComplete="off"
            />
          </label>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setAdminToken(adminTokenInput.trim());
              setMessage(adminTokenInput.trim() ? "管理口令已保存" : "已清除管理口令");
              void refresh();
            }}
          >
            保存口令
          </button>
        </div>
      ) : null}

      <nav className="tabs">
        {(
          [
            ["orders", "订单"],
            ["finance", "财务"],
            ["requests", "申请单"],
            ["scrape", "抓取导入"],
            ["inbound", "进库"],
            ["inventory", "库存"],
            ["outbound", "出库"],
            ["logs", "操作日志"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            type="button"
            key={key}
            className={tab === key ? "active" : ""}
            onClick={() => {
              const switchTab = () => setTab(key);
              const doc = document as Document & {
                startViewTransition?: (cb: () => void) => void;
              };
              if (typeof doc.startViewTransition === "function") {
                doc.startViewTransition(switchTab);
              } else {
                switchTab();
              }
            }}
          >
            {label}
          </button>
        ))}
      </nav>

      {latestLog?.undoable && (
        <div className="undo-banner">
          <span>
            最近操作：{latestLog.summary}
            <span className="muted"> · {formatDate(latestLog.created_at)}</span>
          </span>
          <button
            type="button"
            className="btn"
            disabled={undoBusy}
            onClick={() => void onUndo(latestLog.id)}
          >
            {undoBusy ? "撤回中…" : "撤回"}
          </button>
        </div>
      )}
      {error && <div className="error">{error}</div>}
      {message && <div className="ok-msg">{message}</div>}
      {loading && <div className="muted">加载中…</div>}

      {tab === "orders" && (
        <section className="panel">
          <form className="toolbar" onSubmit={onSearch}>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">全部状态</option>
              {Object.entries(STATUS_LABEL).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <select value={shopFilter} onChange={(e) => setShopFilter(e.target.value)}>
              <option value="">全部店铺</option>
              {shops.map((shop) => <option key={shop}>{shop}</option>)}
            </select>
            <label className="inline-filter">
              预计发货
              <input
                type="month"
                value={shipMonthFilter}
                onChange={(e) => setShipMonthFilter(e.target.value)}
              />
            </label>
            <button
              type="button"
              className={`btn${shipMonthFilter === currentYearMonth() ? " btn-primary" : ""}`}
              onClick={() => setShipMonthFilter(currentYearMonth())}
            >
              本月
            </button>
            {shipMonthFilter && (
              <button type="button" className="btn" onClick={() => setShipMonthFilter("")}>
                清除月份
              </button>
            )}
            <input
              type="search"
              placeholder="搜索订单号 / 名称 / 店铺 / IP / 条形码"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            <button className="btn" type="submit">搜索</button>
            <button
              className="btn btn-primary"
              type="button"
              onClick={() => setShowCreate((value) => !value)}
            >
              {showCreate ? "收起" : "登记订单"}
            </button>
          </form>
          <p className="muted">{orders.length} 个订单</p>
          {showCreate && (
            <form className="create-box" onSubmit={onCreateOrder}>
              <div className="form-grid">
                <label>订单号<input value={form.order_ref} onChange={(e) => setForm({ ...form, order_ref: e.target.value })} /></label>
                <label>店铺<input value={form.shop} onChange={(e) => setForm({ ...form, shop: e.target.value })} /></label>
                <label>
                  下单数量
                  <input
                    type="number"
                    min={1}
                    value={form.order_qty}
                    placeholder="可留空=数量合计"
                    onChange={(e) => setForm({ ...form, order_qty: e.target.value })}
                  />
                </label>
                <label>
                  运费（JPY）
                  <input
                    type="number"
                    min={0}
                    step="1"
                    value={form.shipping_fee}
                    placeholder="整单运费"
                    onChange={(e) => setForm({ ...form, shipping_fee: e.target.value })}
                  />
                </label>
                <label>
                  下单汇率
                  <input
                    type="number"
                    min={0}
                    step="0.0001"
                    value={form.exchange_rate}
                    placeholder="如 0.048"
                    onChange={(e) =>
                      setForm({ ...form, exchange_rate: e.target.value })
                    }
                  />
                </label>
                <label>订单截图 URL<input value={form.order_image_url} onChange={(e) => setForm({ ...form, order_image_url: e.target.value })} /></label>
                <label>预计发货月<input type="month" value={form.expected_ship_at} onChange={(e) => setForm({ ...form, expected_ship_at: e.target.value })} /></label>
                <label>上中下旬<select value={form.expected_ship_period} disabled={!form.expected_ship_at} onChange={(e) => setForm({ ...form, expected_ship_period: e.target.value as "" | ExpectedShipPeriod })}><option value="">整月</option><option value="early">上旬</option><option value="mid">中旬</option><option value="late">下旬</option></select></label>
                <label className="full">备注<textarea value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></label>
              </div>
              <div className="draft-lines">
                <div className="toolbar">
                  <strong>明细行（一单可多品）</strong>
                  <button
                    type="button"
                    className="btn"
                    onClick={() =>
                      setForm((current) => ({
                        ...current,
                        lines: [...current.lines, EMPTY_LINE()],
                      }))
                    }
                  >
                    添加一行
                  </button>
                </div>
                {form.lines.map((line, index) => (
                  <div className="draft-line" key={index}>
                    <div className="draft-line-head">
                      <span>第 {index + 1} 行</span>
                      {form.lines.length > 1 && (
                        <button
                          type="button"
                          className="btn btn-danger"
                          onClick={() =>
                            setForm((current) => ({
                              ...current,
                              lines: current.lines.filter((_, i) => i !== index),
                            }))
                          }
                        >
                          删除
                        </button>
                      )}
                    </div>
                    <div className="form-grid">
                      <label className="full">
                        货品名称 *
                        <input
                          required
                          value={line.name}
                          onChange={(e) => updateDraftLine(index, { name: e.target.value })}
                        />
                      </label>
                      <label>
                        数量
                        <input
                          type="number"
                          min={1}
                          value={line.qty}
                          onChange={(e) => updateDraftLine(index, { qty: e.target.value })}
                        />
                      </label>
                      <label>
                        单价
                        <input
                          type="number"
                          step="0.01"
                          value={line.unit_cost}
                          onChange={(e) => updateDraftLine(index, { unit_cost: e.target.value })}
                        />
                      </label>
                      <label>
                        IP / 作品
                        <input
                          value={line.ip}
                          onChange={(e) => updateDraftLine(index, { ip: e.target.value })}
                        />
                      </label>
                      <label>
                        货品图片 URL
                        <input
                          value={line.image_url}
                          onChange={(e) => updateDraftLine(index, { image_url: e.target.value })}
                        />
                      </label>
                      <label className="full">
                        原链接
                        <input
                          value={line.source_url}
                          onChange={(e) => updateDraftLine(index, { source_url: e.target.value })}
                        />
                      </label>
                    </div>
                  </div>
                ))}
              </div>
              <button className="btn btn-primary">保存订单（{form.lines.length} 行）</button>
            </form>
          )}
          {orders.length > 0 && (
            <div className="toolbar order-select-bar">
              <label className="check-inline">
                <input
                  type="checkbox"
                  checked={
                    orders.length > 0 &&
                    orders.every((order) => selectedOrderIds.includes(order.id))
                  }
                  onChange={(e) =>
                    setSelectedOrderIds(
                      e.target.checked ? orders.map((order) => order.id) : [],
                    )
                  }
                />
                全选
              </label>
              <span className="muted">已选 {selectedOrderIds.length} / {orders.length}</span>
              <button type="button" className="btn" onClick={() => setSelectedOrderIds([])}>
                清空勾选
              </button>
              <button type="button" className="btn" onClick={sendSelectedToInbound}>
                进库所选
              </button>
              <button type="button" className="btn btn-danger" onClick={() => void onCancelSelectedOrders()}>
                取消所选
              </button>
            </div>
          )}
          <div className="order-table">
            <div className="order-table-head">
              <span />
              <span>订单号</span>
              <span>状态</span>
              <span>店铺</span>
              <span>IP</span>
              <span>汇率</span>
              <span>商品¥</span>
              <span>运费¥</span>
              <span>合计¥/CNY</span>
              <span>预计发货</span>
              <span />
            </div>
            {orders.length === 0 ? (
              <div className="empty">暂无订单</div>
            ) : (
              orders.map((order) => (
                <OrderCard
                  key={order.id}
                  order={order}
                  selected={selectedOrderIds.includes(order.id)}
                  expanded={expandedOrderIds.includes(order.id)}
                  onToggleSelect={() => toggleOrderSelected(order.id)}
                  onToggleExpand={() => toggleOrderExpanded(order.id)}
                  onEnsureExpanded={() => {
                    if (!expandedOrderIds.includes(order.id)) {
                      toggleOrderExpanded(order.id);
                    }
                  }}
                  onBarcode={(id, barcode) => void onUpdateLine(id, { barcode })}
                  onQty={(id, qty) => void onUpdateLine(id, { qty })}
                  onProductKind={(id, product_kind) =>
                    void onUpdateLine(id, { product_kind })
                  }
                  onCancelLine={(id) => void onUpdateLine(id, { status: "cancelled" })}
                  productKinds={productKinds}
                  onShippingFee={(fee) =>
                    void updateOrder(order.id, { shipping_fee: fee })
                      .then(() => refresh())
                      .catch((err) => setError(errorText(err)))
                  }
                  onExchangeRate={(rate) =>
                    void updateOrder(order.id, { exchange_rate: rate })
                      .then(() => refresh())
                      .catch((err) => setError(errorText(err)))
                  }
                  onOrderRef={(orderRef) =>
                    void updateOrder(order.id, { order_ref: orderRef })
                      .then(() => refresh())
                      .catch((err) => setError(errorText(err)))
                  }
                />
              ))
            )}
          </div>
        </section>
      )}

      {tab === "finance" && (
        <section className="panel">
          <p className="muted">
            本月下单按 ordered_at；本月出库按出库批次创建时间。货款 CNY =
            日元 × 下单汇率；国际运费单独汇率。
          </p>
          <div className="toolbar">
            <label>
              月份
              <input
                type="month"
                value={financeMonth}
                onChange={(e) => setFinanceMonth(e.target.value)}
              />
            </label>
            <button type="button" className="btn" onClick={() => void loadFinance()}>
              刷新
            </button>
          </div>
          {!financeSummary ? (
            <div className="empty">暂无财务数据</div>
          ) : (
            <div className="finance-grid">
              <article className="finance-card">
                <h3>本月下单（{financeSummary.month}）</h3>
                <p>
                  订单数 <strong>{financeSummary.ordered.order_count}</strong>
                  {financeSummary.ordered.missing_rate_count > 0 && (
                    <span className="muted">
                      {" "}
                      · {financeSummary.ordered.missing_rate_count} 单无汇率
                    </span>
                  )}
                </p>
                <ul>
                  <li>商品 JPY：{moneyText(financeSummary.ordered.goods_jpy, "0")}</li>
                  <li>运费 JPY：{moneyText(financeSummary.ordered.shipping_jpy, "0")}</li>
                  <li>合计 JPY：{moneyText(financeSummary.ordered.total_jpy, "0")}</li>
                  <li>商品 CNY：{moneyText(financeSummary.ordered.goods_cny)}</li>
                  <li>运费 CNY：{moneyText(financeSummary.ordered.shipping_cny)}</li>
                  <li>
                    合计 CNY：
                    <strong>{moneyText(financeSummary.ordered.total_cny)}</strong>
                  </li>
                </ul>
              </article>
              <article className="finance-card">
                <h3>本月出库（{financeSummary.month}）</h3>
                <p>
                  批次数 <strong>{financeSummary.outbound.batch_count}</strong>
                </p>
                <ul>
                  <li>货款 JPY：{moneyText(financeSummary.outbound.goods_jpy, "0")}</li>
                  <li>
                    货款应收 CNY：
                    {moneyText(financeSummary.outbound.goods_receivable_cny)}
                  </li>
                  <li>
                    国际运费 CNY：{moneyText(financeSummary.outbound.freight_cny)}
                  </li>
                  <li>
                    应收合计 CNY：
                    <strong>
                      {moneyText(financeSummary.outbound.amount_receivable_cny)}
                    </strong>
                  </li>
                  <li>
                    已收 CNY：
                    {moneyText(financeSummary.outbound.amount_received_cny, "0")}
                  </li>
                  <li>
                    未收 CNY：
                    <strong>
                      {moneyText(financeSummary.outbound.amount_unreceived_cny)}
                    </strong>
                  </li>
                </ul>
              </article>
            </div>
          )}
        </section>
      )}

      {tab === "requests" && (
        <section className="panel">
          <p className="muted">
            顾客通过 /apply 提交的申请。确认下单后可回填店铺注文番号，并可选生成库存订单。
          </p>
          <div className="toolbar">
            <label>
              状态
              <select
                value={requestStatusFilter}
                onChange={(e) => setRequestStatusFilter(e.target.value)}
              >
                <option value="">全部</option>
                <option value="submitted">已提交</option>
                <option value="ordered">已下单</option>
                <option value="rejected">已拒绝</option>
              </select>
            </label>
            <button type="button" className="btn" onClick={() => void loadOrderRequests()}>
              刷新
            </button>
          </div>
          {orderRequests.length === 0 ? (
            <div className="empty">暂无申请单</div>
          ) : (
            <div className="request-list">
              {orderRequests.map((req) => {
                const draft = confirmDraft[req.id] || {
                  shop_order_ref: req.shop_order_ref || "",
                  staff_note: req.staff_note || "",
                  create_stock: true,
                  exchange_rate: "",
                };
                return (
                  <article className="request-card" key={req.id}>
                    <header>
                      <div className="request-main">
                        {req.image_url ? (
                          <img
                            className="thumb"
                            src={req.image_url}
                            alt=""
                            referrerPolicy="no-referrer"
                          />
                        ) : (
                          <span className="thumb placeholder" />
                        )}
                        <div>
                          <strong>{req.name}</strong>
                          <p className="muted">
                            {req.request_code} · ×{req.qty}
                            {req.shop ? ` · ${req.shop}` : ""}
                            {req.unit_cost != null ? ` · ¥${req.unit_cost}` : ""}
                          </p>
                          {req.source_url ? (
                            <a href={req.source_url} target="_blank" rel="noreferrer">
                              原链接
                            </a>
                          ) : null}
                        </div>
                      </div>
                      <span className={`pill status-${req.status}`}>
                        {REQUEST_STATUS_LABEL[req.status]}
                      </span>
                    </header>
                    <div className="request-meta muted">
                      {req.contact ? <span>ID：{req.contact}</span> : null}
                      {req.note ? <span>顾客备注：{req.note}</span> : null}
                      <span>提交：{formatDate(req.created_at)}</span>
                      {req.stock_order_id ? (
                        <span>库存订单 #{req.stock_order_id}</span>
                      ) : null}
                      {req.shop_order_ref ? (
                        <span>注文：{req.shop_order_ref}</span>
                      ) : null}
                      {req.reject_reason ? (
                        <span className="error">拒绝：{req.reject_reason}</span>
                      ) : null}
                    </div>
                    {req.status === "submitted" ? (
                      <div className="request-actions">
                        <label>
                          店铺注文番号
                          <input
                            value={draft.shop_order_ref}
                            onChange={(e) =>
                              setConfirmDraft((cur) => ({
                                ...cur,
                                [req.id]: { ...draft, shop_order_ref: e.target.value },
                              }))
                            }
                            placeholder="日本站订单号"
                          />
                        </label>
                        <label>
                          备注（顾客可见）
                          <input
                            value={draft.staff_note}
                            onChange={(e) =>
                              setConfirmDraft((cur) => ({
                                ...cur,
                                [req.id]: { ...draft, staff_note: e.target.value },
                              }))
                            }
                          />
                        </label>
                        <label>
                          下单汇率
                          <input
                            type="number"
                            min={0}
                            step="0.0001"
                            value={draft.exchange_rate}
                            placeholder="生成库存订单时写入"
                            onChange={(e) =>
                              setConfirmDraft((cur) => ({
                                ...cur,
                                [req.id]: {
                                  ...draft,
                                  exchange_rate: e.target.value,
                                },
                              }))
                            }
                          />
                        </label>
                        <label className="check">
                          <input
                            type="checkbox"
                            checked={draft.create_stock}
                            onChange={(e) =>
                              setConfirmDraft((cur) => ({
                                ...cur,
                                [req.id]: {
                                  ...draft,
                                  create_stock: e.target.checked,
                                },
                              }))
                            }
                          />
                          同时生成库存订单
                        </label>
                        <button
                          type="button"
                          className="btn btn-primary"
                          onClick={() => void onConfirmRequest(req)}
                        >
                          确认已下单
                        </button>
                        <label>
                          拒绝原因
                          <input
                            value={rejectDraft[req.id] || ""}
                            onChange={(e) =>
                              setRejectDraft((cur) => ({
                                ...cur,
                                [req.id]: e.target.value,
                              }))
                            }
                            placeholder="缺货 / 链接无效…"
                          />
                        </label>
                        <button
                          type="button"
                          className="btn btn-danger"
                          onClick={() => void onRejectRequest(req)}
                        >
                          拒绝
                        </button>
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </div>
          )}
        </section>
      )}

      {tab === "scrape" && (
        <section className="panel">
          <p className="muted">
            支持批量粘贴多个商品/系列/店铺链接（每行一个，也可用逗号分隔）。
            zozo.jp：商品页或「注文内容の詳細」整页源代码可粘贴抓取（订单列表页请改开详情）。
            结果会累加到同一清单；勾选后点「导入为一笔订单」。
          </p>
          <div className="scrape-bar scrape-bar-batch">
            <label className="grow">
              URL 列表 / 页面 HTML
              <textarea
                rows={5}
                value={scrapeUrlValue}
                onChange={(e) => setScrapeUrlValue(e.target.value)}
                placeholder={"每行一个链接，或粘贴整页 HTML（zozo 等）\nhttps://jumpcs.shueisha.co.jp/shop/g/g4530430540549/\nhttps://animegood.shop/products/xxx"}
              />
            </label>
            <div className="scrape-actions">
              <button type="button" className="btn btn-primary" disabled={scrapeBusy} onClick={() => void onScrape()}>
                {scrapeBusy
                  ? "抓取中…"
                  : looksLikeHtmlDocument(scrapeUrlValue)
                    ? "解析 HTML"
                    : `批量抓取（${parseScrapeUrls(scrapeUrlValue).length || 0}）`}
              </button>
              {collection.length > 0 && (
                <button
                  type="button"
                  className="btn"
                  onClick={() => {
                    setCollection([]);
                    setCollectionPick([]);
                    setCollectionQty({});
                    setCollectionPrice({});
                    setCollectionBarcode({});
                  }}
                >
                  清空清单
                </button>
              )}
            </div>
          </div>
          {collection.length > 0 && (
            <div className="collection-box">
              <div className="form-grid">
                <label>订单号（共用）<input value={scrapeOrderRef} onChange={(e) => setScrapeOrderRef(e.target.value)} placeholder="留空则自动生成" /></label>
                <label>下单数量（整单）<input type="number" min={1} value={scrapeOrderQty} onChange={(e) => setScrapeOrderQty(e.target.value)} placeholder="可留空=数量合计" /></label>
                <label>运费（JPY）<input type="number" min={0} step="1" value={scrapeShippingFee} onChange={(e) => setScrapeShippingFee(e.target.value)} placeholder="整单运费" /></label>
                <label>下单汇率<input type="number" min={0} step="0.0001" value={scrapeExchangeRate} onChange={(e) => setScrapeExchangeRate(e.target.value)} placeholder="如 0.048" /></label>
                <label>共用预计发货月<input type="month" value={batchExpectedShip} onChange={(e) => setBatchExpectedShip(e.target.value)} /></label>
                <label>共用上中下旬<select value={batchExpectedPeriod} disabled={!batchExpectedShip} onChange={(e) => setBatchExpectedPeriod(e.target.value as "" | ExpectedShipPeriod)}><option value="">整月</option><option value="early">上旬</option><option value="mid">中旬</option><option value="late">下旬</option></select></label>
              </div>
              <div className="toolbar">
                <span className="muted">清单 {collection.length} 条，已选 {collectionPick.length} → 将导入为 1 笔订单</span>
                <button type="button" className="btn" onClick={() => setCollectionPick(collection.map((_, index) => index))}>全选</button>
                <button type="button" className="btn" onClick={() => setCollectionPick([])}>取消勾选</button>
                <button type="button" className="btn btn-primary" onClick={() => void onBatchCreate()}>导入为一笔订单</button>
              </div>
              <div className="collection-list">
                {collection.map((product, index) => (
                  <div className="collection-row" key={`${product.source_url}-${index}`}>
                    <label className="collection-main">
                      <input type="checkbox" checked={collectionPick.includes(index)} onChange={() => setCollectionPick((current) => current.includes(index) ? current.filter((value) => value !== index) : [...current, index])} />
                      {product.image_url ? <img className="thumb" src={product.image_url} alt="" referrerPolicy="no-referrer" /> : <span className="thumb placeholder" />}
                      <span>
                        <strong>{product.name}</strong>
                        <span className="muted">
                          {" "}
                          · {product.shop}
                          {product.unit_cost != null
                            ? ` · ¥${product.unit_cost}`
                            : " · 无标价"}
                          {product.expected_ship_at
                            ? ` · ${formatExpectedShip(product.expected_ship_at, product.expected_ship_period)}`
                            : ""}
                        </span>
                      </span>
                    </label>
                    <label className="collection-qty">
                      单价
                      <input
                        type="number"
                        step="0.01"
                        min={0}
                        value={collectionPrice[index] ?? ""}
                        disabled={!collectionPick.includes(index)}
                        placeholder="JPY"
                        onChange={(e) =>
                          setCollectionPrice({
                            ...collectionPrice,
                            [index]: e.target.value,
                          })
                        }
                      />
                    </label>
                    <label className="collection-qty">
                      JAN
                      <input
                        className="collection-jan"
                        type="text"
                        inputMode="numeric"
                        pattern="[0-9]{8}|[0-9]{13}"
                        maxLength={13}
                        value={collectionBarcode[index] ?? ""}
                        disabled={!collectionPick.includes(index)}
                        placeholder="8/13位"
                        title="仅接受校验通过的 JAN/EAN（8 或 13 位）"
                        onChange={(e) =>
                          setCollectionBarcode({
                            ...collectionBarcode,
                            [index]: e.target.value.replace(/\D/g, "").slice(0, 13),
                          })
                        }
                      />
                    </label>
                    <label className="collection-qty">数量<input type="number" min={1} value={collectionQty[index] || "1"} disabled={!collectionPick.includes(index)} onChange={(e) => setCollectionQty({ ...collectionQty, [index]: e.target.value })} /></label>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {tab === "inbound" && (
        <section className="panel">
          <p className="muted">
            勾选待进库行后点「确认进库」，直接变为在库。快递单号可选；多笔订单同时进库时请留空单号。
          </p>
          <h2>待进库</h2>
          <div className="item-pick">
            {inboundLines.length === 0 ? (
              <div className="empty">没有可进库的订单行</div>
            ) : (
              groupLines(inboundLines).map(([orderId, group]) => {
                const ids = group.lines.map((line) => line.id);
                const orderChecked =
                  ids.length > 0 &&
                  ids.every((id) => selectedInboundIds.includes(id));
                const expanded = expandedInboundOrderIds.includes(orderId);
                return (
                  <div className="order-sub" key={orderId}>
                    <div className="order-sub-head">
                      <div className="order-sub-check">
                        <label className="order-check">
                          <input
                            type="checkbox"
                            checked={orderChecked}
                            onChange={() => toggleInboundOrderAll(orderId)}
                          />
                        </label>
                        <button
                          type="button"
                          className="order-ref-btn mono"
                          onClick={() => toggleInboundOrderExpanded(orderId)}
                        >
                          {group.orderRef}
                        </button>
                        <span className="muted"> · {group.lines.length} 行</span>
                      </div>
                      <button
                        type="button"
                        className="btn"
                        onClick={() => toggleInboundOrderExpanded(orderId)}
                      >
                        {expanded ? "收起" : "明细"}
                      </button>
                    </div>
                    {expanded &&
                      group.lines.map((line) => (
                        <label key={line.id}>
                          <input
                            type="checkbox"
                            checked={selectedInboundIds.includes(line.id)}
                            onChange={() => toggleInboundLine(line.id)}
                          />
                          {line.image_url ? (
                            <img
                              className="thumb"
                              src={line.image_url}
                              alt=""
                              referrerPolicy="no-referrer"
                            />
                          ) : (
                            <span className="thumb placeholder" />
                          )}
                          <span>
                            {line.name}
                            <span className="muted"> · x{line.qty}</span>
                          </span>
                        </label>
                      ))}
                  </div>
                );
              })
            )}
          </div>
          <div className="form-grid">
            <CarrierSelect
              value={inboundCarrier}
              onChange={setInboundCarrier}
            />
            <label>
              快递单号
              <input
                value={inboundTrackingNo}
                placeholder="可选"
                onChange={(e) => setInboundTrackingNo(e.target.value)}
              />
            </label>
          </div>
          <div className="toolbar">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void onConfirmInboundToStock()}
            >
              确认进库（已选 {selectedInboundIds.length}）
            </button>
          </div>

          {shipments.length > 0 && (
            <>
              <div className="toolbar">
                <h2>历史待确认</h2>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => void onConfirmAllInbound()}
                >
                  一键确认全部（{shipments.length}）
                </button>
              </div>
              <p className="muted">旧流程遗留的「已发往仓库」包裹，确认后变为在库。</p>
              {shipments.map((shipment) => (
                <article className="ship-card" key={shipment.id}>
                  <header>
                    <div>
                      <strong className="mono">
                        {shipment.tracking_no || "无单号"}
                      </strong>{" "}
                      · {CARRIER_LABEL[shipment.carrier]}
                      <div className="muted">发货 {formatDate(shipment.shipped_at)}</div>
                    </div>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => void onConfirmInbound(shipment.id)}
                    >
                      确认到仓
                    </button>
                  </header>
                  <OrderGroups
                    groups={shipment.order_groups}
                    fallback={shipment.items}
                    barcode={(id, value) => void onUpdateLine(id, { barcode: value })}
                  />
                </article>
              ))}
            </>
          )}
        </section>
      )}

      {tab === "inventory" && (
        <section className="panel">
          <p className="muted">
            仅显示当前在库订单。合箱只做仓库编组，不改变货品状态，也不等于出库装箱。可将 B 箱作为子箱并入主箱 A（订单仍留在 B）。出库前请补齐条形码。
          </p>
          {missingBarcodeLines.length > 0 && (
            <div className="warn-banner">
              有 {missingBarcodeLines.length} 件在库商品尚未添加条形码
              （涉及{" "}
              {
                new Set(missingBarcodeLines.map((line) => line.order_id)).size
              }{" "}
              笔订单）。展开明细可补录；出库时必须登记条码。
            </div>
          )}
          <div className="form-grid inventory-filter-row">
            <label>
              搜索
              <input
                type="search"
                value={inventoryQ}
                placeholder="店铺 / IP / 种类 / 订单号 / 品名 / 条码 / 箱号备注"
                onChange={(e) => setInventoryQ(e.target.value)}
              />
            </label>
            <label>
              箱号筛选
              <select
                value={inventoryBoxFilter}
                onChange={(e) => onInventoryBoxFilterChange(e.target.value)}
              >
                <option value="all">全部在库</option>
                <option value="unboxed">未合箱</option>
                {inventoryBoxSelectOptions.map(({ box, kind }) => {
                  const note = box.note ? ` · ${box.note}` : " · 无备注";
                  const counts = `（${box.order_count} 单）`;
                  if (kind === "child") {
                    return (
                      <option key={box.id} value={String(box.id)}>
                        {`　└ 子箱 #${box.box_no}${note}${counts}`}
                      </option>
                    );
                  }
                  const childCount = box.child_boxes?.length ?? 0;
                  const mainTag =
                    childCount > 0
                      ? `（主箱 · ${childCount} 子箱）`
                      : "";
                  return (
                    <option key={box.id} value={String(box.id)}>
                      {`#${box.box_no}${mainTag}${note}${counts}`}
                    </option>
                  );
                })}
              </select>
            </label>
          </div>
          <div className="toolbar">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void onCombineInventoryOrders()}
            >
              {selectedInventoryOrderIds.length > 0
                ? `合箱（已选 ${selectedInventoryOrderIds.length} 单）`
                : selectedInventoryBox
                  ? "保存备注"
                  : "合箱"}
            </button>
            <label className="inline-filter">
              箱子备注
              <input
                value={stockBoxNoteDraft}
                placeholder="点合箱时一并保存"
                onChange={(e) => setStockBoxNoteDraft(e.target.value)}
              />
            </label>
            {selectedInventoryBox && (
              <button
                type="button"
                className="btn btn-danger"
                onClick={() => void onDissolveStockBox(selectedInventoryBox.id)}
              >
                解散当前箱
              </button>
            )}
            <span className="muted">
              显示 {filteredInventoryGroups.length} 单
              {inventoryQ.trim() ? ` · 搜索「${inventoryQ.trim()}」` : ""}
            </span>
          </div>
          {selectedInventoryBox &&
            selectedInventoryBox.parent_id == null &&
            (selectedInventoryBox.child_boxes?.length ?? 0) === 0 && (
            <div className="toolbar">
              <span className="muted">
                当前 B 箱 #{selectedInventoryBox.box_no}
              </span>
              <label className="inline-filter">
                并入主箱
                <select
                  value={mergeParentBoxId}
                  onChange={(e) => setMergeParentBoxId(e.target.value)}
                >
                  <option value="">选择主箱 A…</option>
                  {stockBoxes
                    .filter(
                      (b) =>
                        b.id !== selectedInventoryBox.id &&
                        b.parent_id == null,
                    )
                    .map((b) => (
                      <option key={b.id} value={String(b.id)}>
                        #{b.box_no}
                        {b.note ? ` · ${b.note}` : ""}
                        {`（${b.order_count} 单`}
                        {b.child_boxes?.length
                          ? ` + ${b.child_boxes.length} 子箱`
                          : ""}
                        ）
                      </option>
                    ))}
                </select>
              </label>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => void onMergeChildIntoMain()}
              >
                合并为子箱
              </button>
            </div>
          )}
          {selectedInventoryBox?.parent_id != null && (
            <div className="toolbar">
              <span className="muted">
                当前为子箱 #{selectedInventoryBox.box_no}，隶属于主箱 #
                {selectedInventoryBox.parent_box_no}
              </span>
              <button
                type="button"
                className="btn"
                onClick={() => void onDetachChildBox(selectedInventoryBox.id)}
              >
                从主箱拆出
              </button>
            </div>
          )}
          {selectedInventoryBox &&
            selectedInventoryBox.parent_id == null &&
            (selectedInventoryBox.child_boxes?.length ?? 0) > 0 && (
            <div className="toolbar">
              <span className="muted">
                当前为主箱 #{selectedInventoryBox.box_no}，子箱：
                {selectedInventoryBox.child_boxes
                  .map((c) => `#${c.box_no}`)
                  .join("、")}
              </span>
            </div>
          )}
          {filteredInventoryGroups.length > 0 && (
            <div className="toolbar order-select-bar">
              <label className="check-inline">
                <input
                  type="checkbox"
                  checked={
                    filteredInventoryGroups.length > 0 &&
                    filteredInventoryGroups.every(([orderId]) =>
                      selectedInventoryOrderIds.includes(orderId),
                    )
                  }
                  ref={(el) => {
                    if (!el) return;
                    const visibleIds = filteredInventoryGroups.map(
                      ([orderId]) => orderId,
                    );
                    const selectedVisible = visibleIds.filter((id) =>
                      selectedInventoryOrderIds.includes(id),
                    );
                    el.indeterminate =
                      selectedVisible.length > 0 &&
                      selectedVisible.length < visibleIds.length;
                  }}
                  onChange={(e) => {
                    const visibleIds = filteredInventoryGroups.map(
                      ([orderId]) => orderId,
                    );
                    if (e.target.checked) {
                      setSelectedInventoryOrderIds((current) => [
                        ...new Set([...current, ...visibleIds]),
                      ]);
                    } else {
                      const drop = new Set(visibleIds);
                      setSelectedInventoryOrderIds((current) =>
                        current.filter((id) => !drop.has(id)),
                      );
                    }
                  }}
                />
                全选当前列表
              </label>
              <span className="muted">
                列表已选{" "}
                {
                  filteredInventoryGroups.filter(([orderId]) =>
                    selectedInventoryOrderIds.includes(orderId),
                  ).length
                }{" "}
                / {filteredInventoryGroups.length}
                {selectedInventoryOrderIds.length >
                filteredInventoryGroups.filter(([orderId]) =>
                  selectedInventoryOrderIds.includes(orderId),
                ).length
                  ? ` · 合计勾选 ${selectedInventoryOrderIds.length}`
                  : ""}
              </span>
              <button
                type="button"
                className="btn"
                onClick={() => setSelectedInventoryOrderIds([])}
              >
                清空勾选
              </button>
            </div>
          )}
          <div className="item-pick">
            {filteredInventoryGroups.length === 0 ? (
              <div className="empty">
                {stockLines.length === 0
                  ? "暂无在库货品"
                  : "当前筛选下没有订单"}
              </div>
            ) : (
              filteredInventoryGroups.map(([orderId, group]) => {
                const box = stockBoxByOrderId.get(orderId);
                const expanded = expandedInventoryOrderIds.includes(orderId);
                const selected = selectedInventoryOrderIds.includes(orderId);
                const missingCount = group.lines.filter(
                  (line) => !(line.barcode || "").trim(),
                ).length;
                const shopSummary = (() => {
                  const seen = new Set<string>();
                  const shops: string[] = [];
                  for (const line of group.lines) {
                    const shop = (line.shop || "").trim();
                    if (!shop || seen.has(shop)) continue;
                    seen.add(shop);
                    shops.push(shop);
                  }
                  return shops;
                })();
                const ipSummary = (() => {
                  const seen = new Set<string>();
                  const ips: string[] = [];
                  for (const line of group.lines) {
                    const ip = (line.ip || "").trim();
                    if (!ip || seen.has(ip)) continue;
                    seen.add(ip);
                    ips.push(ip);
                  }
                  return ips;
                })();
                return (
                  <div className="order-sub" key={orderId}>
                    <div className="order-sub-head">
                      <div className="order-sub-check">
                        <label className="order-check">
                          <input
                            type="checkbox"
                            checked={selected}
                            onChange={() => toggleInventoryOrderSelected(orderId)}
                          />
                        </label>
                        <button
                          type="button"
                          className="order-ref-btn mono"
                          onClick={() => toggleInventoryOrderExpanded(orderId)}
                        >
                          {group.orderRef}
                        </button>
                        <span className="muted"> · {group.lines.length} 行</span>
                        {shopSummary.length > 0 && (
                          <span
                            className="muted ellipsis inventory-meta"
                            title={shopSummary.join(" / ")}
                          >
                            {" "}
                            · {shopSummary.join(" / ")}
                          </span>
                        )}
                        {ipSummary.length > 0 && (
                          <span
                            className="muted ellipsis inventory-meta"
                            title={ipSummary.join(" / ")}
                          >
                            {" "}
                            · IP {ipSummary.join(" / ")}
                          </span>
                        )}
                        {missingCount > 0 && (
                          <span className="badge warn-badge">
                            {missingCount} 件无条码
                          </span>
                        )}
                        {box ? (
                          <span className="badge in_stock">
                            {box.parent_box_no != null
                              ? `子箱 #${box.box_no}→主箱 #${box.parent_box_no}`
                              : (box.child_boxes?.length ?? 0) > 0
                                ? `主箱 #${box.box_no}`
                                : `库存箱 #${box.box_no}`}
                            {box.note ? ` · ${box.note}` : ""}
                          </span>
                        ) : (
                          <span className="muted"> · 未合箱</span>
                        )}
                      </div>
                      <span className="order-row-actions">
                        {box && (
                          <button
                            type="button"
                            className="btn"
                            onClick={() =>
                              void onRemoveInventoryOrder(box.id, orderId)
                            }
                          >
                            移出合箱
                          </button>
                        )}
                        <button
                          type="button"
                          className="btn"
                          onClick={() => toggleInventoryOrderExpanded(orderId)}
                        >
                          {expanded ? "收起" : "明细"}
                        </button>
                      </span>
                    </div>
                    {expanded &&
                      group.lines.map((line) => (
                        <div
                          className={`order-line-compact${!(line.barcode || "").trim() ? " missing-barcode" : ""}`}
                          key={line.id}
                        >
                          {line.image_url ? (
                            <img
                              src={line.image_url}
                              className="thumb-sm"
                              alt=""
                              referrerPolicy="no-referrer"
                            />
                          ) : (
                            <span className="thumb-sm placeholder" />
                          )}
                          <span
                            className="line-name-cell"
                            title={
                              line.product_kind
                                ? `${line.product_kind} · ${line.name}`
                                : line.name
                            }
                          >
                            <KindSelect
                              value={line.product_kind || ""}
                              options={productKinds}
                              onSave={(product_kind) =>
                                void onUpdateLine(line.id, { product_kind })
                              }
                            />
                            <span className="ellipsis">{line.name}</span>
                          </span>
                          <span className="muted">x{line.qty}</span>
                          <BarcodeInput
                            value={line.barcode || ""}
                            onSave={(barcode) =>
                              void onUpdateLine(line.id, { barcode })
                            }
                          />
                        </div>
                      ))}
                  </div>
                );
              })
            )}
          </div>
        </section>
      )}

      {tab === "outbound" && (
        <section className="panel">
          <p className="muted">勾选任一行会自动选择该订单全部在库行。一个批次可有多个箱子，每箱可混装多个订单。出库必须登记条形码；特殊情况可勾选并备注。</p>
          {missingBarcodeLines.length > 0 && (
            <div className="warn-banner">
              在库中有 {missingBarcodeLines.length} 件未登记条形码；装箱出库前请补齐，或使用下方特殊情况放行。
            </div>
          )}
          <h2>1. 选择完整订单</h2>
          <div className="item-pick">
            {stockLines.length === 0 ? (
              <div className="empty">没有可出库的在库货品</div>
            ) : (
              groupLines(stockLines).map(([orderId, group]) => {
                const selectableIds = group.lines
                  .map((line) => line.id)
                  .filter((id) => !assignedIds.has(id));
                const orderChecked =
                  selectableIds.length > 0 &&
                  selectableIds.every((id) => selectedStockIds.includes(id));
                const allAssigned = selectableIds.length === 0;
                const expanded = expandedOutboundOrderIds.includes(orderId);
                const missingCount = group.lines.filter(
                  (line) => !(line.barcode || "").trim(),
                ).length;
                return (
                  <div className="order-sub" key={orderId}>
                    <div className="order-sub-head">
                      <div className="order-sub-check">
                        <label className="order-check">
                          <input
                            type="checkbox"
                            disabled={allAssigned}
                            checked={orderChecked || allAssigned}
                            onChange={() => toggleStockOrder(group.lines[0])}
                          />
                        </label>
                        <button
                          type="button"
                          className="order-ref-btn mono"
                          onClick={() => toggleOutboundOrderExpanded(orderId)}
                        >
                          {group.orderRef}
                        </button>
                        <span className="muted"> · {group.lines.length} 行</span>
                        {missingCount > 0 && (
                          <span className="badge warn-badge">
                            {missingCount} 件无条码
                          </span>
                        )}
                        {stockBoxByOrderId.get(orderId) && (
                          <span className="badge in_stock">
                            库存箱 #{stockBoxByOrderId.get(orderId)!.box_no}
                          </span>
                        )}
                      </div>
                      <button
                        type="button"
                        className="btn"
                        onClick={() => toggleOutboundOrderExpanded(orderId)}
                      >
                        {expanded ? "收起" : "明细"}
                      </button>
                    </div>
                    {expanded &&
                      group.lines.map((line) => (
                        <label
                          key={line.id}
                          className={
                            assignedIds.has(line.id) ? "source-disabled" : ""
                          }
                        >
                          <input
                            type="checkbox"
                            disabled={assignedIds.has(line.id)}
                            checked={
                              selectedStockIds.includes(line.id) ||
                              assignedIds.has(line.id)
                            }
                            onChange={() => toggleStockOrder(line)}
                          />
                          {line.image_url ? (
                            <img
                              className="thumb"
                              src={line.image_url}
                              alt=""
                              referrerPolicy="no-referrer"
                            />
                          ) : (
                            <span className="thumb placeholder" />
                          )}
                          <span>
                            {line.name}
                            <span className="muted">
                              {" "}
                              · x{line.qty}
                              {assignedIds.has(line.id) ? " · 已分箱" : ""}
                              {!(line.barcode || "").trim() ? " · 无条码" : ""}
                            </span>
                          </span>
                        </label>
                      ))}
                  </div>
                );
              })
            )}
          </div>
          <div className="toolbar">
            <button type="button" className="btn btn-primary" onClick={addDraftBox}>
              把已选行分配到新箱（{selectedStockIds.length}）
            </button>
            <button type="button" className="btn" onClick={applyStockBoxSuggestions}>
              按合箱建议分箱
            </button>
          </div>

          <h2>2. 编辑箱子</h2>
          {draftBoxes.length === 0 ? (
            <div className="empty">尚未创建箱子</div>
          ) : (
            draftBoxes.map((box, index) => {
              const lines = stockLines.filter((line) =>
                box.item_ids.includes(line.id),
              );
              const orderGroups = groupLines(lines);
              const missingCount = lines.filter(
                (line) => !(line.barcode || "").trim(),
              ).length;
              const boxExpanded = expandedDraftBoxUids.includes(box.uid);
              return (
                <article className="box-card" key={box.uid}>
                  <div className="order-sub-head draft-box-head">
                    <button
                      type="button"
                      className="order-ref-btn"
                      onClick={() => toggleDraftBoxExpanded(box.uid)}
                    >
                      箱 {box.box_no}
                    </button>
                    <span className="muted">
                      {" "}
                      · {CARRIER_LABEL[box.carrier]}
                      {box.tracking_no.trim()
                        ? ` · ${box.tracking_no.trim()}`
                        : " · 未填单号"}
                      {" · "}
                      {orderGroups.length} 单 · {lines.length} 行
                    </span>
                    {missingCount > 0 && (
                      <span className="badge warn-badge">
                        {missingCount} 件无条码
                      </span>
                    )}
                    <button
                      type="button"
                      className="btn"
                      onClick={() => toggleDraftBoxExpanded(box.uid)}
                    >
                      {boxExpanded ? "收起" : "明细"}
                    </button>
                  </div>
                  {boxExpanded && (
                    <>
                      <div className="form-grid">
                        <label>
                          箱号
                          <input
                            type="number"
                            min={1}
                            value={box.box_no}
                            onChange={(e) =>
                              updateDraftBox(index, {
                                box_no: Number(e.target.value) || 1,
                              })
                            }
                          />
                        </label>
                        <CarrierSelect
                          value={box.carrier}
                          onChange={(value) =>
                            updateDraftBox(index, { carrier: value })
                          }
                        />
                        <label>
                          快递单号 *
                          <input
                            value={box.tracking_no}
                            onChange={(e) =>
                              updateDraftBox(index, {
                                tracking_no: e.target.value,
                              })
                            }
                          />
                        </label>
                      </div>
                      {orderGroups.map(([orderId, group]) => {
                        const orderKey = `${box.uid}:${orderId}`;
                        const orderExpanded =
                          expandedDraftOrderKeys.includes(orderKey);
                        const orderMissing = group.lines.filter(
                          (line) => !(line.barcode || "").trim(),
                        ).length;
                        return (
                          <div className="order-sub" key={orderId}>
                            <div className="order-sub-head">
                              <div className="order-sub-check">
                                <button
                                  type="button"
                                  className="order-ref-btn mono"
                                  onClick={() =>
                                    toggleDraftOrderExpanded(box.uid, orderId)
                                  }
                                >
                                  {group.orderRef}
                                </button>
                                <span className="muted">
                                  {" "}
                                  · {group.lines.length} 行
                                </span>
                                {orderMissing > 0 && (
                                  <span className="badge warn-badge">
                                    {orderMissing} 件无条码
                                  </span>
                                )}
                              </div>
                              <button
                                type="button"
                                className="btn"
                                onClick={() =>
                                  toggleDraftOrderExpanded(box.uid, orderId)
                                }
                              >
                                {orderExpanded ? "收起" : "明细"}
                              </button>
                            </div>
                            {orderExpanded && (
                              <ul>
                                {group.lines.map((line) => (
                                  <li key={line.id}>
                                    {line.name} · x{line.qty}
                                    {!(line.barcode || "").trim() && (
                                      <span className="warn-text">
                                        {" "}
                                        · 无条码
                                      </span>
                                    )}{" "}
                                    <BarcodeInput
                                      value={line.barcode || ""}
                                      onSave={(barcode) =>
                                        void onUpdateLine(line.id, { barcode })
                                      }
                                    />{" "}
                                    <button
                                      type="button"
                                      className="btn btn-danger"
                                      onClick={() =>
                                        removeDraftLine(index, line.id)
                                      }
                                    >
                                      移出
                                    </button>
                                  </li>
                                ))}
                              </ul>
                            )}
                          </div>
                        );
                      })}
                    </>
                  )}
                </article>
              );
            })
          )}
          {draftMissingBarcodeLines.length > 0 && (
            <div className="warn-banner">
              当前装箱中有 {draftMissingBarcodeLines.length} 行未登记条形码，创建批次前须补齐，或勾选特殊情况并备注。
            </div>
          )}
          <label className="inline-filter">
            批次备注
            <input
              value={batchNote}
              onChange={(e) => setBatchNote(e.target.value)}
            />
          </label>
          <div className="form-grid">
            <label>
              运费汇率（国际）
              <input
                type="number"
                min={0}
                step="0.0001"
                value={freightExchangeRate}
                placeholder="可后补"
                onChange={(e) => setFreightExchangeRate(e.target.value)}
              />
            </label>
            <label>
              运费单价（JPY）
              <input
                type="number"
                min={0}
                step="1"
                value={freightUnitPrice}
                placeholder="可后补"
                onChange={(e) => setFreightUnitPrice(e.target.value)}
              />
            </label>
            <label>
              计费重量
              <input
                type="number"
                min={0}
                step="0.01"
                value={chargeableWeight}
                placeholder="可后补"
                onChange={(e) => setChargeableWeight(e.target.value)}
              />
            </label>
          </div>
          <label className="inline-check">
            <input
              type="checkbox"
              checked={outboundAllowMissingBarcode}
              onChange={(e) => setOutboundAllowMissingBarcode(e.target.checked)}
            />
            特殊情况：允许无条形码出库
          </label>
          {outboundAllowMissingBarcode && (
            <label className="inline-filter">
              特殊情况备注 *
              <input
                value={outboundMissingBarcodeNote}
                placeholder="说明为何无条码仍出库"
                onChange={(e) => setOutboundMissingBarcodeNote(e.target.value)}
              />
            </label>
          )}
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => void onCreateOutbound()}
          >
            创建出库批次（{draftBoxes.length} 箱）
          </button>

          <h2>已有出库批次</h2>
          {batches.length === 0 ? <div className="empty">暂无出库批次</div> : batches.map((batch) => (
            <article className="ship-card" key={batch.id}>
              <header>
                <div>
                  <strong>批次 #{batch.id}</strong>
                  <span className="muted">
                    {" "}
                    · {batch.box_count} 箱 · {batch.item_count} 行 ·{" "}
                    {formatDate(batch.created_at)}
                  </span>
                  <span className={`badge ${batch.payment_status}`}>
                    {PAYMENT_LABEL[batch.payment_status] || batch.payment_status}
                  </span>
                  {batch.note && <div>{batch.note}</div>}
                  <div className="muted">
                    货款CNY {moneyText(batch.goods_receivable_cny)} · 运费CNY{" "}
                    {moneyText(batch.freight_cny)} · 应收{" "}
                    {moneyText(batch.amount_receivable_cny)} · 已收{" "}
                    {moneyText(batch.amount_received_cny, "0")} · 未收{" "}
                    {moneyText(batch.amount_unreceived_cny)}
                  </div>
                </div>
                <div className="toolbar">
                  <button
                    type="button"
                    className="btn"
                    onClick={() =>
                      void downloadOutboundFeeDetail(batch.id).catch((err) =>
                        setError(errorText(err)),
                      )
                    }
                  >
                    费用明细 Excel
                  </button>
                  {batch.boxes.some((box) => box.status === "shipped") && (
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => void onConfirmBatch(batch.id)}
                    >
                      确认整批签收
                    </button>
                  )}
                </div>
              </header>
              <form
                className="form-grid"
                onSubmit={(e) => {
                  e.preventDefault();
                  void onSaveBatchFreight(batch, e.currentTarget);
                }}
              >
                <label>
                  运费汇率
                  <input
                    name="freight_rate"
                    type="number"
                    min={0}
                    step="0.0001"
                    defaultValue={batch.freight_exchange_rate ?? ""}
                  />
                </label>
                <label>
                  运费单价JPY
                  <input
                    name="freight_unit"
                    type="number"
                    min={0}
                    step="1"
                    defaultValue={batch.freight_unit_price_jpy ?? ""}
                  />
                </label>
                <label>
                  计费重量
                  <input
                    name="freight_weight"
                    type="number"
                    min={0}
                    step="0.01"
                    defaultValue={batch.chargeable_weight ?? ""}
                  />
                </label>
                <label className="full">
                  <button type="submit" className="btn">
                    保存国际运费
                  </button>
                </label>
              </form>
              <div className="toolbar">
                <label className="inline-filter">
                  已收款（CNY）
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    value={batchReceivedDraft[batch.id] ?? "0"}
                    onChange={(e) =>
                      setBatchReceivedDraft((current) => ({
                        ...current,
                        [batch.id]: e.target.value,
                      }))
                    }
                  />
                </label>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => void onSaveBatchReceived(batch)}
                >
                  登记收款
                </button>
              </div>
              {batch.boxes.map((box) => (
                <div className="box-card" key={box.id}>
                  <strong>箱 {box.box_no}</strong> · {CARRIER_LABEL[box.carrier]} · <span className="mono">{box.tracking_no}</span> · <span className={`badge ${box.status === "delivered" ? "delivered" : "outbound_shipped"}`}>{box.status === "delivered" ? "已签收" : "运输中"}</span>
                  <OrderGroups groups={box.order_groups} fallback={box.items} />
                </div>
              ))}
            </article>
          ))}
        </section>
      )}

      {tab === "logs" && (
        <section className="panel">
          <p className="muted">仅可撤回最近一步且尚未被后续状态变更影响的操作。</p>
          {logs.length === 0 ? <div className="empty">暂无操作日志</div> : (
            <div className="table-wrap"><table><thead><tr><th>时间</th><th>操作</th><th>状态</th><th /></tr></thead><tbody>
              {logs.map((log) => <tr key={log.id}><td className="muted">{formatDate(log.created_at)}</td><td>{log.summary}</td><td>{log.undone_at ? <span className="badge cancelled">已撤回</span> : log.undoable && latestLog?.id === log.id ? <span className="badge in_stock">可撤回</span> : "—"}</td><td>{log.undoable && latestLog?.id === log.id && <button type="button" className="btn" disabled={undoBusy} onClick={() => void onUndo(log.id)}>撤回</button>}</td></tr>)}
            </tbody></table></div>
          )}
        </section>
      )}
    </div>
  );
}

function OrderCard({
  order,
  selected,
  expanded,
  onToggleSelect,
  onToggleExpand,
  onEnsureExpanded,
  onBarcode,
  onQty,
  onProductKind,
  onCancelLine,
  onShippingFee,
  onExchangeRate,
  onOrderRef,
  productKinds,
}: {
  order: Order;
  selected: boolean;
  expanded: boolean;
  onToggleSelect: () => void;
  onToggleExpand: () => void;
  onEnsureExpanded: () => void;
  onBarcode: (id: number, value: string) => void;
  onQty: (id: number, qty: number) => void;
  onProductKind: (id: number, product_kind: string) => void;
  onCancelLine: (id: number) => void;
  onShippingFee: (fee: number | null) => void;
  onExchangeRate: (rate: number | null) => void;
  onOrderRef: (orderRef: string) => void;
  productKinds: string[];
}) {
  const [editing, setEditing] = useState(false);
  const [feeDraft, setFeeDraft] = useState(
    order.shipping_fee != null ? String(order.shipping_fee) : "0",
  );
  const [rateDraft, setRateDraft] = useState(
    order.exchange_rate != null ? String(order.exchange_rate) : "",
  );
  const [refDraft, setRefDraft] = useState(order.order_ref || "");
  useEffect(() => {
    setFeeDraft(order.shipping_fee != null ? String(order.shipping_fee) : "0");
  }, [order.shipping_fee]);
  useEffect(() => {
    setRateDraft(order.exchange_rate != null ? String(order.exchange_rate) : "");
  }, [order.exchange_rate]);
  useEffect(() => {
    setRefDraft(order.order_ref || "");
  }, [order.order_ref]);

  const ipSummary = (() => {
    const ips: string[] = [];
    const seen = new Set<string>();
    for (const line of order.lines) {
      const ip = (line.ip || "").trim();
      if (!ip || seen.has(ip)) continue;
      seen.add(ip);
      ips.push(ip);
    }
    return ips;
  })();

  function commitFee() {
    const text = feeDraft.trim();
    const next = text === "" ? 0 : Number(text);
    const normalized = Number.isNaN(next) ? 0 : Math.max(0, next);
    const prev = order.shipping_fee ?? 0;
    if (normalized !== prev) onShippingFee(normalized);
  }

  function commitRate() {
    const text = rateDraft.trim();
    if (!text) {
      if (order.exchange_rate != null) onExchangeRate(null);
      return;
    }
    const next = Number(text);
    if (Number.isNaN(next) || next <= 0) return;
    if (next !== order.exchange_rate) onExchangeRate(next);
  }

  function commitOrderRef() {
    const next = refDraft.trim();
    if (next !== (order.order_ref || "")) onOrderRef(next);
  }

  function startEditing() {
    setRefDraft(order.order_ref || "");
    setFeeDraft(
      order.shipping_fee != null ? String(order.shipping_fee) : "0",
    );
    setRateDraft(
      order.exchange_rate != null ? String(order.exchange_rate) : "",
    );
    setEditing(true);
    onEnsureExpanded();
  }

  function finishEditing() {
    commitOrderRef();
    commitFee();
    commitRate();
    setEditing(false);
  }

  return (
    <article
      className={`order-row${selected ? " selected" : ""}${editing ? " editing" : ""}`}
    >
      <div className="order-row-main">
        <label className="order-check">
          <input type="checkbox" checked={selected} onChange={onToggleSelect} />
        </label>
        {editing ? (
          <label className="order-ref-inline order-cell-ref">
            <input
              className="mono"
              value={refDraft}
              placeholder={`#${order.id}`}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => setRefDraft(e.target.value)}
              onBlur={commitOrderRef}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  (e.target as HTMLInputElement).blur();
                }
              }}
            />
          </label>
        ) : (
          <button
            type="button"
            className="order-ref-btn mono order-cell-ref"
            onClick={onToggleExpand}
          >
            {order.order_ref || `#${order.id}`}
          </button>
        )}
        <span className={`badge ${order.status} order-cell-status`}>
          {STATUS_LABEL[order.status]}
        </span>
        <span className="ellipsis order-cell-shop" title={order.shop || ""}>
          {order.shop || "—"}
        </span>
        <span
          className="ellipsis order-cell-ip"
          title={ipSummary.join(" / ") || "—"}
        >
          {ipSummary.length ? ipSummary.join(" / ") : "—"}
          <span className="muted">
            {" "}
            · {order.line_count}行/{order.total_qty}件
          </span>
        </span>
        {editing ? (
          <label className="order-fee-inline order-cell-rate">
            <input
              type="number"
              min={0}
              step="0.0001"
              value={rateDraft}
              placeholder="—"
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => setRateDraft(e.target.value)}
              onBlur={commitRate}
            />
          </label>
        ) : (
          <span className="order-cell-rate">
            {order.exchange_rate != null ? order.exchange_rate : "—"}
          </span>
        )}
        <span className="order-cell-goods">
          {order.goods_total != null ? order.goods_total : "—"}
          {order.goods_total_cny != null && (
            <span className="muted block-mini">¥{order.goods_total_cny}</span>
          )}
        </span>
        {editing ? (
          <label className="order-fee-inline order-cell-fee">
            <input
              type="number"
              min={0}
              step="1"
              value={feeDraft}
              placeholder="—"
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => setFeeDraft(e.target.value)}
              onBlur={commitFee}
            />
          </label>
        ) : (
          <span className="order-cell-fee">
            {order.shipping_fee != null ? order.shipping_fee : 0}
            {order.shipping_fee_cny != null && (
              <span className="muted block-mini">¥{order.shipping_fee_cny}</span>
            )}
          </span>
        )}
        <span className="strong order-cell-total">
          {order.order_total != null ? order.order_total : "—"}
          {order.order_total_cny != null && (
            <span className="muted block-mini">¥{order.order_total_cny}</span>
          )}
        </span>
        <span className="ellipsis order-cell-ship">
          {order.expected_ship_at
            ? formatExpectedShip(order.expected_ship_at, order.expected_ship_period)
            : "—"}
        </span>
        <span className="order-row-actions">
          {editing ? (
            <button type="button" className="btn btn-primary" onClick={finishEditing}>
              完成
            </button>
          ) : (
            <button type="button" className="btn" onClick={startEditing}>
              编辑
            </button>
          )}
          <button type="button" className="btn" onClick={onToggleExpand}>
            {expanded ? "收起" : "明细"}
          </button>
        </span>
      </div>
      {expanded && (
        <div className="order-row-detail">
          <div className="order-detail-meta">
            {order.order_image_url && (
              <a href={order.order_image_url} target="_blank" rel="noreferrer" className="order-shot-mini-link">
                <img className="order-shot-mini" src={order.order_image_url} alt="订单截图" referrerPolicy="no-referrer" />
              </a>
            )}
            {order.note && <span className="muted">备注：{order.note}</span>}
            {!editing && (
              <span className="muted">点「编辑」后可改订单号 / 汇率 / 运费 / 数量 / 条码</span>
            )}
          </div>
          {order.lines.map((line) => (
            <div className="order-line-compact" key={line.id}>
              {line.image_url ? (
                <img src={line.image_url} className="thumb-sm" alt="" referrerPolicy="no-referrer" />
              ) : (
                <span className="thumb-sm placeholder" />
              )}
              <span
                className="line-name-cell"
                title={
                  line.product_kind
                    ? `${line.product_kind} · ${line.name}`
                    : line.name
                }
              >
                <KindSelect
                  value={line.product_kind || ""}
                  options={productKinds}
                  onSave={(product_kind) => onProductKind(line.id, product_kind)}
                />
                <span className="ellipsis">{line.name}</span>
              </span>
              {editing ? (
                <QtyInput value={line.qty} onSave={(qty) => onQty(line.id, qty)} />
              ) : (
                <span>x{line.qty}</span>
              )}
              <span>{line.unit_cost != null ? `¥${line.unit_cost}` : "—"}</span>
              <span className="ellipsis">{line.ip || "—"}</span>
              <span className={`badge ${line.status}`}>{STATUS_LABEL[line.status]}</span>
              <BarcodeInput
                value={line.barcode || ""}
                editable={editing}
                onSave={(value) => onBarcode(line.id, value)}
              />
              {line.source_url ? (
                <a className="link" href={line.source_url} target="_blank" rel="noreferrer">链接</a>
              ) : (
                <span />
              )}
              {editing &&
              line.status !== "cancelled" &&
              line.status !== "delivered" ? (
                <button type="button" className="btn btn-danger" onClick={() => onCancelLine(line.id)}>
                  取消行
                </button>
              ) : (
                <span />
              )}
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

function CarrierSelect({
  value,
  onChange,
}: {
  value: Carrier;
  onChange: (value: Carrier) => void;
}) {
  return (
    <label>
      承运商
      <select value={value} onChange={(e) => onChange(e.target.value as Carrier)}>
        <option value="yamato">Yamato</option>
        <option value="sagawa">佐川急便</option>
        <option value="other">其他</option>
      </select>
    </label>
  );
}

function KindSelect({
  value,
  options,
  onSave,
}: {
  value: string;
  options: string[];
  onSave: (kind: string) => void;
}) {
  const choices = useMemo(() => {
    const set = new Set(options);
    if (value && !set.has(value)) set.add(value);
    return Array.from(set);
  }, [options, value]);

  return (
    <select
      className="kind-select"
      title="商品种类"
      value={value}
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => {
        const next = e.target.value;
        if (next !== value) onSave(next);
      }}
    >
      <option value="">种类</option>
      {choices.map((kind) => (
        <option key={kind} value={kind}>
          {kind}
        </option>
      ))}
    </select>
  );
}

function QtyInput({
  value,
  onSave,
}: {
  value: number;
  onSave: (qty: number) => void;
}) {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => setDraft(String(value)), [value]);
  return (
    <input
      className="cell-qty"
      type="number"
      min={1}
      step={1}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        const next = Math.max(1, Math.floor(Number(draft) || 1));
        setDraft(String(next));
        if (next !== value) onSave(next);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          (e.target as HTMLInputElement).blur();
        }
      }}
    />
  );
}

function BarcodeInput({
  value,
  onSave,
  editable = true,
}: {
  value: string;
  onSave: (value: string) => void;
  editable?: boolean;
}) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  return (
    <input
      className={`cell-barcode${editable ? "" : " readonly"}`}
      placeholder={editable ? "到货后补条形码" : "—"}
      value={draft}
      readOnly={!editable}
      disabled={!editable}
      onChange={(e) => {
        if (!editable) return;
        setDraft(e.target.value);
      }}
      onBlur={() => {
        if (!editable) return;
        if (draft.trim() !== value) onSave(draft.trim());
      }}
    />
  );
}

function OrderGroups({
  groups,
  fallback,
  barcode,
}: {
  groups?: { order_id: number | null; order_ref: string; items: Shipment["items"] }[];
  fallback: Shipment["items"];
  barcode?: (id: number, value: string) => void;
}) {
  const normalized = groups?.length
    ? groups
    : [{ order_id: null, order_ref: "未分组订单", items: fallback }];
  return (
    <>
      {normalized.map((group, index) => (
        <div className="order-sub" key={`${group.order_id ?? "none"}-${index}`}>
          <strong>{group.order_ref || "无订单号"}</strong>
          <ul className={barcode ? "ship-items" : undefined}>
            {group.items.map((item) => (
              <li key={item.id}>
                <span>{item.name}<span className="muted"> · {item.shop || "无店铺"} · x{item.qty}</span></span>
                {barcode && <BarcodeInput value={item.barcode || ""} onSave={(value) => barcode(item.id, value)} />}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </>
  );
}
