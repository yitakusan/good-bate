from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.admin_auth import admin_auth_required, require_admin
from app.database import DATA_DIR, init_db
from app.models import (
    ActionLogOut,
    FinanceSummaryOut,
    InboundCreate,
    ItemBatchCreate,
    ItemCreate,
    ItemOut,
    ItemUpdate,
    LineCreate,
    OrderCreate,
    OrderOut,
    OrderRequestConfirm,
    OrderRequestCreate,
    OrderRequestOut,
    OrderRequestPublicOut,
    OrderRequestReject,
    OrderUpdate,
    OutboundBatchCreate,
    OutboundBatchFinanceUpdate,
    OutboundBatchOut,
    ScrapeRequest,
    ScrapeResult,
    ShipmentCreate,
    ShipmentOut,
    StatsOut,
    StockBoxCreate,
    StockBoxMergeChild,
    StockBoxOrdersPayload,
    StockBoxOut,
    StockBoxUpdate,
)
from app.rate_limit import rate_limit
from app.scrapers.preview import scrape_html_document, scrape_url
from app.services import action_log as action_log_svc
from app.services import finance as finance_svc
from app.services import items as items_svc
from app.services import order_requests as order_requests_svc
from app.services import orders as orders_svc
from app.services import outbound_batches as outbound_svc
from app.services import shipments as shipments_svc
from app.services import stock_boxes as stock_boxes_svc
from app.settings import get_settings
from app.tunnel_status import get_tunnel_status, start_tunnel, stop_tunnel

ITEM_IMAGES_DIR = DATA_DIR / "item_images"

OPENAPI_TAGS = [
    {"name": "系统", "description": "健康检查、元信息与 Cloudflare 隧道"},
    {"name": "顾客申请（公开）", "description": "C 端申请页：抓取预览、提交与查询申请"},
    {"name": "申请单（管理）", "description": "员工确认下单 / 拒绝顾客申请"},
    {"name": "订单", "description": "库存订单与明细行"},
    {"name": "货品", "description": "货品清单与批量创建"},
    {"name": "抓取", "description": "商品链接或页面 HTML 解析"},
    {"name": "进库", "description": "运单进库与到仓确认"},
    {"name": "库存合箱", "description": "在库订单合箱（不改变状态，与出库打包独立）"},
    {"name": "出库", "description": "出库批次与签收确认"},
    {"name": "财务", "description": "下单汇率、出库应收/已收与月度汇总"},
    {"name": "操作日志", "description": "可撤销的写操作记录"},
]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    ITEM_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="Stockgood API",
    version="0.3.0",
    description="库存管理接口：订单 → 进库 → 出库 → 签收。支持顾客申请、抓取导入与影子库测试。",
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ITEM_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/media/item_images",
    StaticFiles(directory=str(ITEM_IMAGES_DIR)),
    name="item_images",
)


@app.get("/api/health", tags=["系统"], summary="健康检查")
def health() -> dict[str, str | bool]:
    """返回服务状态、当前库模式（生产 / 影子）与数据库文件名。"""
    settings = get_settings()
    return {
        "status": "ok",
        "db_mode": settings.db_mode,
        "is_shadow": settings.is_shadow,
        "database": settings.database_path.name,
    }


@app.get("/api/meta", tags=["系统"], summary="前端元信息")
def meta() -> dict[str, str | bool]:
    """库模式标签、是否需要管理口令等，供前端页头展示。"""
    settings = get_settings()
    return {
        "db_mode": settings.db_mode,
        "is_shadow": settings.is_shadow,
        "database": settings.database_path.name,
        "label": (
            "测试影子库 · 不参与实际库存"
            if settings.is_shadow
            else "实际库存"
        ),
        "auth_required": admin_auth_required(),
    }


@app.get("/api/tunnel", tags=["系统"], summary="隧道状态")
def tunnel_status() -> dict[str, object]:
    """查询本机 cloudflared 临时隧道是否开启，以及公开 URL。"""
    return get_tunnel_status()


@app.post("/api/tunnel/start", tags=["系统"], summary="开启隧道")
def tunnel_start(_: None = Depends(require_admin)) -> dict[str, object]:
    """启动 Cloudflare 快速隧道（需管理口令，若已配置）。"""
    return start_tunnel()


@app.post("/api/tunnel/stop", tags=["系统"], summary="关闭隧道")
def tunnel_stop(_: None = Depends(require_admin)) -> dict[str, object]:
    """停止本机 cloudflared 隧道进程。"""
    return stop_tunnel()


@app.post(
    "/api/public/scrape",
    response_model=ScrapeResult,
    tags=["顾客申请（公开）"],
    summary="公开抓取预览",
)
async def public_scrape(payload: ScrapeRequest, request: Request) -> dict:
    """顾客端预览商品：传 `url`，或粘贴整页 `html`（如 zozo.jp 被拦截时）。有频率限制。"""
    rate_limit(request, limit=15, window=60.0)
    try:
        if (payload.html or "").strip():
            return await scrape_html_document(payload.html or "", payload.url or "")
        return await scrape_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        import logging
        import traceback

        logging.getLogger("uvicorn.error").error(
            "public scrape failed for %s\n%s", payload.url, traceback.format_exc()
        )
        detail = str(exc).strip() or type(exc).__name__
        raise HTTPException(status_code=502, detail=f"scrape failed: {detail}") from exc


@app.post(
    "/api/public/order-requests",
    response_model=OrderRequestPublicOut,
    tags=["顾客申请（公开）"],
    summary="提交申请",
)
def public_create_order_request(
    payload: OrderRequestCreate, request: Request
) -> dict:
    """顾客提交代购/下单申请，返回申请编号（如 SG-XXXXXX）。"""
    rate_limit(request, limit=10, window=60.0)
    return order_requests_svc.create_request(payload)


@app.get(
    "/api/public/order-requests",
    response_model=list[OrderRequestPublicOut],
    tags=["顾客申请（公开）"],
    summary="公开申请列表",
)
def public_list_order_requests(
    request: Request,
    status: Optional[str] = Query(default=None, description="状态筛选：submitted / ordered / rejected"),
) -> list[dict]:
    """顾客端可见的申请列表（字段已脱敏）。"""
    rate_limit(request, limit=30, window=60.0)
    return order_requests_svc.list_public_requests(status=status)


@app.get(
    "/api/public/order-requests/{code}",
    response_model=OrderRequestPublicOut,
    tags=["顾客申请（公开）"],
    summary="按编号查申请",
)
def public_get_order_request(code: str, request: Request) -> dict:
    """用申请编号（如 SG-XXXXXX）查询进度。"""
    rate_limit(request, limit=30, window=60.0)
    return order_requests_svc.get_by_code(code)


@app.get(
    "/api/order-requests",
    response_model=list[OrderRequestOut],
    tags=["申请单（管理）"],
    summary="申请单列表",
)
def list_order_requests(
    status: Optional[str] = Query(default=None, description="状态筛选：submitted / ordered / rejected"),
    _: None = Depends(require_admin),
) -> list[dict]:
    """员工查看全部顾客申请（含联系方式等完整字段）。"""
    return order_requests_svc.list_requests(status=status)


@app.get(
    "/api/order-requests/{request_id}",
    response_model=OrderRequestOut,
    tags=["申请单（管理）"],
    summary="申请单详情",
)
def get_order_request(
    request_id: int, _: None = Depends(require_admin)
) -> dict:
    """按内部 ID 获取申请单。"""
    return order_requests_svc.get_request(request_id)


@app.post(
    "/api/order-requests/{request_id}/confirm-ordered",
    response_model=OrderRequestOut,
    tags=["申请单（管理）"],
    summary="确认已下单",
)
def confirm_order_request(
    request_id: int,
    payload: OrderRequestConfirm,
    _: None = Depends(require_admin),
) -> dict:
    """回填店铺注文番号；可选生成库存订单，备注会带「来自申请 SG-…」。"""
    return order_requests_svc.confirm_ordered(request_id, payload)


@app.post(
    "/api/order-requests/{request_id}/reject",
    response_model=OrderRequestOut,
    tags=["申请单（管理）"],
    summary="拒绝申请",
)
def reject_order_request(
    request_id: int,
    payload: OrderRequestReject,
    _: None = Depends(require_admin),
) -> dict:
    """拒绝顾客申请并填写原因。"""
    return order_requests_svc.reject_request(request_id, payload)


@app.get("/api/stats", tags=["订单"], summary="状态统计", response_model=StatsOut)
def stats() -> dict:
    """各订单/货品状态数量汇总。"""
    return orders_svc.get_stats()


@app.get("/api/shops", tags=["订单"], summary="店铺列表")
def shops() -> list[str]:
    """已有订单中的店铺名列表（筛选用）。"""
    return orders_svc.list_shops()


@app.get(
    "/api/orders",
    response_model=list[OrderOut],
    tags=["订单"],
    summary="订单列表",
)
def list_orders(
    status: Optional[str] = Query(default=None, description="订单状态"),
    shop: Optional[str] = Query(default=None, description="店铺"),
    q: Optional[str] = Query(default=None, description="搜索：订单号 / 名称 / 店铺 / IP / 条码"),
    expected_ship_month: Optional[str] = Query(
        default=None, description="预计发货月，格式 YYYY-MM"
    ),
) -> list[dict]:
    """筛选、搜索库存订单。"""
    return orders_svc.list_orders(
        status=status,
        shop=shop,
        q=q,
        expected_ship_month=expected_ship_month,
    )


@app.post(
    "/api/orders",
    response_model=OrderOut,
    tags=["订单"],
    summary="新建订单",
)
def create_order(
    payload: OrderCreate, _: None = Depends(require_admin)
) -> dict:
    """创建库存订单及明细行。"""
    return orders_svc.create_order(payload)


@app.get(
    "/api/orders/{order_id}",
    response_model=OrderOut,
    tags=["订单"],
    summary="订单详情",
)
def get_order(order_id: int) -> dict:
    """按 ID 获取订单及明细。"""
    return orders_svc.get_order(order_id)


@app.patch(
    "/api/orders/{order_id}",
    response_model=OrderOut,
    tags=["订单"],
    summary="更新订单",
)
def update_order(
    order_id: int, payload: OrderUpdate, _: None = Depends(require_admin)
) -> dict:
    """修改订单号、运费、备注等；取消订单走 status=cancelled。"""
    return orders_svc.update_order(order_id, payload)


@app.post(
    "/api/orders/{order_id}/lines",
    response_model=OrderOut,
    tags=["订单"],
    summary="追加明细行",
)
def add_lines(
    order_id: int, lines: list[LineCreate], _: None = Depends(require_admin)
) -> dict:
    """向已有订单追加货品行。"""
    return orders_svc.add_lines(order_id, lines)


@app.post(
    "/api/orders/{order_id}/inbound",
    response_model=ShipmentOut,
    tags=["进库"],
    summary="按订单进库",
)
def create_order_inbound(
    order_id: int, payload: InboundCreate, _: None = Depends(require_admin)
) -> dict:
    """为订单创建进库运单（运单号 + 承运商 + 行 ID）。"""
    return shipments_svc.create_inbound_for_order(
        order_id=order_id,
        tracking_no=payload.tracking_no,
        carrier=payload.carrier,
        item_ids=payload.item_ids,
    )


@app.get(
    "/api/items",
    response_model=list[ItemOut],
    tags=["货品"],
    summary="货品列表",
)
def list_items(
    status: Optional[str] = Query(default=None, description="货品状态"),
    shop: Optional[str] = Query(default=None, description="店铺"),
    q: Optional[str] = Query(default=None, description="搜索关键词"),
    expected_ship_month: Optional[str] = Query(
        default=None, description="预计发货月，格式 YYYY-MM"
    ),
) -> list[dict]:
    """按状态 / 店铺 / 关键词筛选货品行。"""
    return items_svc.list_items(
        status=status,
        shop=shop,
        q=q,
        expected_ship_month=expected_ship_month,
    )


@app.post(
    "/api/items",
    response_model=ItemOut,
    tags=["货品"],
    summary="新建货品",
)
def create_item(
    payload: ItemCreate, _: None = Depends(require_admin)
) -> dict:
    """手动登记单条货品（可无订单）。"""
    return items_svc.create_item(payload)


@app.post(
    "/api/items/batch",
    response_model=list[ItemOut],
    tags=["货品"],
    summary="批量新建货品",
)
def create_items_batch(
    payload: ItemBatchCreate, _: None = Depends(require_admin)
) -> list[dict]:
    """批量创建货品（抓取导入等多用此接口）。"""
    return items_svc.create_items_batch(payload.items)


@app.post(
    "/api/scrape",
    response_model=ScrapeResult,
    tags=["抓取"],
    summary="抓取 / 解析 HTML",
)
async def scrape(
    payload: ScrapeRequest, _: None = Depends(require_admin)
) -> dict:
    """员工抓取：传商品 `url`，或整页 `html`（zozo.jp 等被 Akamai 拦截时）。"""
    try:
        if (payload.html or "").strip():
            return await scrape_html_document(payload.html or "", payload.url or "")
        return await scrape_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        import logging
        import traceback

        logging.getLogger("uvicorn.error").error(
            "scrape failed for %s\n%s", payload.url, traceback.format_exc()
        )
        detail = str(exc).strip() or type(exc).__name__
        raise HTTPException(status_code=502, detail=f"scrape failed: {detail}") from exc


@app.get(
    "/api/items/{item_id}",
    response_model=ItemOut,
    tags=["货品"],
    summary="货品详情",
)
def get_item(item_id: int) -> dict:
    """按 ID 获取单条货品。"""
    return items_svc.get_item(item_id)


@app.patch(
    "/api/items/{item_id}",
    response_model=ItemOut,
    tags=["货品"],
    summary="更新货品",
)
def update_item(
    item_id: int, payload: ItemUpdate, _: None = Depends(require_admin)
) -> dict:
    """修改数量、条码、状态等；取消行用 status=cancelled。"""
    return items_svc.update_item(item_id, payload)


@app.get(
    "/api/shipments",
    response_model=list[ShipmentOut],
    tags=["进库"],
    summary="运单列表",
)
def list_shipments(
    status: Optional[str] = Query(default=None, description="shipped / delivered"),
    tracking_no: Optional[str] = Query(default=None, description="运单号"),
    direction: Optional[str] = Query(default=None, description="inbound / outbound"),
) -> list[dict]:
    """筛选进库 / 出库运单。"""
    return shipments_svc.list_shipments(
        status=status, tracking_no=tracking_no, direction=direction
    )


@app.post(
    "/api/shipments",
    response_model=ShipmentOut,
    tags=["进库"],
    summary="新建运单",
)
def create_shipment(
    payload: ShipmentCreate, _: None = Depends(require_admin)
) -> dict:
    """创建运单（进库优先用「按订单进库」接口）。"""
    return shipments_svc.create_shipment(
        tracking_no=payload.tracking_no,
        carrier=payload.carrier,
        item_ids=payload.item_ids,
        direction=payload.direction,
        order_id=payload.order_id,
    )


@app.get(
    "/api/shipments/{shipment_id}",
    response_model=ShipmentOut,
    tags=["进库"],
    summary="运单详情",
)
def get_shipment(shipment_id: int) -> dict:
    """按 ID 获取运单。"""
    return shipments_svc.get_shipment(shipment_id)


@app.post(
    "/api/shipments/{shipment_id}/confirm",
    response_model=ShipmentOut,
    tags=["进库"],
    summary="确认到仓 / 签收",
)
def confirm_shipment(
    shipment_id: int, _: None = Depends(require_admin)
) -> dict:
    """将运单标为已送达，并推进关联货品状态。"""
    return shipments_svc.confirm_shipment(shipment_id)


@app.get(
    "/api/stock-boxes",
    response_model=list[StockBoxOut],
    tags=["库存合箱"],
    summary="库存合箱列表",
)
def list_stock_boxes() -> list[dict]:
    """在库合箱组（不走出库、不改货品状态）。"""
    return stock_boxes_svc.list_boxes()


@app.post(
    "/api/stock-boxes",
    response_model=StockBoxOut,
    tags=["库存合箱"],
    summary="创建库存合箱",
)
def create_stock_box(
    payload: StockBoxCreate, _: None = Depends(require_admin)
) -> dict:
    """将在库订单编入库存箱；不改变订单/货品状态。"""
    return stock_boxes_svc.create_box(
        order_ids=payload.order_ids,
        note=payload.note,
        box_no=payload.box_no,
    )


@app.post(
    "/api/stock-boxes/combine",
    response_model=StockBoxOut,
    tags=["库存合箱"],
    summary="合并订单到同一库存箱",
)
def combine_stock_box(
    payload: StockBoxCreate, _: None = Depends(require_admin)
) -> dict:
    """所选在库订单并入同一库存箱（可复用已有箱）；不改状态。"""
    return stock_boxes_svc.combine_orders(
        order_ids=payload.order_ids, note=payload.note
    )


@app.post(
    "/api/stock-boxes/{parent_id}/merge-child",
    response_model=StockBoxOut,
    tags=["库存合箱"],
    summary="将 B 箱作为子箱并入主箱 A",
)
def merge_stock_box_child(
    parent_id: int,
    payload: StockBoxMergeChild,
    _: None = Depends(require_admin),
) -> dict:
    """子箱订单仍留在 B；B 挂到主箱 A 下（仅一层）。"""
    return stock_boxes_svc.merge_child(parent_id, payload.child_box_id)


@app.post(
    "/api/stock-boxes/{child_id}/detach-parent",
    response_model=StockBoxOut,
    tags=["库存合箱"],
    summary="拆出子箱（取消主从关系）",
)
def detach_stock_box_child(
    child_id: int, _: None = Depends(require_admin)
) -> dict:
    """子箱变为独立主箱，订单仍在该箱内。"""
    return stock_boxes_svc.detach_child(child_id)


@app.get(
    "/api/stock-boxes/{box_id}",
    response_model=StockBoxOut,
    tags=["库存合箱"],
    summary="库存合箱详情",
)
def get_stock_box(box_id: int) -> dict:
    return stock_boxes_svc.get_box(box_id)


@app.patch(
    "/api/stock-boxes/{box_id}",
    response_model=StockBoxOut,
    tags=["库存合箱"],
    summary="更新库存合箱",
)
def update_stock_box(
    box_id: int, payload: StockBoxUpdate, _: None = Depends(require_admin)
) -> dict:
    return stock_boxes_svc.update_box(
        box_id, note=payload.note, box_no=payload.box_no
    )


@app.post(
    "/api/stock-boxes/{box_id}/orders",
    response_model=StockBoxOut,
    tags=["库存合箱"],
    summary="合箱加入订单",
)
def add_stock_box_orders(
    box_id: int,
    payload: StockBoxOrdersPayload,
    _: None = Depends(require_admin),
) -> dict:
    return stock_boxes_svc.add_orders(box_id, payload.order_ids)


@app.post(
    "/api/stock-boxes/{box_id}/remove-orders",
    response_model=Optional[StockBoxOut],
    tags=["库存合箱"],
    summary="合箱移出订单",
)
def remove_stock_box_orders(
    box_id: int,
    payload: StockBoxOrdersPayload,
    _: None = Depends(require_admin),
) -> Optional[dict]:
    """移出后若箱空则自动删除并返回 null。"""
    return stock_boxes_svc.remove_orders(box_id, payload.order_ids)


@app.delete(
    "/api/stock-boxes/{box_id}",
    tags=["库存合箱"],
    summary="解散库存合箱",
)
def delete_stock_box(
    box_id: int, _: None = Depends(require_admin)
) -> dict[str, bool]:
    stock_boxes_svc.delete_box(box_id)
    return {"ok": True}


@app.get(
    "/api/outbound-batches",
    response_model=list[OutboundBatchOut],
    tags=["出库"],
    summary="出库批次列表",
)
def list_outbound_batches(
    limit: int = Query(default=50, ge=1, le=200, description="返回条数上限"),
) -> list[dict]:
    """最近出库批次。"""
    return outbound_svc.list_batches(limit=limit)


@app.post(
    "/api/outbound-batches",
    response_model=OutboundBatchOut,
    tags=["出库"],
    summary="新建出库批次",
)
def create_outbound_batch(
    payload: OutboundBatchCreate, _: None = Depends(require_admin)
) -> dict:
    """按箱子创建出库批次（每箱运单号 + 货品）。创建时锁定货款应收。"""
    return outbound_svc.create_batch(
        boxes=[b.model_dump() for b in payload.boxes],
        note=payload.note,
        allow_missing_barcode=payload.allow_missing_barcode,
        missing_barcode_note=payload.missing_barcode_note,
        freight_exchange_rate=payload.freight_exchange_rate,
        freight_unit_price_jpy=payload.freight_unit_price_jpy,
        chargeable_weight=payload.chargeable_weight,
    )


@app.get(
    "/api/outbound-batches/{batch_id}",
    response_model=OutboundBatchOut,
    tags=["出库"],
    summary="出库批次详情",
)
def get_outbound_batch(batch_id: int) -> dict:
    """按 ID 获取出库批次。"""
    return outbound_svc.get_batch(batch_id)


@app.patch(
    "/api/outbound-batches/{batch_id}/finance",
    response_model=OutboundBatchOut,
    tags=["财务"],
    summary="更新出库批次财务（国际运费 / 已收款）",
)
def update_outbound_batch_finance(
    batch_id: int,
    payload: OutboundBatchFinanceUpdate,
    _: None = Depends(require_admin),
) -> dict:
    """更新国际运费字段或登记已收款。"""
    return outbound_svc.update_finance(
        batch_id, payload.model_dump(exclude_unset=True)
    )


@app.get(
    "/api/outbound-batches/{batch_id}/fee-detail.xlsx",
    tags=["财务"],
    summary="导出发货费用明细 Excel",
)
def export_outbound_fee_detail(
    batch_id: int, _: None = Depends(require_admin)
) -> Response:
    """导出发货费用明细（含订单号、下单汇率、合计CNY）。"""
    content = outbound_svc.export_fee_detail_xlsx(batch_id)
    filename = f"fee-detail-batch-{batch_id}.xlsx"
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get(
    "/api/finance/summary",
    response_model=FinanceSummaryOut,
    tags=["财务"],
    summary="财务月度汇总",
)
def finance_summary(
    month: Optional[str] = Query(
        default=None, description="YYYY-MM；默认本月（UTC）"
    ),
) -> dict:
    """按下单月与出库月分别汇总金额。"""
    return finance_svc.month_summary(month)


@app.post(
    "/api/outbound-batches/{batch_id}/confirm",
    response_model=OutboundBatchOut,
    tags=["出库"],
    summary="确认出库批次签收",
)
def confirm_outbound_batch(
    batch_id: int, _: None = Depends(require_admin)
) -> dict:
    """整批确认签收。"""
    return outbound_svc.confirm_batch(batch_id)


@app.get(
    "/api/action-logs",
    response_model=list[ActionLogOut],
    tags=["操作日志"],
    summary="操作日志列表",
)
def list_action_logs(
    limit: int = Query(default=50, ge=1, le=200, description="返回条数上限"),
) -> list[dict]:
    """最近写操作记录。"""
    return action_log_svc.list_logs(limit=limit)


@app.get(
    "/api/action-logs/latest",
    response_model=Optional[ActionLogOut],
    tags=["操作日志"],
    summary="最近可撤销操作",
)
def latest_action_log() -> Optional[dict]:
    """返回最新一条尚未撤销、可撤销的操作（若有）。"""
    return action_log_svc.get_latest_undoable()


@app.post(
    "/api/action-logs/{log_id}/undo",
    response_model=ActionLogOut,
    tags=["操作日志"],
    summary="撤销操作",
)
def undo_action_log(
    log_id: int, _: None = Depends(require_admin)
) -> dict:
    """按日志 ID 撤销对应写操作（若仍允许）。"""
    return action_log_svc.undo(log_id)
