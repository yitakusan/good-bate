import { labels, parseEntry, kinds, statusMap, exceptions, unknown, type Entry, type Fields, type Kind } from "./fulfillment";

const aliases:Record<string,string> = {
  "订单号":"orderRef","品名":"name","品类":"category","商品类型":"category","数量":"qty","采购价":"unitCost","库存数量":"stockQty",
  "已到货数量":"arrivedQty","可售库存":"sellableQty","预计发货":"expectedAt","品牌/IP 合规状态":"compliance","商品 SKU":"sku",
  order_ref:"orderRef",ordered_at:"orderedAt",order_qty:"orderQty",shipping_fee:"shippingFee",exchange_rate:"exchangeRate",
  order_image_url:"orderImageUrl",unit_cost:"unitCost",product_kind:"category",image_url:"imageUrl",source_url:"sourceUrl",
  expected_ship_at:"expectedAt",expected_ship_period:"expectedPeriod",arrived_at:"arrivedAt",status:"orderStatus",
  animegood_product_id:"animegoodProductId",warehouse_id:"warehouseId",order_id:"stockgoodOrderId",
  inbound_tracking_no:"inboundTracking",outbound_tracking_no:"outboundTracking",outbound_box_no:"outboundBox",
  inbound_carrier:"inboundCarrier",outbound_carrier:"outboundCarrier",inbound_tracking_url:"inboundTrackingUrl",
  outbound_tracking_url:"outboundTrackingUrl",inbound_shipment_id:"inboundShipmentId",outbound_shipment_id:"outboundShipmentId",stock_box_no:"box",
};
const headers = Object.fromEntries(Object.entries(labels).map(([key,label]) => [label,key]));
const csvColumns = ["记录 ID","记录类型",...Object.values(labels),"异常类型","更新时间"];
const csvCell = (input:string) => {
  const text = /^[=+\-@\t\r]/.test(input) || input.startsWith("'") ? "'"+input : input;
  return '"' + text.replaceAll('"','""') + '"';
};
const unescapeCell = (s:string) => /^'['=+\-@\t\r]/.test(s) ? s.slice(1) : s;
export function toCSV(entries:Entry[]) {
  return "\ufeff"+[csvColumns,...entries.map(e => [e.id,kinds[e.kind],...Object.keys(labels).map(k => e.fields[k]??""),e.manual.join("；"),e.updatedAt])].map(row => row.map(csvCell).join(",")).join("\r\n");
}
function csvRows(source:string) {
  const rows:string[][] = [];
  let row:string[] = [], cell = "", quoted = false, closed = false;
  const endCell = () => {row.push(unescapeCell(cell)); cell = ""; closed = false;};
  for (let i=0;i<source.length;i++) {
    const c = source[i];
    if (quoted) {
      if (c === '"' && source[i+1] === '"') {cell += '"'; i++;}
      else if (c === '"') {quoted = false; closed = true;}
      else cell += c;
      continue;
    }
    if (c === ",") {endCell(); continue;}
    if (c === "\n" || c === "\r") {
      if (c === "\r" && source[i+1] === "\n") i++;
      endCell(); rows.push(row); row = []; continue;
    }
    if (closed) throw new Error("CSV 引号后的字符无效");
    if (c === '"') {
      if (cell) throw new Error("CSV 引号位置无效");
      quoted = true;
    } else cell += c;
  }
  if (quoted) throw new Error("CSV 引号未闭合");
  if (row.length || cell || closed) {endCell(); rows.push(row);}
  return rows.filter(r => r.some(v => v.trim()));
}

type Row = Record<string,unknown>;
const str = (value:unknown) => typeof value === "string" || typeof value === "number" ? String(value) : "";
const purchaseFields = {id:"stockgoodOrderId",order_ref:"orderRef",shop:"shop",status:"stockgoodOrderStatus",ordered_at:"orderedAt",order_qty:"orderQty",
  shipping_fee:"shippingFee",exchange_rate:"exchangeRate",order_image_url:"orderImageUrl",note:"orderNote",
  expected_ship_at:"orderExpectedAt",expected_ship_period:"orderExpectedPeriod",warehouse_id:"warehouseId"};
const isRow = (data:unknown):data is Row => !!data && typeof data === "object" && !Array.isArray(data);
function mapped(row:Row, mapping:Record<string,string>):Fields {
  return Object.fromEntries(Object.entries(row).flatMap(([k,v]) => {
    const target = mapping[k];
    return target && str(v) ? [[target,str(v)]] : [];
  }));
}
function stockgood(order:Row,line:Row):Row {
  const lineMap = {...aliases,id:"stockgoodLineId",name:"name",shop:"shop",qty:"qty",note:"note",ip:"ip",barcode:"barcode"};
  const fields = {...mapped(order,purchaseFields),...mapped(line,lineMap)};
  const oldId = str(order.id || line.order_id || order.order_ref);
  const lineId = str(line.id);
  const raw = (data:Row, keys:Record<string,string>) => JSON.stringify(Object.fromEntries(Object.entries(data).filter(([k]) => k !== "lines" && !Object.hasOwn(keys,k))));
  return {
    id:lineId ? "stockgood:"+(oldId || "legacy")+":"+lineId : undefined,
    kind:"purchase", fields:{...fields,sku:str(line.sku || line.barcode),box:str(line.stock_box_no ?? line.outbound_box_no),tracking:str(line.outbound_tracking_no || line.inbound_tracking_no),originalOrder:raw(order,purchaseFields),originalLine:raw(line,lineMap)},
  };
}
async function stableId(kind:Kind,f:Fields) {
  const basis = kind === "catalog" ? [f.sku] : kind === "fulfillment" ? [f.tbOrder,f.sku||f.name] : [f.shop,f.orderRef,f.batch,f.sku||f.barcode||f.name,f.stockgoodLineId];
  if (!basis.some(Boolean)) return crypto.randomUUID();
  const hash = await crypto.subtle.digest("SHA-256",new TextEncoder().encode(JSON.stringify([kind,basis])));
  return kind+":"+Array.from(new Uint8Array(hash),b => b.toString(16).padStart(2,"0")).join("").slice(0,32);
}
async function importRow(row:Row) {
  const kindText = str(row.kind ?? row["记录类型"]);
  const resolvedKind = Object.entries(kinds).find(([k,label]) => kindText === k || kindText === label)?.[0];
  if (kindText && !resolvedKind) throw new Error("记录类型无效");
  const kind = (resolvedKind ?? "purchase") as Kind;
  const nested = isRow(row.fields);
  const fields:Fields = {};
  for (const [key,data] of Object.entries(nested ? row.fields as Row : row)) {
    const camel = key.replace(/_([a-z])/g, (_,letter:string) => letter.toUpperCase());
    const target = aliases[key] ?? headers[key] ?? camel;
    if (Object.hasOwn(labels,target)) fields[target] = str(data);
  }
  if (fields.orderStatus && statusMap[fields.orderStatus]) fields.orderStatus = statusMap[fields.orderStatus];
  if (!fields.orderStatus && fields.stockgoodOrderStatus) fields.orderStatus = statusMap[fields.stockgoodOrderStatus] ?? unknown;
  const origin = str(row.manual ?? row["异常类型"]);
  const manual = Array.isArray(row.manual) ? row.manual : origin.split(/[;；、]/).map(s => s.trim()).filter(Boolean);
  if (manual.some(flag => !exceptions.includes(flag))) throw new Error("异常类型无效");
  const given = str(row.id ?? row["记录 ID"]);
  return parseEntry({id:given || await stableId(kind,fields),kind,fields,manual,revision:0});
}

export async function readImport(source:string,name:string) {
  let raw:unknown;
  const input = source.replace(/^\ufeff/,"").trim();
  if (!input) throw new Error("文件为空");
  if (name.toLowerCase().endsWith(".csv")) {
    const [cols,...rows] = csvRows(input);
    if (!cols || !rows.length) throw new Error("CSV 需要列标题和至少一行数据");
    if (new Set(cols).size !== cols.length) throw new Error("CSV 有重复列标题");
    raw = rows.map((row,i) => {
      if (row.length !== cols.length) throw new Error("第 "+(i+2)+" 行列数与标题不一致");
      return Object.fromEntries(cols.map((k,j) => [k.trim(),row[j]]));
    });
  } else {
    const parsed = JSON.parse(input);
    raw = Array.isArray(parsed) ? parsed : isRow(parsed) ? parsed.entries ?? parsed.orders ?? parsed.items ?? (Array.isArray(parsed.lines) ? [parsed] : null) : null;
  }
  if (!Array.isArray(raw)) throw new Error("JSON 需要记录数组、entries、orders 或 items");
  const flattened:Row[] = [];
  for (const row of raw) {
    if (!isRow(row)) throw new Error("记录需要是对象");
    if (Array.isArray(row.lines)) {
      if (!row.lines.length) throw new Error("Stockgood 订单缺少明细");
      for (const line of row.lines) {
        if (!isRow(line)) throw new Error("Stockgood 明细格式无效");
        flattened.push(stockgood(row,line));
      }
    } else if ("order_id" in row && "id" in row && !("fields" in row)) {
      flattened.push(stockgood({},row));
    } else flattened.push(row);
  }
  if (!flattened.length || flattened.length > 2500) throw new Error("每个文件支持 1 至 2500 行记录");
  const entries = await Promise.all(flattened.map(async (row,i) => {
    try {return await importRow(row);}
    catch(error) {throw new Error("第 "+(i+1)+" 条："+(error instanceof Error ? error.message : "格式无效"));}
  }));
  if (new Set(entries.map(e => e.id)).size !== entries.length) throw new Error("文件内有相同记录。请为同订单、同 SKU 的多条明细指定不同记录 ID。");
  return entries;
}
