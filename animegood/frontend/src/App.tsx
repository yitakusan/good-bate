import { useEffect, useMemo, useState } from "react";
import {
  addItem,
  clearCart,
  exportCartBase64,
  getCartCount,
  loadCart,
  mergeCartItems,
  parseCartImport,
  removeItem,
  saveCart,
  updateQuantity,
  type CartItem,
} from "./cart";
import { ExchangeRateWidget } from "./ExchangeRateWidget";
import { HeroEvents, type HeroEvent } from "./HeroEvents";
import {
  adminHeaders,
  formatCnyEstimate,
  loadAdminToken,
  saveAdminToken,
} from "./adminAuth";
import {
  applyProductRefresh,
  exportWishlistBase64,
  loadWishlist,
  mergeWishlistItems,
  parseWishlistImport,
  saveWishlist,
  toWishlistItem,
  toggleWishlist,
  type WishlistItem,
} from "./wishlist";

type Product = {
  id: number;
  product_name: string;
  display_name_zh?: string | null;
  series?: string;
  ip: string;
  shop: string;
  source_url: string;
  price: number | null;
  stock_status: string;
  release_date: string | null;
  preorder_date: string | null;
  image_url: string | null;
  first_seen: string;
  source_platform: string;
  favorite_count: number;
};

type FilterOptions = {
  ips: string[];
  shops: string[];
  release_months: string[];
  series: string[];
};

type SourceRegistryItem = {
  id: string;
  shop: string;
  base_url: string;
  source_platform: string;
  enabled: boolean;
  inclusion_status: string;
  difficulty: string;
  priority: number;
  core_ips: string[];
  notes: string | null;
  product_count: number;
  last_run_status: string | null;
  last_run_at: string | null;
  last_run_message: string | null;
};

type SourceRegistry = {
  items: SourceRegistryItem[];
  included_count: number;
  excluded_count: number;
  easy_pending_count: number;
};

type RegistryFilter = "全部" | "已收录" | "未收录" | "易抓待接入";

type ScrapeStepStatus = "pending" | "running" | "success" | "failed";

type ScrapeStep = {
  sourceId: string;
  shop: string;
  status: ScrapeStepStatus;
  stored: number;
  message?: string;
};

type ScrapeSourceResult = {
  source_id: string;
  status: string;
  stored: number;
  skipped?: number;
  message?: string;
};

const emptyFilters: FilterOptions = {
  ips: [],
  shops: [],
  release_months: [],
  series: [],
};

const SCRAPE_CONCURRENCY = 3;
const PAGE_SIZE = 40;
const SEARCH_DEBOUNCE_MS = 300;

function wishlistToProduct(item: WishlistItem, fallback?: Product): Product {
  return {
    id: item.id,
    product_name: item.product_name,
    display_name_zh: item.display_name_zh ?? null,
    series: fallback?.series ?? "",
    ip: item.ip,
    shop: item.shop,
    source_url: item.source_url,
    price: item.price,
    stock_status: item.stock_status,
    release_date: item.release_date,
    image_url: item.image_url,
    favorite_count: fallback?.favorite_count ?? 0,
    first_seen: fallback?.first_seen ?? "",
    source_platform: fallback?.source_platform ?? "",
    preorder_date: fallback?.preorder_date ?? null,
  };
}

function App() {
  const [products, setProducts] = useState<Product[]>([]);
  const [productTotal, setProductTotal] = useState(0);
  const [filters, setFilters] = useState<FilterOptions>(emptyFilters);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [selectedIp, setSelectedIp] = useState("");
  const [selectedShop, setSelectedShop] = useState("");
  const [selectedSeries, setSelectedSeries] = useState("");
  const [selectedMonth, setSelectedMonth] = useState("");
  const [adminToken, setAdminToken] = useState(() => loadAdminToken());
  const [authRequired, setAuthRequired] = useState(false);
  const [scrapeIntervalHours, setScrapeIntervalHours] = useState(0);
  const [cnyPer100Jpy, setCnyPer100Jpy] = useState<number | null>(null);
  const [devToolsOpen, setDevToolsOpen] = useState(false);
  const [registry, setRegistry] = useState<SourceRegistry | null>(null);
  const [registryFilter, setRegistryFilter] = useState<RegistryFilter>("全部");
  const [registryOpen, setRegistryOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMoreProducts, setHasMoreProducts] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scrapeLimit, setScrapeLimit] = useState("20");
  const [scrapeIncremental, setScrapeIncremental] = useState(true);
  const [selectedScrapeIds, setSelectedScrapeIds] = useState<string[]>([]);
  const [isScraping, setIsScraping] = useState(false);
  const [scrapingSourceId, setScrapingSourceId] = useState<string | null>(null);
  const [scrapeMessage, setScrapeMessage] = useState<string | null>(null);
  const [scrapeError, setScrapeError] = useState(false);
  const [scrapeSteps, setScrapeSteps] = useState<ScrapeStep[]>([]);
  const [refreshToken, setRefreshToken] = useState(0);
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
  const [clearToken, setClearToken] = useState<string | null>(null);
  const [clearCountdown, setClearCountdown] = useState<number | null>(null);
  const [isPreparingClear, setIsPreparingClear] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [clearMessage, setClearMessage] = useState<string | null>(null);
  const [clearError, setClearError] = useState(false);
  const [availableOnly, setAvailableOnly] = useState(false);
  const [sort, setSort] = useState("newest");
  const [view, setView] = useState<"discover" | "wishlist" | "cart">("discover");
  const [wishlist, setWishlist] = useState<WishlistItem[]>(() => loadWishlist());
  const [wishlistProducts, setWishlistProducts] = useState<Product[]>([]);
  const [cart, setCart] = useState<CartItem[]>(() => loadCart());
  const [detailProduct, setDetailProduct] = useState<Product | null>(null);
  const [compareProducts, setCompareProducts] = useState<Product[]>([]);
  const [seriesProducts, setSeriesProducts] = useState<Product[]>([]);
  const [events, setEvents] = useState<HeroEvent[]>([]);

  useEffect(() => {
    saveWishlist(wishlist);
  }, [wishlist]);

  useEffect(() => {
    saveCart(cart);
  }, [cart]);

  useEffect(() => {
    saveAdminToken(adminToken);
  }, [adminToken]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearch(search);
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    let cancelled = false;
    async function loadAdminStatus() {
      try {
        const response = await fetch("/api/admin/status");
        if (!response.ok || cancelled) return;
        const payload = (await response.json()) as {
          auth_required: boolean;
          scrape_interval_hours: number;
        };
        if (!cancelled) {
          setAuthRequired(Boolean(payload.auth_required));
          setScrapeIntervalHours(Number(payload.scrape_interval_hours) || 0);
        }
      } catch {
        // ignore
      }
    }
    async function loadRate() {
      try {
        const response = await fetch("/api/exchange-rate", { cache: "no-store" });
        if (!response.ok || cancelled) return;
        const payload = (await response.json()) as { cny_per_100_jpy: number };
        if (!cancelled && typeof payload.cny_per_100_jpy === "number") {
          setCnyPer100Jpy(payload.cny_per_100_jpy);
        }
      } catch {
        // ignore
      }
    }
    void loadAdminStatus();
    void loadRate();
    return () => {
      cancelled = true;
    };
  }, [refreshToken]);

  function adminFetchInit(init: RequestInit = {}): RequestInit {
    return {
      ...init,
      headers: {
        ...(init.headers ?? {}),
        ...adminHeaders(adminToken),
      },
    };
  }

  function clearAllFilters() {
    setSearch("");
    setDebouncedSearch("");
    setSelectedIp("");
    setSelectedShop("");
    setSelectedSeries("");
    setSelectedMonth("");
    setAvailableOnly(false);
    setSort("newest");
  }

  const activeFilterChips = useMemo(() => {
    const chips: { key: string; label: string; clear: () => void }[] = [];
    if (debouncedSearch.trim()) {
      chips.push({
        key: "q",
        label: `搜索：${debouncedSearch.trim()}`,
        clear: () => {
          setSearch("");
          setDebouncedSearch("");
        },
      });
    }
    if (selectedIp) {
      chips.push({ key: "ip", label: `IP：${selectedIp}`, clear: () => setSelectedIp("") });
    }
    if (selectedShop) {
      chips.push({
        key: "shop",
        label: `店铺：${selectedShop}`,
        clear: () => setSelectedShop(""),
      });
    }
    if (selectedSeries) {
      chips.push({
        key: "series",
        label: `系列：${selectedSeries}`,
        clear: () => setSelectedSeries(""),
      });
    }
    if (selectedMonth) {
      chips.push({
        key: "month",
        label: `发售：${selectedMonth}`,
        clear: () => setSelectedMonth(""),
      });
    }
    if (availableOnly) {
      chips.push({
        key: "available",
        label: "仅可购买",
        clear: () => setAvailableOnly(false),
      });
    }
    return chips;
  }, [
    debouncedSearch,
    selectedIp,
    selectedShop,
    selectedSeries,
    selectedMonth,
    availableOnly,
  ]);

  const wishlistIds = useMemo(() => new Set(wishlist.map((item) => item.id)), [wishlist]);
  const cartCount = useMemo(() => getCartCount(cart), [cart]);
  const cartQuantities = useMemo(() => {
    const map = new Map<number, number>();
    for (const item of cart) {
      map.set(item.id, item.quantity);
    }
    return map;
  }, [cart]);

  function handleAddToCart(product: Product) {
    setCart((items) => addItem(items, product));
  }

  function bumpFavoriteCount(productId: number, delta: number) {
    const update = (items: Product[]) =>
      items.map((item) =>
        item.id === productId
          ? { ...item, favorite_count: Math.max(0, item.favorite_count + delta) }
          : item,
      );
    setProducts(update);
    setWishlistProducts(update);
    setCompareProducts(update);
    setDetailProduct((current) =>
      current && current.id === productId
        ? { ...current, favorite_count: Math.max(0, current.favorite_count + delta) }
        : current,
    );
  }

  async function handleToggleWishlist(product: Product) {
    const isSaved = wishlistIds.has(product.id);
    setWishlist((items) => toggleWishlist(items, toWishlistItem(product)));
    bumpFavoriteCount(product.id, isSaved ? -1 : 1);
    try {
      await fetch(`/api/products/${product.id}/favorite?delta=${isSaved ? -1 : 1}`, {
        method: "POST",
      });
    } catch {
      setWishlist((items) => toggleWishlist(items, toWishlistItem(product)));
      bumpFavoriteCount(product.id, isSaved ? 1 : -1);
    }
  }

  async function openDetail(product: Product) {
    setDetailProduct(product);
    setCompareProducts([]);
    setSeriesProducts([]);

    const tasks: Promise<void>[] = [];

    if (product.ip !== "未分类") {
      tasks.push(
        (async () => {
          try {
            const response = await fetch(
              `/api/products?ip=${encodeURIComponent(product.ip)}&limit=20&sort=price_asc`,
            );
            if (!response.ok) return;
            const payload = (await response.json()) as { items: Product[] };
            setCompareProducts(payload.items.filter((item) => item.id !== product.id));
          } catch {
            setCompareProducts([]);
          }
        })(),
      );
    }

    if (product.series) {
      tasks.push(
        (async () => {
          try {
            const params = new URLSearchParams({
              series: product.series!,
              limit: "24",
              sort: "price_asc",
            });
            if (product.shop) params.set("shop", product.shop);
            const response = await fetch(`/api/products?${params}`);
            if (!response.ok) return;
            const payload = (await response.json()) as { items: Product[] };
            let items = payload.items.filter((item) => item.id !== product.id);
            // 同店同系列过少时，放宽到全站同系列
            if (items.length < 2 && product.shop) {
              const allRes = await fetch(
                `/api/products?series=${encodeURIComponent(product.series!)}&limit=24&sort=price_asc`,
              );
              if (allRes.ok) {
                const allPayload = (await allRes.json()) as { items: Product[] };
                items = allPayload.items.filter((item) => item.id !== product.id);
              }
            }
            setSeriesProducts(items);
          } catch {
            setSeriesProducts([]);
          }
        })(),
      );
    }

    await Promise.all(tasks);
  }

  const filterQuery = useMemo(() => {
    const params = new URLSearchParams();
    if (debouncedSearch.trim()) params.set("q", debouncedSearch.trim());
    if (selectedIp) params.set("ip", selectedIp);
    if (selectedShop) params.set("shop", selectedShop);
    if (selectedSeries) params.set("series", selectedSeries);
    if (selectedMonth) params.set("release_month", selectedMonth);
    if (availableOnly) params.set("available_only", "true");
    if (sort !== "newest") params.set("sort", sort);
    return params.toString();
  }, [debouncedSearch, selectedIp, selectedShop, selectedSeries, selectedMonth, availableOnly, sort]);

  const spotlightIps = useMemo(
    () => filters.ips.filter((ip) => ip !== "未分类").slice(0, 10),
    [filters.ips],
  );

  const filteredRegistryItems = useMemo(() => {
    if (!registry) return [];
    if (registryFilter === "全部") return registry.items;
    if (registryFilter === "易抓待接入") {
      return registry.items.filter(
        (item) => item.inclusion_status === "未收录" && isEasyDifficulty(item.difficulty),
      );
    }
    return registry.items.filter((item) => item.inclusion_status === registryFilter);
  }, [registry, registryFilter]);

  const scrapeProgress = useMemo(() => {
    if (scrapeSteps.length === 0) {
      return null;
    }

    const total = scrapeSteps.length;
    const completed = scrapeSteps.filter(
      (step) => step.status === "success" || step.status === "failed",
    ).length;
    const runningSteps = scrapeSteps.filter((step) => step.status === "running");
    const percent = isScraping && runningSteps.length > 0
      ? Math.min(99, Math.round(((completed + runningSteps.length * 0.4) / total) * 100))
      : Math.round((completed / total) * 100);

    return {
      total,
      completed,
      percent: isScraping ? percent : completed === total ? 100 : percent,
      runningSteps,
    };
  }, [scrapeSteps, isScraping]);

  async function loadRegistrySnapshot(): Promise<SourceRegistry | null> {
    try {
      const response = await fetch("/api/source-registry");
      if (!response.ok) {
        return null;
      }
      return (await response.json()) as SourceRegistry;
    } catch {
      return null;
    }
  }

  function enabledSources(snapshot: SourceRegistry) {
    return [...snapshot.items]
      .filter((item) => item.enabled)
      .sort((left, right) => left.priority - right.priority || left.shop.localeCompare(right.shop, "zh-CN"));
  }

  async function scrapeSingleSource(sourceId: string, limitValue: number | null): Promise<ScrapeSourceResult> {
    const params = new URLSearchParams();
    if (limitValue !== null) {
      params.set("limit", String(limitValue));
    }
    if (scrapeIncremental) {
      params.set("incremental", "true");
    }
    const queryString = params.toString();
    const response = await fetch(
      `/api/scrape/run/${sourceId}${queryString ? `?${queryString}` : ""}`,
      adminFetchInit({ method: "POST" }),
    );

    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      const detail =
        payload && typeof payload.detail === "string"
          ? payload.detail
          : response.status === 401
            ? "需要管理口令：请在开发者工具填写与服务器 ANIMEGOOD_ADMIN_TOKEN 相同的口令"
            : `抓取失败（HTTP ${response.status}）`;
      throw new Error(detail);
    }

    return (await response.json()) as ScrapeSourceResult;
  }

  function updateScrapeStep(sourceId: string, patch: Partial<ScrapeStep>) {
    setScrapeSteps((steps) =>
      steps.map((step) => (step.sourceId === sourceId ? { ...step, ...patch } : step)),
    );
  }

  useEffect(() => {
    async function loadRegistry() {
      try {
        const response = await fetch("/api/source-registry");
        if (!response.ok) {
          return;
        }
        const payload = (await response.json()) as SourceRegistry;
        setRegistry(payload);
        setSelectedScrapeIds((current) => {
          const enabled = payload.items.filter((item) => item.enabled).map((item) => item.id);
          if (current.length === 0) {
            return enabled;
          }
          const enabledSet = new Set(enabled);
          const kept = current.filter((id) => enabledSet.has(id));
          return kept.length > 0 ? kept : enabled;
        });
      } catch {
        setRegistry(null);
      }
    }

    void loadRegistry();
  }, [refreshToken]);

  useEffect(() => {
    async function loadEvents() {
      try {
        const response = await fetch("/api/events?limit=10");
        if (!response.ok) {
          return;
        }
        const payload = (await response.json()) as { items: HeroEvent[] };
        setEvents(payload.items ?? []);
      } catch {
        setEvents([]);
      }
    }

    void loadEvents();
  }, [refreshToken]);

  function parseScrapeLimitValue(): number | null | "invalid" {
    const trimmed = scrapeLimit.trim();
    if (trimmed === "") {
      return null;
    }
    const limitValue = Number(trimmed);
    if (!Number.isInteger(limitValue) || limitValue < 1 || limitValue > 500) {
      return "invalid";
    }
    return limitValue;
  }

  async function runProductScrape(
    sources: Pick<SourceRegistryItem, "id" | "shop">[],
    limitValue: number | null,
  ): Promise<{ totalStored: number; totalSkipped: number; failed: number }> {
    setScrapeSteps(
      sources.map((source) => ({
        sourceId: source.id,
        shop: source.shop,
        status: "pending",
        stored: 0,
      })),
    );

    let totalStored = 0;
    let totalSkipped = 0;
    let failed = 0;
    let nextIndex = 0;

    async function worker() {
      while (true) {
        const index = nextIndex;
        nextIndex += 1;
        if (index >= sources.length) {
          return;
        }

        const source = sources[index];
        updateScrapeStep(source.id, { status: "running", message: undefined });

        try {
          const result = await scrapeSingleSource(source.id, limitValue);
          const succeeded = result.status === "成功";
          if (!succeeded) {
            failed += 1;
          }
          totalStored += result.stored;
          totalSkipped += result.skipped ?? 0;
          updateScrapeStep(source.id, {
            status: succeeded ? "success" : "failed",
            stored: result.stored,
            message: typeof result.message === "string" ? result.message : undefined,
          });
        } catch (reason) {
          failed += 1;
          updateScrapeStep(source.id, {
            status: "failed",
            stored: 0,
            message: reason instanceof Error ? reason.message : "抓取失败",
          });
        }
      }
    }

    const workerCount = Math.min(SCRAPE_CONCURRENCY, sources.length);
    await Promise.all(Array.from({ length: workerCount }, () => worker()));

    return { totalStored, totalSkipped, failed };
  }

  async function handleScrape() {
    const limitValue = parseScrapeLimitValue();
    if (limitValue === "invalid") {
      setScrapeError(true);
      setScrapeMessage("每源数量请输入 1–500 之间的整数，或留空表示不限制。");
      return;
    }

    setIsScraping(true);
    setScrapingSourceId(null);
    setScrapeMessage(null);
    setScrapeError(false);
    setScrapeSteps([]);

    try {
      const snapshot = registry ?? (await loadRegistrySnapshot());
      if (!snapshot) {
        throw new Error("无法读取数据源列表，请确认后端已启动。");
      }

      const enabled = enabledSources(snapshot);
      const selectedSet = new Set(selectedScrapeIds);
      const sources =
        selectedScrapeIds.length > 0
          ? enabled.filter((item) => selectedSet.has(item.id))
          : enabled;
      if (sources.length === 0) {
        throw new Error("请至少勾选一个要抓取的店铺。");
      }

      const { totalStored, totalSkipped, failed } = await runProductScrape(sources, limitValue);

      setScrapeMessage(
        `抓取完成：${sources.length} 个商品源，${
          scrapeIncremental ? "新入库" : "写入"
        } ${totalStored} 条${
          scrapeIncremental && totalSkipped > 0 ? `，跳过已有 ${totalSkipped} 条` : ""
        }，失败 ${failed} 个。`,
      );

      try {
        const eventParams = new URLSearchParams();
        if (limitValue !== null) {
          eventParams.set("limit_per_source", String(limitValue));
        }
        if (scrapeIncremental) {
          eventParams.set("incremental", "true");
        }
        const eventQuery = eventParams.toString();
        const eventResponse = await fetch(
          `/api/scrape/events/run${eventQuery ? `?${eventQuery}` : ""}`,
          adminFetchInit({ method: "POST" }),
        );
        if (eventResponse.ok) {
          const eventPayload = (await eventResponse.json()) as {
            stored: number;
            skipped?: number;
            failed: number;
          };
          setScrapeMessage(
            (current) =>
              `${current ?? ""} 活动${scrapeIncremental ? "新" : ""}入库 ${eventPayload.stored} 条${
                scrapeIncremental && (eventPayload.skipped ?? 0) > 0
                  ? `（跳过 ${eventPayload.skipped}）`
                  : ""
              }${eventPayload.failed > 0 ? `，活动源失败 ${eventPayload.failed} 个` : ""}。`,
          );
        }
      } catch {
        setScrapeMessage((current) => `${current ?? ""} 活动资讯抓取未完成。`);
      }

      setRefreshToken((token) => token + 1);
    } catch (reason) {
      setScrapeError(true);
      setScrapeMessage(reason instanceof Error ? reason.message : "抓取失败");
    } finally {
      setIsScraping(false);
      setScrapingSourceId(null);
    }
  }

  async function handleScrapeEvents() {
    const limitValue = parseScrapeLimitValue();
    if (limitValue === "invalid") {
      setScrapeError(true);
      setScrapeMessage("每源数量请输入 1–500 之间的整数，或留空表示不限制。");
      return;
    }

    setIsScraping(true);
    setScrapingSourceId(null);
    setScrapeMessage(null);
    setScrapeError(false);
    setScrapeSteps([]);

    try {
      const eventParams = new URLSearchParams();
      if (limitValue !== null) {
        eventParams.set("limit_per_source", String(limitValue));
      }
      if (scrapeIncremental) {
        eventParams.set("incremental", "true");
      }
      const eventQuery = eventParams.toString();
      const eventResponse = await fetch(
        `/api/scrape/events/run${eventQuery ? `?${eventQuery}` : ""}`,
        adminFetchInit({ method: "POST" }),
      );

      if (!eventResponse.ok) {
        const payload = await eventResponse.json().catch(() => null);
        const detail =
          payload && typeof payload.detail === "string"
            ? payload.detail
            : `活动资讯抓取失败（HTTP ${eventResponse.status}）`;
        throw new Error(detail);
      }

      const eventPayload = (await eventResponse.json()) as {
        stored: number;
        skipped?: number;
        failed: number;
      };
      setScrapeError(eventPayload.failed > 0);
      setScrapeMessage(
        `活动资讯抓取完成：${scrapeIncremental ? "新" : ""}入库 ${eventPayload.stored} 条${
          scrapeIncremental && (eventPayload.skipped ?? 0) > 0
            ? `，跳过已有 ${eventPayload.skipped}`
            : ""
        }${eventPayload.failed > 0 ? `，失败 ${eventPayload.failed} 个源` : ""}。`,
      );
      setRefreshToken((token) => token + 1);
    } catch (reason) {
      setScrapeError(true);
      setScrapeMessage(reason instanceof Error ? reason.message : "活动资讯抓取失败");
    } finally {
      setIsScraping(false);
      setScrapingSourceId(null);
    }
  }

  async function handleScrapeSource(item: SourceRegistryItem) {
    const limitValue = parseScrapeLimitValue();
    if (limitValue === "invalid") {
      setScrapeError(true);
      setScrapeMessage("每源数量请输入 1–500 之间的整数，或留空表示不限制。");
      return;
    }

    setIsScraping(true);
    setScrapingSourceId(item.id);
    setScrapeMessage(null);
    setScrapeError(false);
    setScrapeSteps([]);

    try {
      const { totalStored, failed } = await runProductScrape(
        [{ id: item.id, shop: item.shop }],
        limitValue,
      );
      const succeeded = failed === 0;
      setScrapeError(!succeeded);
      setScrapeMessage(
        succeeded
          ? `「${item.shop}」抓取完成，入库 ${totalStored} 条。`
          : `「${item.shop}」抓取失败${totalStored > 0 ? `，入库 ${totalStored} 条` : ""}。`,
      );
      setRefreshToken((token) => token + 1);
    } catch (reason) {
      setScrapeError(true);
      setScrapeMessage(reason instanceof Error ? reason.message : "抓取失败");
    } finally {
      setIsScraping(false);
      setScrapingSourceId(null);
    }
  }

  useEffect(() => {
    async function loadData() {
      setIsLoading(true);
      try {
        const params = new URLSearchParams(filterQuery);
        params.set("limit", String(PAGE_SIZE));
        params.set("offset", "0");

        const [filtersResponse, productsResponse] = await Promise.all([
          fetch("/api/filters"),
          fetch(`/api/products?${params.toString()}`),
        ]);

        if (!filtersResponse.ok || !productsResponse.ok) {
          const failedResponse = filtersResponse.ok ? productsResponse : filtersResponse;
          const payload = await failedResponse.json().catch(() => null);
          const detail =
            payload && typeof payload.detail === "string"
              ? payload.detail
              : `接口请求失败（HTTP ${failedResponse.status}）`;
          throw new Error(detail);
        }

        const [filterPayload, productPayload] = await Promise.all([
          filtersResponse.json(),
          productsResponse.json(),
        ]);

        const items = (productPayload.items ?? []) as Product[];
        setFilters(filterPayload);
        setProducts(items);
        setProductTotal(typeof productPayload.total === "number" ? productPayload.total : items.length);
        setHasMoreProducts(items.length >= PAGE_SIZE);
        setError(null);
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "加载失败");
      } finally {
        setIsLoading(false);
      }
    }

    void loadData();
  }, [filterQuery, refreshToken]);

  async function handleLoadMore() {
    if (isLoading || isLoadingMore || !hasMoreProducts) {
      return;
    }
    setIsLoadingMore(true);
    try {
      const params = new URLSearchParams(filterQuery);
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String(products.length));
      const response = await fetch(`/api/products?${params.toString()}`);
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        const detail =
          payload && typeof payload.detail === "string"
            ? payload.detail
            : `加载更多失败（HTTP ${response.status}）`;
        throw new Error(detail);
      }
      const payload = (await response.json()) as { items: Product[] };
      const items = payload.items ?? [];
      setProducts((current) => {
        const seen = new Set(current.map((item) => item.id));
        return [...current, ...items.filter((item) => !seen.has(item.id))];
      });
      setHasMoreProducts(items.length >= PAGE_SIZE);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "加载更多失败");
    } finally {
      setIsLoadingMore(false);
    }
  }

  const wishlistIdsKey = useMemo(
    () =>
      wishlist
        .map((item) => item.id)
        .sort((a, b) => a - b)
        .join(","),
    [wishlist],
  );

  useEffect(() => {
    if (view !== "wishlist" || !wishlistIdsKey) {
      if (!wishlistIdsKey) {
        setWishlistProducts([]);
      }
      return;
    }

    let cancelled = false;
    async function refreshWishlist() {
      try {
        const params = new URLSearchParams();
        for (const id of wishlistIdsKey.split(",")) {
          params.append("ids", id);
        }
        const response = await fetch(`/api/products/by-ids?${params.toString()}`);
        if (!response.ok || cancelled) {
          return;
        }
        const payload = (await response.json()) as { items: Product[] };
        const items = payload.items ?? [];
        if (cancelled) {
          return;
        }
        setWishlistProducts(items);
        setWishlist((current) => applyProductRefresh(current, items));
      } catch {
        // keep local snapshot
      }
    }

    void refreshWishlist();
    return () => {
      cancelled = true;
    };
  }, [view, wishlistIdsKey, refreshToken]);

  useEffect(() => {
    if (clearCountdown === null || clearCountdown <= 0) {
      return;
    }

    const timer = window.setTimeout(() => {
      setClearCountdown((value) => (value !== null && value > 0 ? value - 1 : 0));
    }, 1000);

    return () => window.clearTimeout(timer);
  }, [clearCountdown]);

  function resetClearConfirm() {
    setClearConfirmOpen(false);
    setClearToken(null);
    setClearCountdown(null);
    setIsPreparingClear(false);
    setIsClearing(false);
  }

  async function handlePrepareClear() {
    setIsPreparingClear(true);
    setClearMessage(null);
    setClearError(false);

    try {
      const response = await fetch(
        "/api/admin/clear-scraped-data/prepare",
        adminFetchInit({ method: "POST" }),
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        const detail =
          payload && typeof payload.detail === "string"
            ? payload.detail
            : `准备清空失败（HTTP ${response.status}）`;
        throw new Error(detail);
      }

      const payload = (await response.json()) as {
        token: string;
        wait_seconds: number;
        message: string;
      };
      setClearConfirmOpen(true);
      setClearToken(payload.token);
      setClearCountdown(payload.wait_seconds);
      setClearMessage(payload.message);
    } catch (reason) {
      setClearError(true);
      setClearMessage(reason instanceof Error ? reason.message : "准备清空失败");
      resetClearConfirm();
    } finally {
      setIsPreparingClear(false);
    }
  }

  async function handleConfirmClear() {
    if (!clearToken || clearCountdown === null || clearCountdown > 0) {
      return;
    }

    setIsClearing(true);
    setClearMessage(null);
    setClearError(false);

    try {
      const response = await fetch(
        `/api/admin/clear-scraped-data/confirm?token=${encodeURIComponent(clearToken)}`,
        adminFetchInit({ method: "POST" }),
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        const detail =
          payload && typeof payload.detail === "string"
            ? payload.detail
            : `清空失败（HTTP ${response.status}）`;
        throw new Error(detail);
      }

      const payload = (await response.json()) as {
        deleted_products: number;
        deleted_runs: number;
      };
      setClearMessage(
        `已清空：删除商品 ${payload.deleted_products} 条，删除抓取记录 ${payload.deleted_runs} 条。`,
      );
      resetClearConfirm();
      setRefreshToken((token) => token + 1);
    } catch (reason) {
      setClearError(true);
      setClearMessage(reason instanceof Error ? reason.message : "清空失败");
    } finally {
      setIsClearing(false);
    }
  }

  return (
    <main>
      <header className="hero">
        <ExchangeRateWidget />
        <p className="eyebrow">Animegood Aggregator</p>
        <h1>动漫周边新品与联动预告</h1>
        <p className="subtitle">
          帮你发现日本官方店与电商的动漫周边新品，点击即可跳转原店购买。
        </p>
        <HeroEvents events={events} showShopLabels />
      </header>

      <div className="view-tabs" role="tablist" aria-label="浏览模式">
        <button
          type="button"
          className={view === "discover" ? "active" : ""}
          onClick={() => setView("discover")}
        >
          发现
        </button>
        <button
          type="button"
          className={view === "wishlist" ? "active" : ""}
          onClick={() => setView("wishlist")}
        >
          收藏夹{wishlist.length > 0 ? ` (${wishlist.length})` : ""}
        </button>
        <button
          type="button"
          className={view === "cart" ? "active" : ""}
          onClick={() => setView("cart")}
        >
          购物车{cartCount > 0 ? ` (${cartCount})` : ""}
        </button>
      </div>

      {view === "discover" ? (
        <>
      <section className="filters" aria-label="筛选">
        <label className="search-field">
          <span>搜索</span>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="商品名 / IP / 系列 / 角色 / 店铺"
          />
        </label>
        <Select label="IP" value={selectedIp} options={filters.ips} onChange={setSelectedIp} />
        <Select label="店铺" value={selectedShop} options={filters.shops} onChange={setSelectedShop} />
        <Select
          label="系列"
          value={selectedSeries}
          options={filters.series}
          onChange={setSelectedSeries}
        />
        <Select
          label="发售月份"
          value={selectedMonth}
          options={filters.release_months}
          onChange={setSelectedMonth}
        />
        <label>
          <span>排序</span>
          <select value={sort} onChange={(event) => setSort(event.target.value)}>
            <option value="newest">最新发现</option>
            <option value="popular">收藏最多</option>
            <option value="price_asc">价格从低到高</option>
            <option value="price_desc">价格从高到低</option>
          </select>
        </label>
        <label className="filter-check">
          <span>仅可购买</span>
          <input
            type="checkbox"
            checked={availableOnly}
            onChange={(event) => setAvailableOnly(event.target.checked)}
          />
        </label>
      </section>

      {(activeFilterChips.length > 0 || productTotal > 0 || !isLoading) && view === "discover" ? (
        <div className="filter-summary" aria-label="筛选摘要">
          <p className="filter-summary-count">
            {isLoading ? "加载中…" : `共 ${productTotal} 件`}
            {!isLoading && products.length > 0 && products.length < productTotal
              ? `（已加载 ${products.length}）`
              : ""}
          </p>
          {activeFilterChips.length > 0 ? (
            <div className="filter-chips">
              {activeFilterChips.map((chip) => (
                <button key={chip.key} type="button" className="filter-chip" onClick={chip.clear}>
                  {chip.label} ×
                </button>
              ))}
              <button type="button" className="filter-clear" onClick={clearAllFilters}>
                清除筛选
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      {spotlightIps.length > 0 ? (
        <section className="ip-chips" aria-label="热门 IP">
          <p className="ip-chips-label">热门 IP</p>
          <div className="ip-chips-list">
            {spotlightIps.map((ip) => (
              <button
                key={ip}
                type="button"
                className={selectedIp === ip ? "active" : ""}
                onClick={() => setSelectedIp(selectedIp === ip ? "" : ip)}
              >
                {ip}
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {error ? <p className="notice error">读取数据失败：{error}</p> : null}
      {isLoading ? <p className="notice">正在加载最新商品...</p> : null}
      {!isLoading && !error && products.length === 0 ? (
        <section className="empty-state" aria-label="暂无商品">
          <h2>还没有商品</h2>
          {activeFilterChips.length > 0 ? (
            <>
              <p>当前筛选条件下没有结果。试试清除部分条件，或换个关键词。</p>
              <button type="button" className="scrape-button" onClick={clearAllFilters}>
                清除筛选
              </button>
            </>
          ) : (
            <>
              <p>
                {scrapeIntervalHours > 0
                  ? `站点会定时自动抓取（约每 ${scrapeIntervalHours} 小时）。若刚部署，可先手动拉取一次。`
                  : "首次使用需要抓取商品入库。访客无需操作；管理员可一键拉取。"}
              </p>
              {authRequired ? (
                <label className="admin-token-field">
                  <span>管理口令</span>
                  <input
                    type="password"
                    value={adminToken}
                    autoComplete="current-password"
                    placeholder="与服务器 ANIMEGOOD_ADMIN_TOKEN 一致"
                    onChange={(event) => setAdminToken(event.target.value)}
                  />
                </label>
              ) : null}
              <div className="empty-state-actions">
                <button
                  type="button"
                  className="scrape-button"
                  disabled={isScraping || (authRequired && !adminToken.trim())}
                  onClick={() => void handleScrape()}
                >
                  {isScraping ? "拉取中..." : "拉取最新商品"}
                </button>
                <button
                  type="button"
                  className="scrape-button secondary"
                  onClick={() => setDevToolsOpen(true)}
                >
                  打开开发者工具
                </button>
              </div>
              {authRequired && !adminToken.trim() ? (
                <p className="notice">公网模式需填写管理口令后才能拉取；普通访客请稍后再看。</p>
              ) : null}
              {scrapeMessage ? (
                <p className={`notice ${scrapeError ? "error" : "success"}`}>{scrapeMessage}</p>
              ) : null}
            </>
          )}
        </section>
      ) : null}

      <section className="grid" aria-label="最新商品">
        {products.map((product) => (
          <ProductCard
            key={product.id}
            product={product}
            isSaved={wishlistIds.has(product.id)}
            showShopLabels
            cnyPer100Jpy={cnyPer100Jpy}
            onToggleSave={() => void handleToggleWishlist(product)}
            onAddToCart={() => handleAddToCart(product)}
            cartQuantity={cartQuantities.get(product.id) ?? 0}
            onOpen={() => void openDetail(product)}
          />
        ))}
      </section>
      {!isLoading && !error && products.length > 0 ? (
        <div className="load-more">
          <p className="load-more-count">已显示 {products.length} 件</p>
          {hasMoreProducts ? (
            <button
              type="button"
              className="load-more-button"
              disabled={isLoadingMore}
              onClick={() => void handleLoadMore()}
            >
              {isLoadingMore ? "加载中..." : "加载更多"}
            </button>
          ) : (
            <p className="load-more-end">已到底</p>
          )}
        </div>
      ) : null}
        </>
      ) : view === "wishlist" ? (
        <>
          {wishlist.length === 0 ? (
            <p className="notice">收藏夹为空。在发现页点击商品卡片上的「收藏」即可加入。</p>
          ) : (
            <section className="grid" aria-label="收藏夹">
              {wishlist.map((product) => {
                const live =
                  wishlistProducts.find((item) => item.id === product.id) ??
                  products.find((item) => item.id === product.id);
                const cardProduct = wishlistToProduct(product, live);
                return (
                  <ProductCard
                    key={product.id}
                    showShopLabels
                    product={cardProduct}
                    isSaved
                    cnyPer100Jpy={cnyPer100Jpy}
                    onToggleSave={() => void handleToggleWishlist(cardProduct)}
                    onAddToCart={() => handleAddToCart(cardProduct)}
                    cartQuantity={cartQuantities.get(product.id) ?? 0}
                    onOpen={() => void openDetail(cardProduct)}
                  />
                );
              })}
            </section>
          )}
          <WishlistBackupPanel
            items={wishlist}
            onImport={(incoming) => setWishlist((items) => mergeWishlistItems(items, incoming))}
          />
        </>
      ) : (
        <CartPanel
          items={cart}
          onUpdateQuantity={(id, quantity) => setCart((items) => updateQuantity(items, id, quantity))}
          onRemove={(id) => setCart((items) => removeItem(items, id))}
          onClear={() => setCart(clearCart())}
          onImport={(incoming) => setCart((items) => mergeCartItems(items, incoming))}
        />
      )}

      <details
        className="dev-tools"
        open={devToolsOpen}
        onToggle={(event) => setDevToolsOpen((event.target as HTMLDetailsElement).open)}
      >
        <summary>开发者工具</summary>

      <section className="scrape-panel" aria-label="抓取控制">
        <div className="scrape-panel-text">
          <h2>手动抓取</h2>
          <p>
            商品：点「立即抓取」或网站收录表内单站抓取。活动资讯：点「抓取活动资讯」。
            {authRequired
              ? " 公网已启用管理口令，须填写下方口令。"
              : " 当前未启用管理口令（本机开发模式）。"}
            {scrapeIntervalHours > 0
              ? ` 定时抓取：每 ${scrapeIntervalHours} 小时。`
              : ""}
          </p>
        </div>
        <label className="admin-token-field">
          <span>管理口令</span>
          <input
            type="password"
            value={adminToken}
            autoComplete="current-password"
            placeholder={authRequired ? "必填" : "可选（未配置服务端口令时可留空）"}
            onChange={(event) => setAdminToken(event.target.value)}
          />
        </label>
        <label className="scrape-limit">
          <span>每源数量</span>
          <input
            type="number"
            min={1}
            max={500}
            value={scrapeLimit}
            placeholder="留空不限制"
            disabled={isScraping}
            onChange={(event) => setScrapeLimit(event.target.value)}
          />
        </label>
        <label className="filter-check scrape-incremental">
          <span>仅入库新数据</span>
          <input
            type="checkbox"
            checked={scrapeIncremental}
            disabled={isScraping}
            onChange={(event) => setScrapeIncremental(event.target.checked)}
          />
        </label>
        <p className="scrape-incremental-hint">
          {scrapeIncremental
            ? "增量模式：按链接查重，已有商品/活动跳过，不刷新旧价。"
            : "全量模式：会更新已有商品的价格与库存。"}
        </p>
        {registry ? (
          <fieldset className="scrape-source-picker" disabled={isScraping}>
            <legend>选择要抓的店铺</legend>
            <div className="scrape-source-actions">
              <button
                type="button"
                className="scrape-button secondary"
                onClick={() =>
                  setSelectedScrapeIds(
                    registry.items.filter((item) => item.enabled).map((item) => item.id),
                  )
                }
              >
                全选已启用
              </button>
              <button
                type="button"
                className="scrape-button secondary"
                onClick={() => setSelectedScrapeIds([])}
              >
                清空
              </button>
            </div>
            <div className="scrape-source-list">
              {registry.items
                .filter((item) => item.enabled)
                .map((item) => {
                  const checked = selectedScrapeIds.includes(item.id);
                  return (
                    <label key={item.id} className="scrape-source-item">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => {
                          setSelectedScrapeIds((current) =>
                            checked
                              ? current.filter((id) => id !== item.id)
                              : [...current, item.id],
                          );
                        }}
                      />
                      <span>{item.shop}</span>
                    </label>
                  );
                })}
            </div>
          </fieldset>
        ) : null}
        <div className="scrape-panel-actions">
          <button type="button" className="scrape-button" disabled={isScraping} onClick={() => void handleScrape()}>
            {isScraping ? "抓取中..." : "立即抓取"}
          </button>
          <button
            type="button"
            className="scrape-button secondary"
            disabled={isScraping}
            onClick={() => void handleScrapeEvents()}
          >
            {isScraping ? "抓取中..." : "抓取活动资讯"}
          </button>
        </div>
      </section>

      {scrapeProgress ? (
        <section className="scrape-progress" aria-label="抓取进度">
          <div className="scrape-progress-header">
            <p className="scrape-progress-title">
              {isScraping && scrapeProgress.runningSteps.length > 0
                ? scrapeProgress.runningSteps.length === 1
                  ? `正在抓取 ${scrapeProgress.completed + 1}/${scrapeProgress.total}：${scrapeProgress.runningSteps[0].shop}`
                  : `正在抓取 ${scrapeProgress.runningSteps.length} 个站点（${scrapeProgress.completed}/${scrapeProgress.total} 已完成）`
                : `抓取进度 ${scrapeProgress.completed}/${scrapeProgress.total}`}
            </p>
            <span className="scrape-progress-percent">{scrapeProgress.percent}%</span>
          </div>
          <div
            className="scrape-progress-bar"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={scrapeProgress.percent}
            aria-label="抓取进度"
          >
            <div className="scrape-progress-fill" style={{ width: `${scrapeProgress.percent}%` }} />
          </div>
          <ul className="scrape-progress-steps">
            {scrapeSteps.map((step) => (
              <li key={step.sourceId} className={`scrape-step scrape-step-${step.status}`}>
                <span className="scrape-step-shop">{step.shop}</span>
                <span className="scrape-step-status">{scrapeStepLabel(step)}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {scrapeMessage ? (
        <p className={`notice ${scrapeError ? "error" : "success"}`}>{scrapeMessage}</p>
      ) : null}

      <section className="admin-panel" aria-label="数据管理">
        <div className="admin-panel-text">
          <h2>数据管理</h2>
          <p>清空本地已抓取的商品与运行记录，不可恢复，仅供调试使用。</p>
        </div>
        {!clearConfirmOpen ? (
          <button
            type="button"
            className="admin-danger-button"
            disabled={isScraping || isPreparingClear || isClearing}
            onClick={() => void handlePrepareClear()}
          >
            {isPreparingClear ? "准备中..." : "清空抓取数据"}
          </button>
        ) : (
          <div className="clear-confirm">
            <p className="clear-confirm-warning">
              此操作将删除全部商品与抓取记录，且无法恢复。请再次确认。
            </p>
            {clearCountdown !== null && clearCountdown > 0 ? (
              <p className="clear-confirm-countdown">请等待 {clearCountdown} 秒后可确认</p>
            ) : (
              <p className="clear-confirm-ready">现在可以确认清空</p>
            )}
            <div className="clear-confirm-actions">
              <button
                type="button"
                className="admin-secondary-button"
                disabled={isClearing}
                onClick={resetClearConfirm}
              >
                取消
              </button>
              <button
                type="button"
                className="admin-danger-button"
                disabled={isClearing || clearCountdown === null || clearCountdown > 0}
                onClick={() => void handleConfirmClear()}
              >
                {isClearing ? "清空中..." : "确认清空"}
              </button>
            </div>
          </div>
        )}
      </section>

      {clearMessage ? (
        <p className={`notice ${clearError ? "error" : "success"}`}>{clearMessage}</p>
      ) : null}

      <section className={`registry ${registryOpen ? "open" : "collapsed"}`} aria-label="网站收录表">
        <button
          type="button"
          className="registry-toggle"
          aria-expanded={registryOpen}
          onClick={() => setRegistryOpen((open) => !open)}
        >
          <div className="registry-toggle-text">
            <h2>网站收录表</h2>
            <p className="registry-summary">
              已收录 {registry?.included_count ?? 0} 个 · 未收录 {registry?.excluded_count ?? 0} 个
              {registry && registry.easy_pending_count > 0
                ? ` · 易抓待接入 ${registry.easy_pending_count} 个`
                : ""}
            </p>
          </div>
          <span className="registry-chevron" aria-hidden="true">
            {registryOpen ? "收起" : "展开"}
          </span>
        </button>

        {registryOpen ? (
          <>
            <div className="registry-toolbar">
              <div className="registry-tabs" role="tablist" aria-label="收录筛选">
                {(["全部", "已收录", "未收录", "易抓待接入"] as RegistryFilter[]).map((option) => (
                  <button
                    key={option}
                    type="button"
                    className={registryFilter === option ? "active" : ""}
                    onClick={() => setRegistryFilter(option)}
                  >
                    {option}
                  </button>
                ))}
              </div>
            </div>

            <div className="registry-table-wrap">
              <table className="registry-table">
                <thead>
                  <tr>
                    <th>收录状态</th>
                    <th>店铺</th>
                    <th>网站</th>
                    <th>平台</th>
                    <th>难度</th>
                    <th>优先级</th>
                    <th>核心 IP</th>
                    <th>商品数</th>
                    <th>最近抓取</th>
                    <th>操作</th>
                    <th>备注</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRegistryItems.length === 0 ? (
                    <tr>
                      <td colSpan={11} className="registry-empty">
                        暂无收录数据
                      </td>
                    </tr>
                  ) : (
                    filteredRegistryItems.map((item) => (
                      <tr key={item.id}>
                        <td>
                          <span className={inclusionClassName(item.inclusion_status)}>
                            {item.inclusion_status}
                          </span>
                        </td>
                        <td>{item.shop}</td>
                        <td>
                          <a href={item.base_url} target="_blank" rel="noreferrer">
                            {formatHost(item.base_url)}
                          </a>
                        </td>
                        <td>{platformLabel(item.source_platform)}</td>
                        <td>
                          <span className={difficultyClassName(item.difficulty)}>{item.difficulty}</span>
                        </td>
                        <td>{item.priority}</td>
                        <td>{item.core_ips.length > 0 ? item.core_ips.join("、") : "—"}</td>
                        <td>{item.product_count}</td>
                        <td>
                          {item.last_run_status ? (
                            <span className={runStatusClassName(item.last_run_status)}>
                              {item.last_run_status}
                            </span>
                          ) : (
                            "—"
                          )}
                          {item.last_run_at ? (
                            <span className="registry-subtext">{formatDate(item.last_run_at)}</span>
                          ) : null}
                        </td>
                        <td>
                          <button
                            type="button"
                            className="registry-scrape-button"
                            disabled={isScraping}
                            title={
                              item.enabled
                                ? `抓取 ${item.shop}`
                                : `测试抓取 ${item.shop}（当前未启用，不会参与「立即抓取」）`
                            }
                            onClick={() => void handleScrapeSource(item)}
                          >
                            {scrapingSourceId === item.id ? "抓取中..." : "抓取"}
                          </button>
                        </td>
                        <td className="registry-notes">{item.notes ?? "—"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </section>

      </details>

      {detailProduct ? (
        <ProductDetail
          product={detailProduct}
          compareProducts={compareProducts}
          seriesProducts={seriesProducts}
          isSaved={wishlistIds.has(detailProduct.id)}
          showShopLabels
          cnyPer100Jpy={cnyPer100Jpy}
          onClose={() => {
            setDetailProduct(null);
            setSeriesProducts([]);
            setCompareProducts([]);
          }}
          onSelectSeries={(series) => {
            setSelectedSeries(series);
            setView("discover");
            setDetailProduct(null);
            setSeriesProducts([]);
            setCompareProducts([]);
          }}
          onToggleSave={() => void handleToggleWishlist(detailProduct)}
          onAddToCart={() => handleAddToCart(detailProduct)}
          cartQuantity={cartQuantities.get(detailProduct.id) ?? 0}
        />
      ) : null}
    </main>
  );
}

function WishlistBackupPanel({
  items,
  onImport,
}: {
  items: WishlistItem[];
  onImport: (incoming: WishlistItem[]) => void;
}) {
  const [importText, setImportText] = useState("");
  const [importMessage, setImportMessage] = useState<string | null>(null);
  const [importError, setImportError] = useState(false);
  const [exportText, setExportText] = useState("");

  useEffect(() => {
    setExportText(items.length > 0 ? exportWishlistBase64(items) : "");
  }, [items]);

  function handleImport() {
    const result = parseWishlistImport(importText);
    if (!result.ok) {
      setImportError(true);
      setImportMessage(result.error);
      return;
    }
    onImport(result.items);
    setImportError(false);
    setImportMessage(`已合并 ${result.items.length} 条收藏。`);
    setImportText("");
  }

  function handleCopyExport() {
    if (!exportText) {
      return;
    }
    void navigator.clipboard.writeText(exportText).then(() => {
      setImportError(false);
      setImportMessage("已复制收藏夹备份到剪贴板。");
    });
  }

  return (
    <section className="cart-io" aria-label="收藏夹导入导出">
      <h2>备份与恢复</h2>
      <p>
        导出为 Base64 字符串，可在另一台设备导入。导入默认与现有收藏合并（相同商品 ID
        覆盖为导入快照，最多 200 条）。打开本页时会自动用库内最新价格/库存刷新。
      </p>
      <label className="cart-io-field">
        <span>导出</span>
        <textarea readOnly value={exportText} rows={3} placeholder="收藏夹为空时无可导出内容" />
      </label>
      <button type="button" className="scrape-button secondary" disabled={!exportText} onClick={handleCopyExport}>
        复制备份
      </button>
      <label className="cart-io-field">
        <span>导入（合并）</span>
        <textarea
          value={importText}
          rows={3}
          placeholder="粘贴 Base64 备份字符串"
          onChange={(event) => setImportText(event.target.value)}
        />
      </label>
      <button type="button" className="scrape-button" onClick={handleImport}>
        导入合并
      </button>
      {importMessage ? (
        <p className={`notice ${importError ? "error" : "success"}`}>{importMessage}</p>
      ) : null}
    </section>
  );
}

function ProductName({
  product_name,
  display_name_zh,
  as: Tag = "h2",
  className = "",
}: {
  product_name: string;
  display_name_zh?: string | null;
  as?: "h2" | "p" | "span";
  className?: string;
}) {
  const showOriginal = Boolean(display_name_zh && display_name_zh !== product_name);
  return (
    <div className={`product-name-block ${className}`.trim()}>
      <Tag>{showOriginal ? display_name_zh : product_name}</Tag>
      {showOriginal ? <p className="product-name-original">{product_name}</p> : null}
    </div>
  );
}

function ProductCard({
  product,
  isSaved,
  showShopLabels,
  cnyPer100Jpy = null,
  onToggleSave,
  onAddToCart,
  cartQuantity,
  onOpen,
}: {
  product: Product;
  isSaved: boolean;
  showShopLabels: boolean;
  cnyPer100Jpy?: number | null;
  onToggleSave: () => void;
  onAddToCart: () => void;
  cartQuantity: number;
  onOpen: () => void;
}) {
  const cnyLabel = formatCnyEstimate(product.price, cnyPer100Jpy ?? null);
  return (
    <article className="card card-clickable">
      <button type="button" className="card-open" onClick={onOpen}>
        <div className="thumb">
          {product.favorite_count > 0 ? (
            <span className="hot-badge">{product.favorite_count} 人收藏</span>
          ) : null}
          {product.image_url ? (
            <img src={product.image_url} alt={product.product_name} loading="lazy" />
          ) : (
            <span>NO IMAGE</span>
          )}
        </div>
        <div className="card-body">
          <div className="meta">
            <span>{product.ip}</span>
            {showShopLabels ? <span className="meta-shop">{product.shop}</span> : null}
            <span className={stockClassName(product.stock_status)}>{product.stock_status}</span>
          </div>
          <ProductName product_name={product.product_name} display_name_zh={product.display_name_zh} />
          <dl>
            <div>
              <dt>价格</dt>
              <dd>
                {product.price ? `¥${product.price.toLocaleString("ja-JP")}` : "未取得"}
                {cnyLabel ? <span className="price-cny">{cnyLabel}</span> : null}
              </dd>
            </div>
            <div>
              <dt>发售日</dt>
              <dd>{product.release_date ?? "未取得"}</dd>
            </div>
          </dl>
        </div>
      </button>
      <div className="card-actions">
        <button
          type="button"
          className={`favorite-button ${isSaved ? "active" : ""}`}
          aria-pressed={isSaved}
          onClick={onToggleSave}
        >
          {isSaved ? "已收藏" : "收藏"}
        </button>
        <button
          type="button"
          className={`cart-button ${cartQuantity > 0 ? "active" : ""}`}
          onClick={onAddToCart}
          title={cartQuantity > 0 ? `已在购物车 ×${cartQuantity}` : "加入购物车"}
        >
          {cartQuantity > 0 ? `×${cartQuantity}` : "加购"}
        </button>
      </div>
    </article>
  );
}

function ProductDetail({
  product,
  compareProducts,
  seriesProducts,
  isSaved,
  showShopLabels,
  cnyPer100Jpy = null,
  onClose,
  onSelectSeries,
  onToggleSave,
  onAddToCart,
  cartQuantity,
}: {
  product: Product;
  compareProducts: Product[];
  seriesProducts: Product[];
  isSaved: boolean;
  showShopLabels: boolean;
  cnyPer100Jpy?: number | null;
  onClose: () => void;
  onSelectSeries: (series: string) => void;
  onToggleSave: () => void;
  onAddToCart: () => void;
  cartQuantity: number;
}) {
  const cnyLabel = formatCnyEstimate(product.price, cnyPer100Jpy ?? null);
  return (
    <div className="detail-overlay" role="presentation" onClick={onClose}>
      <div
        className="detail-panel"
        role="dialog"
        aria-modal="true"
        aria-label="商品详情"
        onClick={(event) => event.stopPropagation()}
      >
        <button type="button" className="detail-close" onClick={onClose}>
          关闭
        </button>
        <div className="detail-header">
          {product.image_url ? (
            <img src={product.image_url} alt={product.product_name} className="detail-image" />
          ) : null}
          <div>
            <div className="meta">
              <span>{product.ip}</span>
              {product.series ? (
                <button
                  type="button"
                  className="meta-series"
                  onClick={() => onSelectSeries(product.series!)}
                  title="按此系列筛选"
                >
                  系列：{product.series}
                </button>
              ) : null}
              {showShopLabels ? <span className="meta-shop">{product.shop}</span> : null}
              <span className={stockClassName(product.stock_status)}>{product.stock_status}</span>
            </div>
            <ProductName product_name={product.product_name} display_name_zh={product.display_name_zh} />
            <p className="detail-stats">
              {product.favorite_count > 0 ? `${product.favorite_count} 人收藏 · ` : ""}
              {product.price ? `¥${product.price.toLocaleString("ja-JP")}` : "价格未取得"}
              {cnyLabel ? ` · ${cnyLabel}` : ""}
            </p>
            <div className="detail-actions">
              <button
                type="button"
                className={`cart-button ${cartQuantity > 0 ? "active" : ""}`}
                onClick={onAddToCart}
              >
                {cartQuantity > 0 ? `已在购物车 ×${cartQuantity}` : "加入购物车"}
              </button>
              <button
                type="button"
                className={`favorite-button ${isSaved ? "active" : ""}`}
                onClick={onToggleSave}
              >
                {isSaved ? "已收藏" : "收藏"}
              </button>
              <a
                className="purchase-link"
                href={purchaseUrl(product.source_url, product.id)}
                target="_blank"
                rel="noreferrer"
                title={`去 ${product.shop} 购买`}
              >
                <span className="purchase-link-label">
                  {showShopLabels ? <span className="purchase-link-shop">{product.shop}</span> : null}
                  <span className="purchase-link-action">跳转到</span>
                </span>
              </a>
            </div>
          </div>
        </div>

        {seriesProducts.length > 0 && product.series ? (
          <section className="compare-section">
            <h3>同系列其他商品（{product.series}）</h3>
            <div className="compare-table-wrap">
              <table className="compare-table">
                <thead>
                  <tr>
                    <th>商品</th>
                    {showShopLabels ? <th>店铺</th> : null}
                    <th>价格</th>
                    <th>库存</th>
                    <th>热度</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {seriesProducts.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <ProductName
                          product_name={item.product_name}
                          display_name_zh={item.display_name_zh}
                          as="span"
                          className="product-name-compact"
                        />
                      </td>
                      {showShopLabels ? <td>{item.shop}</td> : null}
                      <td>{item.price ? `¥${item.price.toLocaleString("ja-JP")}` : "—"}</td>
                      <td>{item.stock_status}</td>
                      <td>{item.favorite_count || "—"}</td>
                      <td>
                        <a href={purchaseUrl(item.source_url, item.id)} target="_blank" rel="noreferrer">
                          购买
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}

        {compareProducts.length > 0 ? (
          <section className="compare-section">
            <h3>同 IP 其他商品（{product.ip}）</h3>
            <div className="compare-table-wrap">
              <table className="compare-table">
                <thead>
                  <tr>
                    <th>商品</th>
                    {showShopLabels ? <th>店铺</th> : null}
                    <th>价格</th>
                    <th>库存</th>
                    <th>热度</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  <tr className="compare-current">
                    <td>
                      <ProductName
                        product_name={product.product_name}
                        display_name_zh={product.display_name_zh}
                        as="span"
                        className="product-name-compact"
                      />
                    </td>
                    {showShopLabels ? <td>{product.shop}</td> : null}
                    <td>{product.price ? `¥${product.price.toLocaleString("ja-JP")}` : "—"}</td>
                    <td>{product.stock_status}</td>
                    <td>{product.favorite_count || "—"}</td>
                    <td>当前</td>
                  </tr>
                  {compareProducts.map((item) => (
                    <tr key={item.id}>
                    <td>
                      <ProductName
                        product_name={item.product_name}
                        display_name_zh={item.display_name_zh}
                        as="span"
                        className="product-name-compact"
                      />
                    </td>
                      {showShopLabels ? <td>{item.shop}</td> : null}
                      <td>{item.price ? `¥${item.price.toLocaleString("ja-JP")}` : "—"}</td>
                      <td>{item.stock_status}</td>
                      <td>{item.favorite_count || "—"}</td>
                      <td>
                        <a href={purchaseUrl(item.source_url, item.id)} target="_blank" rel="noreferrer">
                          购买
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}
      </div>
    </div>
  );
}

function CartPanel({
  items,
  onUpdateQuantity,
  onRemove,
  onClear,
  onImport,
}: {
  items: CartItem[];
  onUpdateQuantity: (id: number, quantity: number) => void;
  onRemove: (id: number) => void;
  onClear: () => void;
  onImport: (incoming: CartItem[]) => void;
}) {
  const [importText, setImportText] = useState("");
  const [importMessage, setImportMessage] = useState<string | null>(null);
  const [importError, setImportError] = useState(false);
  const [exportText, setExportText] = useState("");
  const [cnyPer100Jpy, setCnyPer100Jpy] = useState<number | null>(null);

  const totalJpy = useMemo(
    () => items.reduce((sum, item) => sum + (item.price ?? 0) * item.quantity, 0),
    [items],
  );

  const pricedItemCount = useMemo(
    () => items.filter((item) => item.price !== null).length,
    [items],
  );

  useEffect(() => {
    let cancelled = false;
    async function loadRate() {
      try {
        const response = await fetch("/api/exchange-rate", { cache: "no-store" });
        if (!response.ok) {
          return;
        }
        const payload = (await response.json()) as { cny_per_100_jpy: number };
        if (!cancelled && typeof payload.cny_per_100_jpy === "number") {
          setCnyPer100Jpy(payload.cny_per_100_jpy);
        }
      } catch {
        // ignore
      }
    }
    void loadRate();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setExportText(items.length > 0 ? exportCartBase64(items) : "");
  }, [items]);

  function handleImport() {
    const result = parseCartImport(importText);
    if (!result.ok) {
      setImportError(true);
      setImportMessage(result.error);
      return;
    }
    onImport(result.items);
    setImportError(false);
    setImportMessage(`已合并 ${result.items.length} 条商品到购物车。`);
    setImportText("");
  }

  function handleCopyExport() {
    if (!exportText) {
      return;
    }
    void navigator.clipboard.writeText(exportText).then(() => {
      setImportError(false);
      setImportMessage("已复制购物车备份到剪贴板。");
    });
  }

  const cnyEstimate =
    cnyPer100Jpy !== null && totalJpy > 0
      ? `约 ¥${((totalJpy * cnyPer100Jpy) / 100).toFixed(2)} 元（按 100 日元 ≈ ${cnyPer100Jpy} 元）`
      : null;

  if (items.length === 0) {
    return (
      <section className="cart-panel" aria-label="购物车">
        <p className="notice">购物车为空。在发现页点击商品卡片上的「加购」即可加入。</p>
        <CartImportExport
          exportText={exportText}
          importText={importText}
          importMessage={importMessage}
          importError={importError}
          onImportTextChange={setImportText}
          onImport={handleImport}
          onCopyExport={handleCopyExport}
        />
      </section>
    );
  }

  return (
    <section className="cart-panel" aria-label="购物车">
      <ul className="cart-list">
        {items.map((item) => {
          const lineTotal = item.price !== null ? item.price * item.quantity : null;
          return (
            <li key={item.id} className="cart-item">
              <div className="cart-item-thumb">
                {item.image_url ? (
                  <img src={item.image_url} alt={item.product_name} loading="lazy" />
                ) : (
                  <span>NO IMAGE</span>
                )}
              </div>
              <div className="cart-item-body">
                <p className="cart-item-shop">{item.shop}</p>
                <ProductName
                  product_name={item.product_name}
                  display_name_zh={item.display_name_zh}
                  className="cart-item-name-block"
                />
                <p className="cart-item-price">
                  单价 {item.price ? `¥${item.price.toLocaleString("ja-JP")}` : "未取得"}
                </p>
                <div className="cart-item-controls">
                  <div className="cart-qty" aria-label="数量">
                    <button
                      type="button"
                      onClick={() => onUpdateQuantity(item.id, item.quantity - 1)}
                      aria-label="减少数量"
                    >
                      −
                    </button>
                    <span>{item.quantity}</span>
                    <button
                      type="button"
                      onClick={() => onUpdateQuantity(item.id, item.quantity + 1)}
                      disabled={item.quantity >= 99}
                      aria-label="增加数量"
                    >
                      +
                    </button>
                  </div>
                  <button type="button" className="cart-remove" onClick={() => onRemove(item.id)}>
                    移除
                  </button>
                  <a
                    className="purchase-link cart-purchase-link"
                    href={purchaseUrl(item.source_url, item.id)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    跳转到
                  </a>
                </div>
              </div>
              <div className="cart-item-subtotal">
                {lineTotal !== null ? `¥${lineTotal.toLocaleString("ja-JP")}` : "—"}
              </div>
            </li>
          );
        })}
      </ul>

      <div className="cart-summary">
        <p className="cart-summary-total">
          合计（{items.length} 种 / {getCartCount(items)} 件）
          {pricedItemCount < items.length ? "，部分商品无价格" : ""}
          ：<strong>¥{totalJpy.toLocaleString("ja-JP")}</strong>
        </p>
        {cnyEstimate ? <p className="cart-summary-cny">{cnyEstimate}</p> : null}
        <button type="button" className="admin-secondary-button" onClick={onClear}>
          清空购物车
        </button>
      </div>

      <CartImportExport
        exportText={exportText}
        importText={importText}
        importMessage={importMessage}
        importError={importError}
        onImportTextChange={setImportText}
        onImport={handleImport}
        onCopyExport={handleCopyExport}
      />
    </section>
  );
}

function CartImportExport({
  exportText,
  importText,
  importMessage,
  importError,
  onImportTextChange,
  onImport,
  onCopyExport,
}: {
  exportText: string;
  importText: string;
  importMessage: string | null;
  importError: boolean;
  onImportTextChange: (value: string) => void;
  onImport: () => void;
  onCopyExport: () => void;
}) {
  return (
    <section className="cart-io" aria-label="购物车导入导出">
      <h2>备份与恢复</h2>
      <p className="section-desc">
        导出为 Base64 字符串，可在另一台设备导入。导入默认与现有购物车合并（相同商品 ID 累加数量，上限 99）。
      </p>
      <label className="cart-io-field">
        <span>导出</span>
        <textarea readOnly value={exportText} placeholder="购物车为空时无可导出内容" rows={3} />
        <button type="button" className="scrape-button secondary" disabled={!exportText} onClick={onCopyExport}>
          复制备份
        </button>
      </label>
      <label className="cart-io-field">
        <span>导入（合并）</span>
        <textarea
          value={importText}
          onChange={(event) => onImportTextChange(event.target.value)}
          placeholder="粘贴 Base64 备份字符串"
          rows={3}
        />
        <button type="button" className="scrape-button" onClick={onImport}>
          导入合并
        </button>
      </label>
      {importMessage ? (
        <p className={`notice ${importError ? "error" : "success"}`}>{importMessage}</p>
      ) : null}
    </section>
  );
}

function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label>
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">全部</option>
        {options.map((option) => (
          <option value={option} key={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function stockClassName(status: string) {
  if (status === "可购买") return "stock available";
  if (status === "未开售") return "stock upcoming";
  if (status === "已结束" || status === "缺货") return "stock unavailable";
  return "stock unknown";
}

function inclusionClassName(status: string) {
  return status === "已收录" ? "badge included" : "badge excluded";
}

function runStatusClassName(status: string) {
  return status === "成功" ? "badge run-success" : "badge run-failed";
}

function isEasyDifficulty(difficulty: string) {
  return difficulty === "极低" || difficulty === "低" || difficulty === "中低";
}

function difficultyClassName(difficulty: string) {
  if (difficulty === "极低" || difficulty === "低") return "badge difficulty-easy";
  if (difficulty === "中低") return "badge difficulty-medium-low";
  if (difficulty === "中" || difficulty === "中高") return "badge difficulty-medium";
  return "badge difficulty-hard";
}

function platformLabel(platform: string) {
  const labels: Record<string, string> = {
    shopify: "Shopify",
    "ec-cube": "EC-CUBE",
    "base-stores": "BASE / STORES",
    ochanoko: "おちゃのこ",
    "color-me": "カラーミー",
    futureshop: "futureshop",
    "large-ec": "大型 EC",
  };
  return labels[platform] ?? platform;
}

function formatHost(url: string) {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

function scrapeStepLabel(step: ScrapeStep) {
  if (step.status === "pending") {
    return "等待中";
  }
  if (step.status === "running") {
    return "抓取中...";
  }
  if (step.status === "success") {
    return `成功 · ${step.stored} 条`;
  }
  return step.message ? `失败 · ${step.message}` : "失败";
}

function purchaseUrl(sourceUrl: string, productId: number) {
  try {
    const url = new URL(sourceUrl);
    url.searchParams.set("utm_source", "animegood");
    url.searchParams.set("utm_content", String(productId));
    return url.toString();
  } catch {
    return sourceUrl;
  }
}

export default App;
