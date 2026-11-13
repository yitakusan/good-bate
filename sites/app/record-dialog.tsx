"use client";
import { useEffect, useRef, useState } from "react";
import { X, Save, PackagePlus } from "lucide-react";
import { exceptions, kinds, labels, numeric, periods, statuses, type Entry, type Kind } from "../lib/fulfillment";

const groups = [
  ["商品与采购",["name","sku","ip","category","brand","barcode","qty","unitCost","orderRef","shop","orderedAt","orderStatus","imageUrl","sourceUrl"]],
  ["库存与保税仓",["batch","box","tracking","arrivedAt","arrivedQty","stockQty","sellableQty","inventoryStatus","bondedStatus","inboundTracking","outboundTracking"]],
  ["淘宝履约与三单申报",["tbOrder","purchaseLink","compliance","hsCode","declarationElements","orderDocument","paymentDocument","logisticsDocument","declarationStatus","customsStatus","deliveryStatus","domesticTracking"]],
  ["预计发货与跟进",["expectedAt","expectedPeriod","shippedAt","delayReason","followup","owner","note"]],
  ["Stockgood 原订单字段",["orderQty","shippingFee","exchangeRate","orderImageUrl","orderNote","stockgoodOrderStatus","orderExpectedAt","orderExpectedPeriod","stockgoodOrderId","stockgoodLineId","animegoodProductId","warehouseId","inboundCarrier","outboundCarrier","inboundTrackingUrl","outboundTrackingUrl","inboundShipmentId","outboundShipmentId","outboundBox","originalOrder","originalLine"]],
] as const;
const catalog = [["商品与 SKU",["name","sku","ip","category","brand","barcode","unitCost","imageUrl","sourceUrl","compliance","hsCode","declarationElements","owner","note"]]] as const;
const multi = new Set(["note","orderNote","declarationElements","delayReason","originalOrder","originalLine"]);
export default function RecordDialog({entry,entries,readonly,onClose,onSave}:{entry:Entry;entries:Entry[];readonly:boolean;onClose:()=>void;onSave:(e:Entry)=>Promise<void>}) {
  const [draft,setDraft] = useState(entry);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {ref.current?.showModal();},[]);
  const update = (key:string,val:string) => setDraft(e => ({...e,fields:{...e.fields,[key]:val}}));
  const options = (key:string) => {
    if (key === "expectedPeriod" || key === "orderExpectedPeriod") return Object.entries(periods);
    const choices = statuses[key as keyof typeof statuses];
    return choices?.map(s => [s,s]);
  };
  const visibleGroups = draft.kind === "catalog" ? catalog : groups;
  async function submit(event:React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {await onSave(draft);}
    catch(e) {setError(e instanceof Error ? e.message : "保存失败");}
    finally {setBusy(false);}
  }
  return <dialog ref={ref} className="drawer" onCancel={e => {e.preventDefault(); if(!busy) onClose();}}>
    <form onSubmit={submit} className="drawer-form">
      <header className="drawer-head"><div className="drawer-icon"><PackagePlus size={21}/></div><div><h2>{readonly ? "示例记录" : entry.revision ? "编辑记录" : "新建记录"}</h2><p>{readonly ? "示例仅供查看。请切换到运营台账录入实际数据。" : "保存后自动更新看板、统计和异常优先级。"}</p></div><button type="button" className="icon-button" aria-label="关闭" onClick={onClose} disabled={busy}><X size={20}/></button></header>
      <div className="drawer-body">
        <fieldset disabled={readonly||busy}>
          <label className="kind-label">记录类型<select value={draft.kind} disabled={entry.revision>0} onChange={e => setDraft({...draft,kind:e.target.value as Kind})}>{Object.entries(kinds).map(([k,label])=><option key={k} value={k}>{label}</option>)}</select></label>
          {visibleGroups.map(([title,keys],index)=><details key={title} open={index===0 || (index===3 && !!entry.fields.expectedAt) ? true : undefined}><summary>{title}</summary><div className="form-grid">
            {keys.map(key=>{
              const val = draft.fields[key] || "";
              const list = options(key);
              const isRequired = key === "name" || (key === "sku" && draft.kind === "catalog");
              return <label key={key} className={multi.has(key) ? "wide" : ""}>{labels[key]}{isRequired && <span className="required"> *</span>}
                {list ? <select value={val} onChange={e=>update(key,e.target.value)}><option value="">需确认</option>{val&&!list.some(([k])=>k===val)&&<option value={val}>{val}</option>}{list.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select>
                : key === "purchaseLink" ? <select value={val} onChange={e=>{
                  const next=entries.find(item=>item.id===e.target.value);
                  setDraft(d=>({...d,fields:{...d.fields,purchaseLink:e.target.value,...(next?{name:next.fields.name,sku:next.fields.sku||"",batch:next.fields.batch||"",ip:next.fields.ip||"",category:next.fields.category||"",brand:next.fields.brand||"",hsCode:next.fields.hsCode||"",declarationElements:next.fields.declarationElements||"",compliance:next.fields.compliance||""}:{})}}));
                }}><option value="">选择采购记录</option>{val&&!entries.some(e=>e.id===val)&&<option value={val}>{val}</option>}{entries.filter(e=>e.kind==="purchase"&&e.id!==draft.id).map(e=><option key={e.id} value={e.id}>{e.fields.name} · {e.fields.batch||e.fields.orderRef||e.id}</option>)}</select>
                : multi.has(key) ? <textarea value={val} onChange={e=>update(key,e.target.value)} rows={3} maxLength={key.startsWith("original")?18000:2000}/>
                : <input required={isRequired} inputMode={numeric.includes(key)?"decimal":"text"} value={val} placeholder={key.endsWith("At")?"YYYY-MM-DD":undefined} maxLength={2000} onChange={e=>update(key,e.target.value)} list={key==="sku"&&draft.kind!=="catalog"?"known-skus":undefined} onBlur={key==="sku"&&draft.kind!=="catalog"?()=>{
                  const found=entries.find(e=>e.kind==="catalog"&&e.fields.sku===val);
                  if (found) setDraft(d=>({...d,fields:{...Object.fromEntries(["name","ip","category","barcode","brand","hsCode","declarationElements","compliance","unitCost"].map(k=>[k,found.fields[k]||""])),...Object.fromEntries(Object.entries(d.fields).filter(([,v])=>v))}}));
                }:undefined}/>}
              </label>;
            })}
          </div></details>)}
          <datalist id="known-skus">{entries.filter(e=>e.kind==="catalog").map(e=><option key={e.id} value={e.fields.sku}>{e.fields.name}</option>)}</datalist>
          <details><summary>手动标记异常</summary><div className="checkboxes">{exceptions.map(flag=><label key={flag}><input type="checkbox" checked={draft.manual.includes(flag)} onChange={e=>setDraft({...draft,manual:e.target.checked?[...draft.manual,flag]:draft.manual.filter(s=>s!==flag)})}/>{flag}</label>)}</div></details>
        </fieldset>
      </div>
      <footer className="drawer-foot">{error&&<p role="alert">{error}</p>}<button type="button" className="button" onClick={onClose} disabled={busy}>{readonly?"关闭":"取消"}</button>{!readonly&&<button type="submit" className="button primary" disabled={busy}><Save size={16}/>{busy?"正在保存":"保存记录"}</button>}</footer>
    </form>
  </dialog>;
}
