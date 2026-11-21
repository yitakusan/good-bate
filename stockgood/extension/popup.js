const API = "http://127.0.0.1:8002";
const HOST = "com.stockgood.launcher";

const statusEl = document.getElementById("status");
const hintEl = document.getElementById("hint");
const idEl = document.getElementById("ext-id");
const resultEl = document.getElementById("result");
const retryBtn = document.getElementById("retry");
const startBtn = document.getElementById("start");

function setStatus(text) {
  statusEl.textContent = text;
}

function showOfflineHelp() {
  hintEl.hidden = false;
  hintEl.textContent = "请先打开服务: 在项目目录双击 启动.bat。若要让插件自己拉起, 把下面的扩展 ID 交给 extension\\注册拉起.bat, 只需做一次。";
  idEl.hidden = false;
  idEl.textContent = chrome.runtime.id;
  retryBtn.hidden = false;
  startBtn.hidden = false;
}

async function health() {
  try {
    const response = await fetch(API + "/api/health", { cache: "no-store" });
    return response.ok;
  } catch {
    return false;
  }
}

function startNative() {
  return new Promise((resolve) => {
    chrome.runtime.sendNativeMessage(HOST, { cmd: "start" }, (response) => {
      if (chrome.runtime.lastError || !response || !response.ok) {
        resolve(false);
        return;
      }
      resolve(true);
    });
  });
}

async function ensureService() {
  if (await health()) return true;
  setStatus("本地服务没开, 正在拉起…");
  hintEl.hidden = true;
  const started = await startNative();
  if (started && (await health())) return true;
  setStatus("本地服务没在运行");
  showOfflineHelp();
  return false;
}

function money(value) {
  if (value === null || value === undefined || value === "") return "";
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return "¥" + number.toLocaleString("zh-CN");
}

function renderResult(data) {
  resultEl.hidden = false;
  resultEl.replaceChildren();
  const meta = document.createElement("p");
  meta.className = "meta";
  const bits = [];
  if (data.order_ref) bits.push("订单号 " + data.order_ref);
  if (data.shipping_fee !== null && data.shipping_fee !== undefined) {
    bits.push("运费 " + money(data.shipping_fee));
  }
  if (data.order_total !== null && data.order_total !== undefined) {
    bits.push("合计 " + money(data.order_total));
  }
  meta.textContent = [data.message || "", bits.join(" · ")].filter(Boolean).join(" ");
  resultEl.append(meta);
  for (const product of data.products || []) {
    const row = document.createElement("div");
    row.className = "line";
    const name = document.createElement("div");
    name.className = "name";
    const qty = product.qty ? " × " + product.qty : "";
    const price = money(product.unit_cost);
    name.textContent = product.name + qty + (price ? "  " + price : "");
    row.append(name);
    if (product.source_url) {
      const link = document.createElement("a");
      link.href = product.source_url;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = product.source_url;
      row.append(link);
    }
    resultEl.append(row);
  }
}

async function scrape() {
  resultEl.hidden = true;
  hintEl.hidden = true;
  idEl.hidden = true;
  retryBtn.hidden = true;
  startBtn.hidden = true;
  const ready = await ensureService();
  if (!ready) return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.id || !tab.url || /^(chrome|edge|about|devtools):/.test(tab.url)) {
    setStatus("请先打开订单页面, 再点插件");
    retryBtn.hidden = false;
    return;
  }
  setStatus("正在读取当前页面…");
  let captured;
  try {
    const [got] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => ({
        url: location.href,
        html: document.documentElement ? document.documentElement.outerHTML : "",
      }),
    });
    captured = got && got.result;
  } catch {
    setStatus("读不到这个页面。请在订单详情页再试。");
    retryBtn.hidden = false;
    return;
  }
  if (!captured || !captured.html) {
    setStatus("页面还是空的。等订单详情出来后再点。");
    retryBtn.hidden = false;
    return;
  }
  setStatus("正在解析…");
  let response;
  try {
    response = await fetch(API + "/api/scrape", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ url: captured.url, html: captured.html }),
    });
  } catch {
    setStatus("本地服务没在运行");
    showOfflineHelp();
    return;
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "解析失败";
    setStatus(detail);
    retryBtn.hidden = false;
    return;
  }
  const count = (body.products || []).length;
  setStatus("已解析 " + count + " 种");
  renderResult(body);
}

retryBtn.addEventListener("click", () => {
  void scrape();
});
startBtn.addEventListener("click", () => {
  void scrape();
});
void scrape();
