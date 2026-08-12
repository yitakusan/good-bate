import { useEffect, useState } from "react";

import {
  AuthUser,
  OrderRequestPublic,
  ScrapeProduct,
  confirmDeposit,
  createOrderRequest,
  fetchMe,
  fetchMeta,
  fetchMyOrderRequests,
  fetchPublicOrderRequests,
  publicScrapeUrl,
} from "./api";
import { batchScrapeDelayMs, waitForBatchScrape } from "./scrapeDelay";

function errorText(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function formatYen(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  return `¥${value.toLocaleString("ja-JP")}`;
}

function orderNo(req: OrderRequestPublic) {
  return (req.account_order_no || req.request_code || "").trim() || "—";
}

function amountOf(req: OrderRequestPublic) {
  if (req.amount != null) return req.amount;
  if (req.unit_cost == null) return null;
  return req.unit_cost * req.qty;
}

function parseScrapeUrls(raw: string): string[] {
  const seen = new Set<string>();
  const urls: string[] = [];
  for (const part of raw.split(/[\n\r,;\t]+/)) {
    let text = part.trim();
    if (!text) continue;
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

export default function ApplyPage() {
  const [scrapeUrlValue, setScrapeUrlValue] = useState("");
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
  const [contact, setContact] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const [depositRate, setDepositRate] = useState(0.3);
  const [pendingMine, setPendingMine] = useState<OrderRequestPublic[]>([]);
  const [depositBusy, setDepositBusy] = useState("");

  const [requests, setRequests] = useState<OrderRequestPublic[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [listError, setListError] = useState("");
  const [listLoading, setListLoading] = useState(false);

  async function loadRequests(filter = statusFilter) {
    setListLoading(true);
    setListError("");
    try {
      setRequests(await fetchPublicOrderRequests(filter || undefined));
    } catch (err) {
      setListError(errorText(err));
    } finally {
      setListLoading(false);
    }
  }

  async function loadPendingMine(user = authUser) {
    if (!user) {
      setPendingMine([]);
      return;
    }
    try {
      setPendingMine(await fetchMyOrderRequests("pending_payment"));
    } catch {
      setPendingMine([]);
    }
  }

  useEffect(() => {
    void (async () => {
      try {
        const meta = await fetchMeta();
        setAuthUser(meta.user ?? null);
        if (typeof meta.deposit_rate === "number" && meta.deposit_rate > 0) {
          setDepositRate(meta.deposit_rate);
        }
        await loadPendingMine(meta.user ?? null);
      } catch {
        try {
          setAuthUser(await fetchMe());
        } catch {
          setAuthUser(null);
        }
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void loadRequests();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  const selectedDepositTotal = (() => {
    let goods = 0;
    let missing = 0;
    for (const index of collectionPick) {
      const product = collection[index];
      if (!product) continue;
      const priceText = (collectionPrice[index] || "").trim();
      const unit =
        priceText === ""
          ? product.unit_cost
          : Number.isFinite(Number(priceText))
            ? Number(priceText)
            : product.unit_cost;
      const qty = Math.max(1, Number(collectionQty[index]) || 1);
      if (unit == null || !Number.isFinite(unit)) {
        missing += 1;
        continue;
      }
      goods += unit * qty;
    }
    return {
      goods,
      deposit: Math.round(goods * depositRate * 100) / 100,
      missing,
      ratePct: Math.round(depositRate * 100),
    };
  })();

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
      for (const index of newIndexes) copy[index] = copy[index] || "1";
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
    return { next, added };
  }

  async function onScrape() {
    const urls = parseScrapeUrls(scrapeUrlValue);
    if (!urls.length) {
      setError("请粘贴一个或多个网址（每行一个，也可用逗号分隔）");
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
          const result = await publicScrapeUrl(url);
          ok += 1;
          const { next, added } = appendScrapeProducts(
            result.products || [],
            working,
          );
          working = next;
          addedTotal += added.length;
          if (!result.products?.length) {
            failures.push(`${url} → ${result.message || "无商品"}`);
            previousFailed = true;
          }
        } catch (err) {
          failures.push(`${url} → ${errorText(err)}`);
          previousFailed = true;
        }
      }
      const failText = failures.length
        ? `；失败 ${failures.length}：${failures.slice(0, 3).join("；")}`
        : "";
      setMessage(
        `抓取完成：成功 ${ok}/${urls.length} 个链接，新增 ${addedTotal} 条商品${failText}`,
      );
      if (failures.length) setError(failures.slice(0, 5).join("\n"));
    } finally {
      setScrapeBusy(false);
    }
  }

  function clearCollection() {
    setCollection([]);
    setCollectionPick([]);
    setCollectionQty({});
    setCollectionPrice({});
    setCollectionBarcode({});
  }

  async function onSubmitRequests() {
    if (!authUser) {
      setError("请先登录后再提交订单");
      return;
    }
    if (!collectionPick.length) {
      setError("请至少勾选一件");
      return;
    }
    if (selectedDepositTotal.missing > 0) {
      setError("所选商品须填写单价，才能计算 30% 定金");
      return;
    }
    setScrapeBusy(true);
    setError("");
    setMessage("");
    let ok = 0;
    const failures: string[] = [];
    try {
      for (const index of collectionPick) {
        const product = collection[index];
        if (!product) continue;
        const priceText = (collectionPrice[index] || "").trim();
        const unitCost =
          priceText === ""
            ? product.unit_cost
            : Number.isFinite(Number(priceText))
              ? Number(priceText)
              : product.unit_cost;
        try {
          await createOrderRequest({
            name: product.name,
            shop: product.shop,
            unit_cost: unitCost,
            image_url: product.image_url,
            source_url: product.source_url,
            ip: product.ip,
            barcode: (collectionBarcode[index] || product.barcode || "").trim(),
            qty: Math.max(1, Number(collectionQty[index]) || 1),
            contact: contact.trim(),
            note: note.trim(),
          });
          ok += 1;
        } catch (err) {
          failures.push(`${product.name} → ${errorText(err)}`);
        }
      }
      if (ok) {
        setMessage(
          `已创建 ${ok} 条待付定金申请（需付定金合计约 ${formatYen(selectedDepositTotal.deposit)}）。确认付款后才会正式提交。`,
        );
        clearCollection();
        setScrapeUrlValue("");
        await loadPendingMine();
        await loadRequests();
      }
      if (failures.length) {
        setError(failures.slice(0, 5).join("\n"));
      }
    } finally {
      setScrapeBusy(false);
    }
  }

  async function onConfirmDeposit(code: string) {
    setDepositBusy(code);
    setError("");
    try {
      await confirmDeposit(code);
      setMessage(`定金已确认，${code} 已正式提交`);
      await loadPendingMine();
      await loadRequests();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setDepositBusy("");
    }
  }

  async function onConfirmAllDeposits() {
    if (!pendingMine.length) return;
    setScrapeBusy(true);
    setError("");
    let ok = 0;
    try {
      for (const req of pendingMine) {
        try {
          await confirmDeposit(req.request_code);
          ok += 1;
        } catch (err) {
          setError(`${req.request_code} → ${errorText(err)}`);
          break;
        }
      }
      if (ok) setMessage(`已确认 ${ok} 笔定金并正式提交`);
      await loadPendingMine();
      await loadRequests();
    } finally {
      setScrapeBusy(false);
    }
  }

  return (
    <div className="apply-page apply-page-wide">
      <header className="apply-hero">
        <div className="apply-hero-main">
          <p className="apply-brand">Stockgood</p>
          <h1>订单申请</h1>
          <p className="apply-lead">
            批量粘贴商品链接抓取后勾选提交；下方可查看已申请订单进度。
          </p>
        </div>
        <div className="apply-account">
          {authUser ? (
            <>
              <span className="apply-account-name" title={authUser.email}>
                {authUser.display_name || authUser.email}
              </span>
              <a className="apply-account-link" href="/me">
                下单历史
              </a>
            </>
          ) : (
            <a className="apply-account-link" href="/me">
              登录查看我的申请
            </a>
          )}
        </div>
      </header>

      <section className="apply-panel">
        <h2>提交申请</h2>
        <p className="muted">
          须登录后提交。创建后为「待付定金」，支付商品金额 {Math.round(depositRate * 100)}%
          定金并确认后才会正式提交（后续对接财务系统自动确认）。
        </p>
        {!authUser ? (
          <p className="error">
            未登录不可提交。请先{" "}
            <a href="/me">登录 / 注册</a>
            。
          </p>
        ) : null}
        <div className="scrape-bar scrape-bar-batch">
          <label className="grow">
            URL 列表
            <textarea
              rows={5}
              value={scrapeUrlValue}
              onChange={(e) => setScrapeUrlValue(e.target.value)}
              placeholder={
                "每行一个链接，例如：\nhttps://jumpcs.shueisha.co.jp/shop/g/g4530430540549/\nhttps://animegood.shop/products/xxx"
              }
            />
          </label>
          <div className="scrape-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={scrapeBusy}
              onClick={() => void onScrape()}
            >
              {scrapeBusy
                ? "抓取中…"
                : `批量抓取（${parseScrapeUrls(scrapeUrlValue).length || 0}）`}
            </button>
            {collection.length > 0 && (
              <button type="button" className="btn" onClick={clearCollection}>
                清空清单
              </button>
            )}
          </div>
        </div>

        {error ? <p className="error" style={{ whiteSpace: "pre-wrap" }}>{error}</p> : null}
        {message ? <p className="ok-msg">{message}</p> : null}

        {collection.length > 0 && (
          <div className="collection-box">
            <div className="form-grid">
              <label>
                ID编号（可选）
                <input
                  value={contact}
                  onChange={(e) => setContact(e.target.value)}
                  placeholder="你的 ID"
                />
              </label>
              <label>
                备注（可选）
                <input
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="规格、颜色等"
                />
              </label>
            </div>
            <div className="toolbar">
              <span className="muted">
                清单 {collection.length} 条，已选 {collectionPick.length}
                {collectionPick.length > 0
                  ? ` · 商品合计 ${formatYen(selectedDepositTotal.goods)} · 定金 ${selectedDepositTotal.ratePct}% ${formatYen(selectedDepositTotal.deposit)}`
                  : ""}
              </span>
              <button
                type="button"
                className="btn"
                onClick={() =>
                  setCollectionPick(collection.map((_, index) => index))
                }
              >
                全选
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => setCollectionPick([])}
              >
                取消勾选
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={scrapeBusy || !authUser}
                onClick={() => void onSubmitRequests()}
                title={!authUser ? "请先登录" : undefined}
              >
                {scrapeBusy ? "提交中…" : "创建待付定金申请"}
              </button>
            </div>
            <div className="collection-list">
              {collection.map((product, index) => (
                <div
                  className="collection-row"
                  key={`${product.source_url}-${index}`}
                >
                  <label className="collection-main">
                    <input
                      type="checkbox"
                      checked={collectionPick.includes(index)}
                      onChange={() =>
                        setCollectionPick((current) =>
                          current.includes(index)
                            ? current.filter((value) => value !== index)
                            : [...current, index],
                        )
                      }
                    />
                    {product.image_url ? (
                      <img
                        className="thumb"
                        src={product.image_url}
                        alt=""
                        referrerPolicy="no-referrer"
                      />
                    ) : (
                      <span className="thumb placeholder" />
                    )}
                    <span>
                      <strong>{product.name}</strong>
                      <span className="muted">
                        {" "}
                        · {product.shop}
                        {product.unit_cost != null
                          ? ` · ¥${product.unit_cost}`
                          : " · 无标价"}
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
                  <label className="collection-qty">
                    数量
                    <input
                      type="number"
                      min={1}
                      value={collectionQty[index] || "1"}
                      disabled={!collectionPick.includes(index)}
                      onChange={(e) =>
                        setCollectionQty({
                          ...collectionQty,
                          [index]: e.target.value,
                        })
                      }
                    />
                  </label>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {authUser && pendingMine.length > 0 ? (
        <section className="apply-panel">
          <div className="apply-list-head">
            <h2>待付定金</h2>
            <button
              type="button"
              className="btn btn-primary"
              disabled={scrapeBusy}
              onClick={() => void onConfirmAllDeposits()}
            >
              全部确认已付并提交
            </button>
          </div>
          <p className="muted">
            财务系统对接前，可手动确认定金（{Math.round(depositRate * 100)}%）。确认后订单才会进入「已提交」。
          </p>
          <div className="order-table apply-order-table">
            <div className="order-table-head apply-order-head apply-order-head-deposit">
              <span>订单号</span>
              <span>定金</span>
              <span />
            </div>
            {pendingMine.map((req) => (
              <div className="apply-order-row apply-order-row-deposit" key={req.request_code}>
                <span className="apply-order-ref" title={req.name}>
                  {orderNo(req)}
                </span>
                <span>{formatYen(req.deposit_amount)}</span>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={depositBusy === req.request_code || scrapeBusy}
                  onClick={() => void onConfirmDeposit(req.request_code)}
                >
                  {depositBusy === req.request_code ? "确认中…" : "确认已付定金"}
                </button>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="apply-panel">
        <div className="apply-list-head">
          <h2>已申请订单</h2>
          <div className="toolbar apply-list-toolbar">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">全部状态</option>
              <option value="submitted">已提交</option>
              <option value="ordered">已下单</option>
              <option value="rejected">已拒绝</option>
            </select>
            <button
              type="button"
              className="btn"
              onClick={() => void loadRequests()}
            >
              刷新
            </button>
          </div>
        </div>
        <p className="muted">
          {listLoading ? "加载中…" : `${requests.length} 个订单`}
        </p>
        {listError ? <p className="error">{listError}</p> : null}
        <div className="order-table apply-order-table">
          <div className="order-table-head apply-order-head">
            <span>订单号</span>
            <span>状态</span>
            <span>金额</span>
          </div>
          {requests.length === 0 && !listLoading ? (
            <div className="empty">暂无申请</div>
          ) : (
            requests.map((req) => (
              <div className="apply-order-row" key={req.request_code}>
                <span
                  className="apply-order-ref"
                  title={
                    req.shop_order_ref
                      ? `${req.name} · 店铺注文 ${req.shop_order_ref}`
                      : req.name
                  }
                >
                  {orderNo(req)}
                </span>
                <span className={`pill status-${req.status}`}>
                  {req.status_label || req.status}
                </span>
                <span>{formatYen(amountOf(req))}</span>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}
