"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, AlertCircle, ArrowDown, ArrowLeftRight, ArrowRight, ArrowUp, Boxes, CalendarDays, ChevronDown, CircleCheck, Clock3, Database, Download, FileJson, FileSpreadsheet, FileText, GitBranch, LayoutDashboard, List, Package, PackageCheck, Plus, Search, SlidersHorizontal, Truck, Upload, Warehouse, X } from "lucide-react";
import { classify, estimatedLabel, exceptions, kinds, stage, stages, statuses, today, totals, unknown, value, type Entry, type Kind } from "../lib/fulfillment";
import { readImport, toCSV } from "../lib/exchange";
import { demoEntries } from "../lib/demo";
import RecordDialog from "./record-dialog";

const repo = "https://github.com/yitakusan/good-bate";
const branch = repo + "/tree/codex/stockgood-fulfillment-sites/sites";
const navigation = [
  {id:"overview",label:"履约总览",icon:LayoutDashboard},
  {id:"records",label:"全部记录",icon:List},
  {id:"inventory",label:"批次库存",icon:Warehouse},
  {id:"cycle",label:"高周转时长",icon:Clock3},
  {id:"exceptions",label:"异常中心",icon:AlertCircle},
] as const;
type View = typeof navigation[number]["id"];
const subtitles:Record<View,string> = {
  overview:"追踪日本采购、保税入仓与国内履约的每一步。",
  records:"统一维护采购明细、商品 SKU 和淘宝全球购订单。",
  inventory:"按采购批次核对到货、库存、可售数量和保税仓进度。",
  cycle:"追踪下单到预计发货达到 6 个自然月的采购记录。",
  exceptions:"集中处理异常，按严重度和延期天数排序。",
};
const filterDefs = [
  ["batch","采购批次"],["ip","IP"],["category","商品类型"],["orderStatus","订单状态"],["inventoryStatus","库存状态"],
  ["customsStatus","清关状态"],["bondedStatus","保税仓状态"],["delay","延期程度"],["exception","异常类型"],["kind","记录类型"],
] as const;
const delayOptions = ["未逾期","延期 1–7 天","延期 8–29 天","延期 30 天以上","需确认"];
const fmt = new Intl.NumberFormat("zh-CN",{maximumFractionDigits:2});
const priorityNames = ["正常","待确认","需跟进","高优先"];
const priorityClasses = ["neutral","blue","amber","red"];
const stageIcons = [Package,Boxes,Warehouse,FileText,FileSpreadsheet,CircleCheck,Truck];
const stageColors = ["#729af1","#67a28d","#2b936d","#6f81d5","#dfad57","#68a3ca","#40ae8c"];
const metricDefs = [
  ["sku","总 SKU","按 SKU / JAN 去重",Boxes,"green"],["qty","总件数","采购明细件数",Package,"blue"],["cost","采购金额","商品金额 · JPY",FileText,"green"],["arrived","已到货数量","累计登记到货",PackageCheck,"green"],
  ["sellable","可售库存","按登记可售件数",Warehouse,"green"],["declare","待申报订单","按订单号去重",FileSpreadsheet,"amber"],["overdue","延期订单","按采购订单去重",Clock3,"amber"],["issues","异常数量","存在异常的记录",AlertCircle,"red"],
] as const;

function saveFile(name:string,body:string,mime:string) {
  const url=URL.createObjectURL(new Blob([body],{type:mime}));
  const link=document.createElement("a");
  link.href=url; link.download=name; link.click();
  window.setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function request(action?:string, entries?:Entry[]) {
  const response=await fetch("/api/records",action ? {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action,entries})} : {cache:"no-store"});
  const result=await response.json().catch(()=>({})) as {error?:string;entries:Entry[];skipped?:number};
  if (!response.ok) throw Object.assign(new Error(result.error || "台账暂时无法访问"),{status:response.status});
  return result as {entries:Entry[];skipped?:number};
}

export default function Dashboard() {
  const [entries,setEntries]=useState<Entry[]>([]);
  const [loaded,setLoaded]=useState(false);
  const [demo,setDemo]=useState(false);
  const [samples,setSamples]=useState<Entry[]>([]);
  const [todayDate,setToday]=useState("");
  const [error,setError]=useState("");
  const [signedOut,setSignedOut]=useState(false);
  const [notice,setNotice]=useState("");
  const [view,setView]=useState<View>("overview");
  const [layout,setLayout]=useState<"board"|"table">("board");
  const [query,setQuery]=useState("");
  const [filters,setFilters]=useState<Record<string,string>>({});
  const [expanded,setExpanded]=useState(false);
  const [selectedStage,setSelectedStage]=useState<number|null>(null);
  const [cycleUncertain,setCycleUncertain]=useState(false);
  const [dialog,setDialog]=useState<Entry|null>(null);
  const [importData,setImportData]=useState<{name:string;entries:Entry[]}|null>(null);
  const [busy,setBusy]=useState(false);
  const [panel,setPanel]=useState<"sources"|"import"|null>(null);
  const [exportOpen,setExportOpen]=useState(false);
  const [pageSize,setPageSize]=useState(40);
  const fileRef=useRef<HTMLInputElement>(null);
  const panelRef=useRef<HTMLDialogElement>(null);
  const load=useCallback(async()=>{
    setError(""); setSignedOut(false);
    try {const result=await request(); setEntries(result.entries); setLoaded(true); return result.entries.length;}
    catch(e) {setSignedOut((e as {status?:number}).status===401); setError((e as Error).message); return -1;}
  },[]);
  useEffect(()=>{
    setToday(today()); setSamples(demoEntries());
    const timer=setInterval(()=>setToday(today()),60000);
    void load().then(count=>{if(count===0 || count===-1) setDemo(true);});
    return ()=>clearInterval(timer);
  },[load]);
  useEffect(()=>{if(panel) panelRef.current?.showModal();},[panel]);
  useEffect(()=>{if(!notice)return;const timer=setTimeout(()=>setNotice(""),5500);return()=>clearTimeout(timer);},[notice]);

  const active=demo?samples:entries;
  const enriched=useMemo(()=>active.map(entry=>({entry,stageIndex:stage(entry),...classify(entry,todayDate||today())}))
    .sort((a,b)=>b.priority-a.priority || b.delay-a.delay || b.entry.updatedAt.localeCompare(a.entry.updatedAt)),[active,todayDate]);
  const viewItems=enriched.filter(({entry,cycle,flags})=>{
    if(view==="cycle") return entry.kind==="purchase"&&entry.fields.orderStatus!=="已取消"&&(cycle==="long"||(cycleUncertain&&cycle==="uncertain"));
    if(view==="exceptions") return flags.length>0;
    if(view==="inventory") return entry.kind==="purchase"&&entry.fields.orderStatus!=="已取消";
    return true;
  });
  const delayLabel=(item:typeof enriched[number])=>item.delay>=30?delayOptions[3]:item.delay>=8?delayOptions[2]:item.delay>0?delayOptions[1]:item.pending&&estimatedLabel(item.entry.fields)===unknown?delayOptions[4]:delayOptions[0];
  const filterValue=(item:typeof enriched[number],key:string)=>key==="delay"?delayLabel(item):key==="kind"?kinds[item.entry.kind]:value(item.entry.fields,key);
  const search=query.trim().toLowerCase();
  const filtered=viewItems.filter(item=>{
    if(search && !["name","sku","ip","orderRef","batch","box","barcode","tbOrder","tracking","domesticTracking","owner"].some(k=>item.entry.fields[k]?.toLowerCase().includes(search))) return false;
    return Object.entries(filters).every(([key,val])=>!val||(key==="exception"?item.flags.includes(val):filterValue(item,key)===val));
  });
  const shown=filtered.filter(item=>selectedStage===null||item.stageIndex===selectedStage);
  const counts=Array.from({length:8},(_,idx)=>filtered.filter(item=>item.stageIndex===idx).length);
  const totalFlow=counts.reduce((a,b)=>a+b,0);
  const filteredTotals=totals(shown.map(x=>x.entry),todayDate||today());
  const alerts=enriched.filter(e=>e.flags.length>0).length;
  const selectedLabel=navigation.find(v=>v.id===view)?.label;
  const activeFilters=Object.values(filters).filter(Boolean).length;
  const currentLayout=view==="overview"?layout:"table";
  function navigate(next:View) {
    setView(next); setSelectedStage(null); setQuery(""); setFilters({}); setPageSize(40); setExpanded(false);
  }
  function create(kind:Kind="purchase") {
    setDemo(false);
    if(signedOut) {window.location.assign("/signin-with-chatgpt?return_to=/"); return;}
    if(!loaded) void load();
    setDialog({id:crypto.randomUUID(),kind,fields:kind==="purchase"?{orderedAt:today(),orderStatus:"已下单",qty:"1"}:{},manual:[],updatedAt:"",revision:0});
  }
  async function update(entry:Entry) {
    const result=await request("save",[entry]);
    const saved=result.entries[0];
    setEntries(list=>[saved,...list.filter(e=>e.id!==saved.id)]);
    setLoaded(true);setDialog(null);setNotice("记录已保存，统计与异常已更新");
  }
  async function selectFile(file?:File) {
    if(!file)return;
    setError(""); setImportData(null); setBusy(true);
    try {
      if(!/\.(json|csv)$/i.test(file.name)||file.size>12_000_000) throw new Error("请选择 12 MB 以内的 JSON 或 CSV 文件");
      setImportData({name:file.name,entries:await readImport(await file.text(),file.name)});
    } catch(e) {setError((e as Error).message);}
    finally {setBusy(false); if(fileRef.current) fileRef.current.value="";}
  }
  async function commitImport() {
    if(!importData||busy)return;
    if(signedOut) {setError("请先登录 ChatGPT，再重新选择要导入的文件。"); return;}
    setBusy(true);setError("");
    let inserted=0, skipped=0;
    try {
      for(let i=0;i<importData.entries.length;i+=50){
        const result=await request("import",importData.entries.slice(i,i+50));
        inserted+=result.entries.length;skipped+=result.skipped??0;
        setEntries(old=>[...result.entries,...old.filter(e=>!result.entries.some(saved=>saved.id===e.id))]);
      }
      setLoaded(true);setDemo(false);setImportData(null);setPanel(null);navigate("records");setNotice("已导入 "+inserted+" 条，跳过 "+skipped+" 条重复记录");
    } catch(e) {setError((inserted?"已导入 "+inserted+" 条。重试会跳过已保存的记录。 ":"")+(e as Error).message);}
    finally {setBusy(false);}
  }
  function download(format:"json"|"csv"|"md", all=false) {
    const data=all?active:shown.map(x=>x.entry);
    const date=todayDate||today();
    if(format==="csv") saveFile("周边履约-"+date+".csv",toCSV(data),"text/csv;charset=utf-8");
    if(format==="json") saveFile("周边履约-"+date+".json",JSON.stringify({schema:"stockgood-fulfillment/v1",exportedAt:new Date().toISOString(),entries:data},null,2),"application/json");
    if(format==="md") {
      const summary=totals(data,date);
      const headings=metricDefs.map(([key,label])=>"- "+label+"： "+fmt.format(summary[key])+(key==="cost"?" JPY":""));
      const grouped=stages.map((s,i)=>"- "+s+"： "+data.filter(e=>stage(e)===i).length);
      const anomalies=data.map(e=>({e,...classify(e,date)})).filter(r=>r.flags.length).sort((a,b)=>b.priority-a.priority||b.delay-a.delay);
      const clean=(s:string)=>s.replace(/[\r\n]+/g," ").replace(/[<>]/g,"");
      const output=["# 履约进度",date,demo?"示例数据":"运营台账","## 统计",...headings,"## 流程",...grouped,"## 待处理异常",...anomalies.map(({e,flags,delay,priority})=>"- "+clean(e.fields.name)+" · "+priorityNames[priority]+" · "+flags.join("、")+" · "+(delay?delay+" 天 · ":"")+clean(value(e.fields,"owner")))];
      saveFile("PROJECT-STATUS.md",output.join("\n\n")+"\n","text/markdown;charset=utf-8");
    }
    setExportOpen(false);
  }
  function openPanel(next:"sources"|"import") {if(!signedOut)setError("");setPanel(next);setImportData(null);setExportOpen(false);}
  function closePanel() {if(!busy){setPanel(null);if(!signedOut)setError("");setImportData(null);}}
  function resetFilters(){setQuery("");setFilters({});setSelectedStage(null);setPageSize(40);}
  const empty=<div className="empty"><div className="empty-icon"><Package size={23}/></div><h3>{search||activeFilters||selectedStage!==null?"没有匹配的记录":"这里还没有记录"}</h3><p>{search||activeFilters||selectedStage!==null?"试试调整搜索词或筛选条件。":view==="cycle"?"满足 6 个月条件的采购记录会显示在这里。":view==="exceptions"?"有待处理的异常时会显示在这里。":"通过导入或手动录入建立你的台账。"}</p>{search||activeFilters||selectedStage!==null?<button className="button" onClick={resetFilters}>重置筛选</button>:!["cycle","exceptions"].includes(view)&&<button className="button" onClick={()=>create()}>新增记录</button>}</div>;

  return <div className="shell">
    <aside className="sidebar">
      <button className="brand" onClick={()=>navigate("overview")}><span className="brand-mark"><Package size={23}/></span><span><strong>周边履约</strong><small>STOCKGOOD</small></span></button>
      <div className="nav-section"><span className="nav-caption">工作台</span>{navigation.map(({id,label,icon:Icon})=><button key={id} className={view===id?"nav active":"nav"} onClick={()=>navigate(id)} aria-current={view===id?"page":undefined}><Icon size={18}/><span>{label}</span>{id==="exceptions"&&alerts>0&&<b className="nav-count">{alerts}</b>}</button>)}</div>
      <div className="nav-section data-nav"><span className="nav-caption">数据</span><button className="nav" onClick={()=>openPanel("sources")}><Database size={18}/><span>数据与同步</span></button></div>
      <div className="sidebar-footer"><div className="workspace-icon"><Warehouse size={16}/></div><div><strong>私有工作区</strong><small>Stockgood Sites</small></div></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><div className="breadcrumb"><span>工作台</span><span>/</span><strong>{selectedLabel}</strong></div><div className="header-right"><span className="date"><CalendarDays size={16}/>{todayDate?todayDate.replaceAll("-"," / "):"今日"}</span><button className="avatar" aria-label="数据与同步" onClick={()=>openPanel("sources")}>S</button></div></header>
      <main>
        <section className="heading"><div><h1>{selectedLabel}</h1><p>{subtitles[view]}</p></div><div className="actions">
          <button className="button" onClick={()=>openPanel("import")}><Upload size={16}/>导入</button>
          <div className="export"><button className="button" aria-expanded={exportOpen} onClick={()=>setExportOpen(!exportOpen)}><Download size={16}/>导出<ChevronDown size={14}/></button>
            {exportOpen&&<><button className="menu-overlay" aria-label="关闭导出菜单" onClick={()=>setExportOpen(false)}></button><div className="dropdown"><button onClick={()=>download("csv")}><FileSpreadsheet size={16}/>当前视图 CSV</button><button onClick={()=>download("json")}><FileJson size={16}/>当前视图 JSON</button><button onClick={()=>download("json",true)}><Database size={16}/>全部记录 JSON</button><button onClick={()=>download("csv",true)}><FileSpreadsheet size={16}/>全部记录 CSV</button><button onClick={()=>download("md",true)}><FileText size={16}/>PROJECT-STATUS.md</button></div></>}
          </div>
          <button className="button primary" onClick={()=>create()}><Plus size={19}/>新增记录</button>
        </div></section>
        {(demo||error&&!panel||!loaded)&&<div className="mode-banner"><div><Activity size={17}/><strong>{demo?"示例数据":loaded?"台账提示":"连接台账"}</strong><span>{error&&!panel?error:demo?"以下记录用于体验流程。切换到运营台账管理实际订单。":"正在加载运营数据…"}</span></div>{signedOut?<a className="text-button" href="/signin-with-chatgpt?return_to=/" target="_top">登录 ChatGPT <ArrowRight size={15}/></a>:<button className="text-button" onClick={()=>{setDemo(false);navigate(view);if(!loaded)void load();}}>进入运营台账 <ArrowRight size={15}/></button>}</div>}
        {!demo&&loaded&&!error&&<div className="real-mode"><span><span className="live-dot"/>运营台账</span><button className="text-button" onClick={()=>{setDemo(true);navigate("overview");}}>查看示例</button></div>}
        {view==="overview"&&<div className="metrics">{metricDefs.map(([key,label,caption,Icon,color])=><article key={key} className="metric"><div className="metric-top"><span>{label}</span><i className={"metric-icon "+color}><Icon size={18}/></i></div><div className="metric-number">{key==="cost"&&<small>¥</small>}{fmt.format(filteredTotals[key])}</div><p>{caption}</p></article>)}</div>}

        {view==="overview"&&<section className="panel flow-panel">
          <div className="panel-heading"><div className="panel-title"><span className="section-icon"><ArrowLeftRight size={19}/></span><div><h2>履约流程</h2><p>点击阶段查看对应记录</p></div></div><button className={"pill "+(selectedStage===7?"green":"neutral")} onClick={()=>setSelectedStage(selectedStage===7?null:7)}><CircleCheck size={14}/>已签收 {counts[7]}</button></div>
          <div className="flow-scroll"><div className="flow-track">{stages.map((name,i)=>{
            const Icon=stageIcons[i];
            return <button key={name} style={{"--step-color":stageColors[i]} as React.CSSProperties} className={"flow-step "+(selectedStage===i?"selected":"")} onClick={()=>{setSelectedStage(selectedStage===i?null:i);setPageSize(40);}}><span className="step-top"><Icon size={16}/><b>{counts[i]}</b></span><span className="step-name">{name}</span><span className="step-progress"><i style={{width:(totalFlow?counts[i]/totalFlow*100:0)+"%"}}/></span></button>;
          })}</div></div>
        </section>}

        <section className="panel records-panel">
          <div className="panel-heading"><div className="panel-title"><span className="section-icon">{view==="exceptions"?<AlertCircle size={19}/>:view==="cycle"?<Clock3 size={19}/>:<List size={19}/>}</span><div><h2>{view==="overview"?"履约看板":selectedLabel}</h2><p>{shown.length} 条记录{selectedStage!==null?" · "+(stages[selectedStage]||"已签收"):""}</p></div></div>
            {view==="overview"?<div className="segments"><button className={layout==="board"?"current":""} onClick={()=>setLayout("board")}><LayoutDashboard size={15}/>看板</button><button className={layout==="table"?"current":""} onClick={()=>setLayout("table")}><List size={15}/>表格</button></div>
              :view==="records"?<div className="list-actions"><button className="button" onClick={()=>create("catalog")}><Plus size={15}/>商品 SKU</button><button className="button" onClick={()=>create("fulfillment")}><Plus size={15}/>履约订单</button></div>
              :view==="cycle"?<label className="check-switch"><input type="checkbox" checked={cycleUncertain} onChange={e=>setCycleUncertain(e.target.checked)}/>同时显示需确认</label>:null}
          </div>
          <div className="toolbar"><div className="search"><Search size={17}/><input aria-label="搜索记录" placeholder="搜索商品、订单号、SKU、批次…" value={query} onChange={e=>{setQuery(e.target.value);setPageSize(40);}}/>{query&&<button className="icon-button" aria-label="清除搜索" onClick={()=>setQuery("")}><X size={15}/></button>}</div><button className={"button "+(expanded||activeFilters?"button-active":"")} aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}><SlidersHorizontal size={16}/>筛选{activeFilters>0&&<b>{activeFilters}</b>}</button>{(activeFilters>0||selectedStage!==null)&&<button className="text-button" onClick={resetFilters}>重置</button>}</div>
          {expanded&&<div className="filter-grid">{filterDefs.map(([key,label])=>{
            const values=key==="delay"?delayOptions:key==="exception"?exceptions:key==="kind"?Object.values(kinds):key in statuses?statuses[key as keyof typeof statuses]:[];
            const opts=Array.from(new Set([...values,...(key==="exception"?[]:viewItems.map(e=>filterValue(e,key)))]));
            return <label key={key}>{label}<select value={filters[key]??""} onChange={e=>{setFilters({...filters,[key]:e.target.value});setPageSize(40);}}><option value="">全部</option>{opts.map(s=><option key={s}>{s}</option>)}</select></label>;
          })}</div>}
          {view==="cycle"&&<p className="inline-note">以预计最早发货日判断 6 个月。若预计旬别或月份跨过门槛，标记为「需确认」。</p>}
          {shown.length===0?empty:currentLayout==="board"?<div className="board-scroll"><div className="board">
            {(selectedStage!==null?[selectedStage]:[0,1,2,3,4,5,6,...(counts[7]?[7]:[])]).map(index=><div key={index} className="column"><h3><i style={{background:stageColors[index]||"#40ae8c"}}/>{stages[index]||"已签收"}<span>{counts[index]}</span></h3>{shown.filter(item=>item.stageIndex===index).slice(0,12).map(item=><button className="kanban-card" key={item.entry.id} onClick={()=>setDialog(item.entry)}><strong>{item.entry.fields.name}</strong><span>{value(item.entry.fields,"sku")} · {value(item.entry.fields,"batch")}</span><div><span className={"pill "+priorityClasses[item.priority]}>{priorityNames[item.priority]}</span><span>{item.delay?item.delay+" 天延期":estimatedLabel(item.entry.fields)}</span></div></button>)}{counts[index]===0&&<p className="column-empty">暂无记录</p>}{counts[index]>12&&<button className="text-button" onClick={()=>{setSelectedStage(index);setLayout("table");}}>查看全部 {counts[index]} 条 <ArrowRight size={14}/></button>}</div>)}
            {shown.some(i=>i.stageIndex<0)&&<button className="column archive-column" onClick={()=>setLayout("table")}><List size={18}/>查看商品档案与取消记录</button>}
          </div></div>:<><div className="table-wrap"><table><thead><tr><th>商品 / SKU</th><th>{view==="inventory"?"采购批次 / 箱号":"订单 / 批次"}</th>{view==="inventory"?<><th>库存 / 可售</th><th>保税仓状态</th></>:<><th>预计发货</th><th>{view==="cycle"?"延期原因 / 跟进":"履约状态"}</th></>}<th>{view==="exceptions"?"异常类型":"优先级"}</th><th>责任人</th><th></th></tr></thead><tbody>{shown.slice(0,pageSize).map(item=>{
            const {entry,stageIndex,priority,flags,delay,cycle}=item,f=entry.fields;
            return <tr key={entry.id}><td><button className="table-link" onClick={()=>setDialog(entry)}>{f.name}</button><small>{value(f,"sku")} · {value(f,"ip")}</small></td><td>{view==="inventory"?value(f,"batch"):f.tbOrder||value(f,"orderRef")}<small>{view==="inventory"?value(f,"box"):value(f,"batch")}</small></td>{view==="inventory"?<><td>{value(f,"stockQty")} / {value(f,"sellableQty")}<small>{value(f,"inventoryStatus")}</small></td><td>{value(f,"bondedStatus")}</td></>:<><td>{estimatedLabel(f)}<small>{delay?"延期 "+delay+" 天":view==="cycle"?cycle==="long"?"≥ 6 个月":"需确认":""}</small></td><td>{view==="cycle"?<>{value(f,"delayReason")}<small>{value(f,"followup")}</small></>:stageIndex===7?"已签收":stageIndex<0?f.orderStatus==="已取消"?"已取消":kinds[entry.kind]:stages[stageIndex]}</td></>}<td>{view==="exceptions"?<><span className={"pill "+priorityClasses[priority]}>{priorityNames[priority]}</span><small>{flags.join("、")}</small></>:<span className={"pill "+priorityClasses[priority]}>{priorityNames[priority]}</span>}</td><td>{value(f,"owner")}</td><td><button className="text-button" onClick={()=>setDialog(entry)}>{demo?"查看":"编辑"} <ArrowRight size={14}/></button></td></tr>;
          })}</tbody></table></div>{shown.length>pageSize&&<button className="button more" onClick={()=>setPageSize(pageSize+40)}>显示更多 <ArrowDown size={15}/></button>}</>}
        </section>
      </main>
    </div>
    {notice&&<div className="toast" role="status"><CircleCheck size={20}/>{notice}</div>}
    {dialog&&<RecordDialog key={dialog.id} entry={dialog} entries={active} readonly={dialog.id.startsWith("demo-")&&demo} onClose={()=>setDialog(null)} onSave={update}/>}
    {panel&&<dialog className="modal" ref={panelRef} onCancel={e=>{e.preventDefault();closePanel();}}><header className="modal-head"><div><h2>{panel==="sources"?"数据与同步":"导入记录"}</h2><p>{panel==="sources"?"管理数据来源与同步文件。":"支持 Stockgood 订单 JSON，以及工作台的 JSON / CSV。"}</p></div><button type="button" className="icon-button" aria-label="关闭" onClick={closePanel} disabled={busy}><X size={20}/></button></header>
      {panel==="sources"?<div className="modal-body sources">
        <div><Database size={20}/><section><strong>Sites 运营数据库</strong><p>保存当前账户的订单、商品和履约记录。Stockgood 既有数据可通过 JSON 导入。</p></section><span className={"pill "+(loaded?"green":"neutral")}>{loaded?"已连接":"需确认"}</span></div>
        <div><GitBranch size={20}/><section><strong>GitHub · yitakusan/good-bate</strong><p>在独立分支查看站点源码。</p></section><a className="text-button" href={branch} target="_blank" rel="noreferrer">打开分支 <ArrowUp size={14}/></a></div>
        <div><ArrowLeftRight size={20}/><section><strong>本地多 Agent / DSH / QQ / 外部数据库</strong><p>接入时可使用版本化 JSON 或 CSV 交换记录。</p></section><span className="pill neutral">待配置</span></div>
        <div><FileText size={20}/><section><strong>docs/PROJECT-STATUS.md</strong><p>导出当前台账的统计、流程和异常摘要。</p></section><button className="text-button" onClick={()=>download("md",true)}>下载 Markdown <Download size={15}/></button></div>
      </div>:<><div className="modal-body"><div className="dropzone" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(!busy)void selectFile(e.dataTransfer.files[0]);}}><Upload size={25}/><strong>{busy?"正在处理…":"拖放 JSON / CSV 到这里"}</strong><button className="button" onClick={()=>fileRef.current?.click()} disabled={busy}>选择文件</button><input ref={fileRef} type="file" accept=".json,.csv" hidden onChange={e=>void selectFile(e.target.files?.[0])}/><span>最多 2,500 行 · 12 MB</span></div>
        {importData&&<div className="import-preview"><strong>{importData.name}</strong><p>已校验 {importData.entries.length} 条。导入会跳过相同记录 ID。</p>{importData.entries.slice(0,4).map(e=><div key={e.id}><span>{e.fields.name}</span><small>{kinds[e.kind]}</small></div>)}</div>}
        {error&&<p className="form-error" role="alert">{error}</p>}
        <button className="text-button" onClick={()=>saveFile("周边履约-导入模板.csv",toCSV([{id:"",kind:"purchase",fields:{name:"示例商品",sku:"SKU-001",qty:"1"},manual:[],revision:0,updatedAt:""}]),"text/csv;charset=utf-8")}><Download size={15}/>下载 CSV 模板</button></div>
        <footer className="modal-foot"><button className="button" disabled={busy} onClick={closePanel}>取消</button><button className="button primary" disabled={!importData||busy} onClick={()=>void commitImport()}><Upload size={16}/>确认导入</button></footer></>}
    </dialog>}
  </div>;
}
