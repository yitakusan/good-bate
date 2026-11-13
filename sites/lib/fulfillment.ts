export const unknown = "需确认";
export const stages = ["日本采购", "库存批次", "1210 保税仓入库", "淘宝全球购订单", "三单申报", "清关", "国内配送"];
export const exceptions = ["缺货", "数量不一致", "未填写发货时间", "长期未发货", "订单未申报", "资料缺失", "需要人工确认"];
export const statuses = {
  orderStatus: [unknown, "待下单", "已下单", "已发往仓库", "在库", "已发往用户", "已签收", "已取消", "缺货"],
  inventoryStatus: [unknown, "待到货", "部分到货", "在库", "已售罄", "冻结", "已出库", "缺货"],
  bondedStatus: [unknown, "待入仓", "入仓中", "已入仓", "入仓异常"],
  declarationStatus: [unknown, "待申报", "申报中", "已申报", "申报退回"],
  customsStatus: [unknown, "待清关", "清关中", "已放行", "清关异常"],
  deliveryStatus: [unknown, "待发货", "配送中", "已签收", "配送异常"],
  compliance: [unknown, "审核中", "已核验", "受限"],
  followup: ["待跟进", "跟进中", "已处理", unknown],
};
export const statusMap: Record<string, string> = {
  ordered: "已下单", inbound_shipped: "已发往仓库", in_transit: "已发往仓库", in_stock: "在库",
  outbound_shipped: "已发往用户", delivered: "已签收", cancelled: "已取消",
};
export const labels: Record<string, string> = {
  orderRef:"采购订单号", shop:"采购店铺", orderedAt:"下单日期", orderQty:"订单总件数", shippingFee:"订单运费 (JPY)",
  exchangeRate:"下单汇率 (CNY/JPY)", orderImageUrl:"订单图片 URL", orderNote:"订单备注", stockgoodOrderStatus:"原订单状态",
  orderExpectedAt:"订单头预计发货", orderExpectedPeriod:"订单头旬别", name:"商品名称", sku:"SKU", ip:"IP",
  category:"商品品类", barcode:"条码 / JAN", qty:"采购件数", unitCost:"采购单价 (JPY)", imageUrl:"商品图片 URL",
  sourceUrl:"商品链接", brand:"品牌", hsCode:"HS 编码", declarationElements:"申报要素", compliance:"品牌 / IP 合规",
  batch:"采购批次", box:"箱号", tracking:"物流单号", inboundTracking:"进库单号", outboundTracking:"出库单号",
  arrivedAt:"到货日期", arrivedQty:"已到货件数", stockQty:"库存件数", sellableQty:"可售件数", inventoryStatus:"库存状态",
  bondedStatus:"保税仓状态", tbOrder:"淘宝全球购订单号", orderStatus:"订单状态", declarationStatus:"申报状态",
  orderDocument:"订单回执 / 编号", paymentDocument:"支付单回执 / 编号", logisticsDocument:"物流单回执 / 编号",
  customsStatus:"清关状态", deliveryStatus:"国内配送状态", domesticTracking:"国内运单号",
  expectedAt:"预计发货 (YYYY-MM 或 YYYY-MM-DD)", expectedPeriod:"明细旬别", shippedAt:"实际采购发货",
  delayReason:"延期原因", followup:"人工跟进", owner:"责任人", note:"明细备注", stockgoodOrderId:"原订单 ID",
  stockgoodLineId:"原明细 ID", animegoodProductId:"Animegood 商品 ID", warehouseId:"原仓库 ID",
  inboundCarrier:"进库承运商", outboundCarrier:"出库承运商", inboundTrackingUrl:"进库查询链接", outboundTrackingUrl:"出库查询链接",
  inboundShipmentId:"进库物流记录 ID", outboundShipmentId:"出库物流记录 ID", outboundBox:"原出库箱号",
  originalOrder:"原始订单补充字段", originalLine:"原始明细补充字段", purchaseLink:"关联采购记录 ID",
};
export const kinds = { purchase:"采购明细", catalog:"商品 / SKU", fulfillment:"履约订单" };
export type Kind = keyof typeof kinds;
export type Fields = Record<string, string>;
export type Entry = { id:string; kind:Kind; fields:Fields; manual:string[]; updatedAt:string; revision:number };
export const numeric = ["qty","orderQty","unitCost","shippingFee","exchangeRate","arrivedQty","stockQty","sellableQty"];
export const integer = new Set(["qty","orderQty","arrivedQty","stockQty","sellableQty"]);
export const periods = { early:"上旬", mid:"中旬", late:"下旬" };
export const normalizePeriod = (value:string) => Object.keys(periods).find(k => k === value || periods[k as keyof typeof periods] === value) ?? value;
export const number = (s?:string) => s !== undefined && s.trim() !== "" && Number.isFinite(Number(s)) ? Number(s) : null;
export const value = (f:Fields,k:string) => f[k] || unknown;
export const today = () => new Intl.DateTimeFormat("sv-SE", {timeZone:"Asia/Tokyo",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());
const iso = (d:Date) => d.toISOString().slice(0,10);
const day = 86_400_000;
const diff = (end:string, start:string) => Math.round((Date.parse(end) - Date.parse(start)) / day);
export function moveMonth(date:string, offset:number) {
  const [y,m,d] = date.split("-").map(Number);
  const last = new Date(Date.UTC(y,m+offset,0)).getUTCDate();
  return iso(new Date(Date.UTC(y,m+offset-1,Math.min(d,last))));
}
export function dateRange(raw?:string, period?:string): [string,string] | null {
  const s = raw?.trim() ?? "";
  if (/^\d{4}-\d{2}-\d{2}(?:T.+| .+)?$/.test(s)) {
    const d = s.slice(0,10);
    const t = Date.parse(d);
    return Number.isFinite(t) && iso(new Date(t)) === d ? [d,d] : null;
  }
  if (!/^\d{4}-(?:0[1-9]|1[0-2])$/.test(s)) return null;
  const [y,m] = s.split("-").map(Number);
  if (y < 1000) return null;
  const last = new Date(Date.UTC(y,m,0)).getUTCDate();
  const p = normalizePeriod(period ?? "");
  if (p === "early") return [s+"-01",s+"-10"];
  if (p === "mid") return [s+"-11",s+"-20"];
  if (p === "late") return [s+"-21",s+"-"+last];
  return [s+"-01",s+"-"+last];
}
export function estimate(f:Fields) {
  return f.expectedAt ? dateRange(f.expectedAt,f.expectedPeriod) : dateRange(f.orderExpectedAt,f.orderExpectedPeriod);
}
export function estimatedLabel(f:Fields) {
  const dt = f.expectedAt || f.orderExpectedAt;
  if (!dt || !estimate(f)) return unknown;
  const p = normalizePeriod(f.expectedAt ? f.expectedPeriod || "" : f.orderExpectedPeriod || "");
  return dt + (dt.length === 7 && p in periods ? " · " + periods[p as keyof typeof periods] : "");
}
const finalPurchase = new Set(["已发往仓库","在库","已发往用户","已签收","已取消"]);
const hasSales = (entry:Entry) => entry.kind === "fulfillment" || Boolean(entry.fields.tbOrder && entry.fields.tbOrder !== unknown);
const needsDeclaration = (entry:Entry) => hasSales(entry) && entry.fields.orderStatus !== "已取消" && ["",unknown,"待申报","申报退回"].includes(entry.fields.declarationStatus ?? "");
export function classify(e:Entry, now:string) {
  const f = e.fields, pending = e.kind === "purchase" && !finalPurchase.has(f.orderStatus) && !dateRange(f.shippedAt) && !dateRange(f.arrivedAt) && !(Number(f.arrivedQty) > 0 && Number(f.arrivedQty) >= Number(f.qty));
  const order = dateRange(f.orderedAt), expected = estimate(f);
  const threshold = order && moveMonth(order[0],6);
  const latestThreshold = order && moveMonth(order[1],6);
  const cycle = threshold && latestThreshold && expected ? expected[0] >= latestThreshold ? "long" : expected[1] >= threshold ? "uncertain" : "normal" : "uncertain";
  const delay = pending && expected ? Math.max(0,diff(now,expected[1])) : 0;
  const arrival = number(f.arrivedQty), qty = number(f.qty);
  const flags = new Set(e.manual);
  if (f.orderStatus !== "已取消" && e.kind !== "catalog") {
    if (f.orderStatus === "缺货" || f.inventoryStatus === "缺货") flags.add(exceptions[0]);
    if (qty !== null && arrival !== null && (arrival > qty || (["在库","已发往用户","已签收"].includes(f.orderStatus) && arrival !== qty))) flags.add(exceptions[1]);
    if (pending && !expected) flags.add(exceptions[2]);
    if (pending && (delay >= 30 || (!expected && threshold && now >= threshold))) flags.add(exceptions[3]);
    if (needsDeclaration(e)) flags.add(exceptions[4]);
    if (hasSales(e) && [f.hsCode,f.declarationElements,f.orderDocument,f.paymentDocument,f.logisticsDocument].some(v => !v || v === unknown)) flags.add(exceptions[5]);
    if (value(f,"orderStatus") === unknown || (hasSales(e) && value(f,"compliance") !== "已核验") || f.followup === unknown) flags.add(exceptions[6]);
  }
  if (f.compliance === "受限" && f.orderStatus !== "已取消") flags.add(exceptions[6]);
  const severe = f.orderStatus !== "已取消" && (["入仓异常","申报退回","清关异常","配送异常","受限"].some(s => Object.values({
    bonded:f.bondedStatus, declaration:f.declarationStatus, customs:f.customsStatus, delivery:f.deliveryStatus, compliance:f.compliance,
  }).includes(s)));
  if (severe) flags.add(exceptions[6]);
  const priority = severe || delay >= 30 || flags.has(exceptions[0]) ? 3 : delay > 0 || flags.has(exceptions[1]) || flags.has(exceptions[4]) || flags.has(exceptions[5]) ? 2 : flags.size ? 1 : 0;
  return {flags:[...flags], delay, cycle, pending, priority, declaration:needsDeclaration(e)};
}
export function stage(e:Entry):number {
  const f = e.fields;
  if (e.kind === "catalog" || f.orderStatus === "已取消") return -1;
  if (f.deliveryStatus === "已签收") return 7;
  if (["已放行"].includes(f.customsStatus) || ["配送中","配送异常"].includes(f.deliveryStatus)) return 6;
  if (["清关中","清关异常"].includes(f.customsStatus) || f.declarationStatus === "已申报") return 5;
  if (["申报中","申报退回","待申报"].includes(f.declarationStatus) || (f.tbOrder && f.tbOrder !== unknown)) return 4;
  if (e.kind === "fulfillment" || f.bondedStatus === "已入仓") return 3;
  if (["待入仓","入仓中","入仓异常"].includes(f.bondedStatus)) return 2;
  if ((f.batch && f.batch !== unknown) || (number(f.arrivedQty) ?? 0) > 0 || dateRange(f.arrivedAt)) return 1;
  return 0;
}
export const entryKey = (e:Entry) => e.fields.tbOrder && e.fields.tbOrder !== unknown ? "tb:"+e.fields.tbOrder : e.fields.orderRef && e.fields.orderRef !== unknown ? "jp:"+(e.fields.shop??"")+"/"+e.fields.orderRef : e.id;
export function totals(entries:Entry[], date:string) {
  const purchase = entries.filter(e => e.kind === "purchase" && e.fields.orderStatus !== "已取消");
  const operational = entries.filter(e => e.kind !== "catalog" && e.fields.orderStatus !== "已取消");
  const skus = new Set(entries.filter(e => e.fields.orderStatus !== "已取消").map(({fields:f}) => f.sku || f.barcode).filter(s => s && s !== unknown));
  const sum = (key:string) => purchase.reduce((acc,e) => acc + (number(e.fields[key]) ?? 0),0);
  const count = (flag:"delay"|"declaration") => new Set(operational.filter(e => classify(e,date)[flag]).map(e => flag === "delay" && e.fields.orderRef && e.fields.orderRef !== unknown ? "jp:"+(e.fields.shop??"")+"/"+e.fields.orderRef : entryKey(e))).size;
  return { sku:skus.size, qty:sum("qty"), cost:purchase.reduce((n,e) => n+((number(e.fields.qty)??0)*(number(e.fields.unitCost)??0)),0),
    arrived:sum("arrivedQty"), sellable:purchase.filter(e => !["冻结","已售罄","已出库","缺货"].includes(e.fields.inventoryStatus)).reduce((n,e) => n+(number(e.fields.sellableQty)??0),0),
    declare:count("declaration"), overdue:count("delay"), issues:entries.filter(e => classify(e,date).flags.length).length,
  };
}

export function parseEntry(input:unknown):Entry {
  if (!input || typeof input !== "object") throw new Error("记录格式无效");
  const {id,kind,fields,manual=[],revision=0,updatedAt=""} = input as Entry;
  if (typeof id !== "string" || !/^[a-z0-9:_-]{1,128}$/i.test(id) || !Object.hasOwn(kinds,kind) || !fields || typeof fields !== "object" || Array.isArray(fields)) throw new Error("记录编号或类型无效");
  const cleaned:Fields = {};
  for (const [key,s] of Object.entries(fields)) {
    if (!Object.hasOwn(labels,key) || typeof s !== "string" || s.length > (key.startsWith("original") ? 18000 : 2000)) throw new Error("字段无效或内容过长：" + key);
    if (s.trim()) cleaned[key] = s.trim();
  }
  if (!cleaned.name) throw new Error("请填写商品名称");
  if (kind === "catalog" && (!cleaned.sku || cleaned.sku === unknown)) throw new Error("商品档案需要填写 SKU");
  if (!Array.isArray(manual) || manual.some(flag => !exceptions.includes(flag))) throw new Error("异常类型无效");
  for (const key of numeric) {
    const s = cleaned[key];
    if (!s || s === unknown) continue;
    const n = number(s);
    if (n === null || n < 0 || n > 1e12 || (integer.has(key) && !Number.isInteger(n)) || (["qty","exchangeRate"].includes(key) && n === 0)) throw new Error(labels[key]+"格式无效");
  }
  if (number(cleaned.sellableQty) !== null && number(cleaned.stockQty) !== null && Number(cleaned.sellableQty) > Number(cleaned.stockQty)) throw new Error("可售件数超过库存件数");
  for (const key of ["orderedAt","arrivedAt","expectedAt","orderExpectedAt","shippedAt"]) {
    if (cleaned[key] && cleaned[key] !== unknown && !dateRange(cleaned[key])) throw new Error(labels[key]+"格式无效");
  }
  return {id,kind,fields:cleaned,manual:[...new Set(manual)],revision:Number.isSafeInteger(revision)&&revision>=0?revision:0,updatedAt:typeof updatedAt==="string"?updatedAt:""};
}
