import { today, moveMonth, type Entry, type Fields } from "./fulfillment";

export function demoEntries():Entry[] {
  const now = today();
  const plus = (days:number) => new Date(Date.parse(now)+days*86_400_000).toISOString().slice(0,10);
  const products:Fields[] = [
    {name:"葬送的芙莉莲 · 迷你立牌套装",ip:"葬送的芙莉莲",category:"亚克力",sku:"FRN-AC-021",qty:"36",unitCost:"1650",orderRef:"JP-2609-041",shop:"Animate",orderedAt:moveMonth(now,-2),expectedAt:plus(19),orderStatus:"已下单",inventoryStatus:"待到货",owner:"采购"},
    {name:"孤独摇滚！ · 乐队纪念徽章",ip:"孤独摇滚！",category:"徽章",sku:"BTR-BD-014",qty:"48",unitCost:"660",orderRef:"JP-2609-008",shop:"Aniplex",orderedAt:moveMonth(now,-8),expectedAt:plus(-36),orderStatus:"已下单",inventoryStatus:"待到货",delayReason:"供应商延后出货",followup:"跟进中",owner:"采购"},
    {name:"排球少年!! · 乌野校队吊饰",ip:"排球少年!!",category:"挂件",sku:"HQ-KC-032",qty:"60",unitCost:"880",batch:"JP-B024",box:"A-03",orderRef:"JP-2610-016",shop:"Movic",orderedAt:moveMonth(now,-1),arrivedAt:plus(-7),arrivedQty:"60",stockQty:"60",sellableQty:"42",orderStatus:"在库",inventoryStatus:"在库",owner:"仓库"},
    {name:"我推的孩子 · 星野爱收藏卡",ip:"我推的孩子",category:"卡牌",sku:"ONK-CD-007",qty:"100",unitCost:"330",batch:"JP-B024",box:"A-04",orderRef:"JP-2610-022",orderedAt:moveMonth(now,-1),arrivedAt:plus(-3),arrivedQty:"96",stockQty:"96",sellableQty:"80",orderStatus:"在库",inventoryStatus:"在库",owner:"仓库"},
    {name:"蓝色监狱 · 洁世一趴趴玩偶",ip:"蓝色监狱",category:"毛绒",sku:"BLL-PL-017",qty:"24",unitCost:"2420",batch:"JP-B025",box:"B-01",orderRef:"JP-2610-029",arrivedAt:plus(-9),arrivedQty:"24",stockQty:"24",sellableQty:"18",orderStatus:"在库",inventoryStatus:"在库",bondedStatus:"入仓中",owner:"仓库"},
    {name:"初音未来 · 冬日主题亚克力",ip:"初音未来",category:"亚克力",sku:"MIK-AC-036",qty:"30",unitCost:"1320",batch:"JP-B026",orderRef:"JP-2610-033",arrivedAt:plus(-10),arrivedQty:"30",stockQty:"30",sellableQty:"20",orderStatus:"在库",inventoryStatus:"在库",bondedStatus:"已入仓",owner:"运营"},
    {name:"咒术回战 · 五条悟迷你色纸",ip:"咒术回战",category:"色纸",sku:"JJK-SK-033",qty:"24",unitCost:"550",batch:"JP-B021",orderRef:"JP-2610-005",arrivedAt:plus(-11),arrivedQty:"24",stockQty:"16",sellableQty:"10",orderStatus:"在库",inventoryStatus:"在库",bondedStatus:"已入仓",tbOrder:"TB-DEMO-0821",declarationStatus:"待申报",owner:"申报"},
    {name:"宝可梦 · 皮卡丘刺绣挂件",ip:"宝可梦",category:"挂件",sku:"PKM-KC-029",qty:"40",unitCost:"1100",batch:"JP-B021",orderRef:"JP-2610-003",arrivedAt:plus(-14),arrivedQty:"40",stockQty:"20",sellableQty:"10",orderStatus:"在库",inventoryStatus:"在库",bondedStatus:"已入仓",tbOrder:"TB-DEMO-0830",declarationStatus:"已申报",customsStatus:"清关中",compliance:"已核验",hsCode:"需确认",owner:"关务"},
    {name:"间谍过家家 · 阿尼亚冰箱贴",ip:"间谍过家家",category:"杂货",sku:"SPY-MG-018",qty:"36",unitCost:"715",batch:"JP-B020",orderRef:"JP-2609-037",arrivedAt:plus(-16),arrivedQty:"36",stockQty:"16",sellableQty:"11",orderStatus:"在库",inventoryStatus:"在库",bondedStatus:"已入仓",tbOrder:"TB-DEMO-0790",declarationStatus:"已申报",customsStatus:"已放行",deliveryStatus:"配送中",compliance:"已核验",owner:"配送"},
  ];
  return products.map((fields,i) => ({id:"demo-"+i,kind:"purchase",fields,manual:[],updatedAt:now,revision:0}));
}
