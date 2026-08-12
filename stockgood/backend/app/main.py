from __future__ import annotations

import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.auth import (
    SESSION_COOKIE,
    auth_required,
    bootstrap_admin_if_needed,
    change_password,
    clear_session,
    create_session,
    create_user,
    get_optional_user,
    get_user_by_email,
    list_users,
    purge_expired_sessions,
    require_admin_role,
    require_finance,
    require_staff,
    require_warehouse,
    set_user_active,
    user_count,
    verify_password,
)
from app.database import DATA_DIR, init_db
from app.models import (
    ActionLogOut,
    ChangePasswordIn,
    CreateUserIn,
    DepositConfirmIn,
    FinanceSummaryOut,
    InboundCreate,
    ItemBatchCreate,
    ItemCreate,
    ItemOut,
    ItemUpdate,
    LineCreate,
    LoginIn,
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
    RegisterCustomerIn,
    ScrapeRequest,
    ScrapeResult,
    SetActiveIn,
    ShipmentCreate,
    ShipmentOut,
    StatsOut,
    StockBoxCreate,
    StockBoxMergeChild,
    StockBoxOrdersPayload,
    StockBoxOut,
    StockBoxUpdate,
    UserOut,
)
from app.rate_limit import rate_limit
from app.scrapers.preview import scrape_html_document, scrape_url
from app.services import action_log as action_log_svc
from app.services import apply_stats as apply_stats_svc
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
APP_VERSION = "0.9.2"

OPENAPI_TAGS = [
    {"name": "系统", "description": "健康检查、元信息与 Cloudflare 隧道"},
    {"name": "账号", "description": "登录、注册与用户管理"},
    {"name": "顾客申请（公开）", "description": "C 端申请页：抓取预览、提交与查询申请"},
    {"name": "顾客（登录）", "description": "登录客户查看自己的申请"},
    {"name": "申请单（管理）", "description": "员工确认下单 / 拒绝顾客申请"},
    {"name": "订单", "description": "库存订单与明细行"},
    {"name": "货品", "description": "货品清单与批量创建"},
    {"name": "抓取", "description": "商品链接或页面 HTML 解析"},
    {"name": "进库", "description": "运单进库与到仓确认"},
    {"name": "库存合箱", "description": "在库订单合箱（不改变状态，与出库打包独立）"},
    {"name": "出库", "description": "出库批次与签收确认"},
    {"name": "财务", "description": "下单汇率、出库应收/已收与月度汇总"},
    {"name": "统计", "description": "申请单日/月报：单量、热门链接、花费用户、IP"},
    {"name": "操作日志", "description": "可撤销的写操作记录"},
]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    ITEM_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    bootstrap_admin_if_needed()
    purge_expired_sessions()
    yield


app = FastAPI(
    title="Stockgood API",
    version=APP_VERSION,
    description="库存管理接口：订单 → 进库 → 出库 → 签收。支持顾客申请、账号登录与影子库测试。",
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
)

_cors = get_settings().cors_origin_list
_cors_credentials = _cors != ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors,
    allow_credentials=_cors_credentials,
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
def health() -> dict[str, object]:
    """返回服务状态、库模式、磁盘与最近备份信息。"""
    settings = get_settings()
    db_path = settings.database_path
    backup_dir = DATA_DIR / "backups"
    last_backup = None
    if backup_dir.is_dir():
        files = sorted(backup_dir.glob("*.sqlite"), key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            last_backup = {
                "name": files[0].name,
                "mtime": int(files[0].stat().st_mtime),
            }
    disk = shutil.disk_usage(str(DATA_DIR if DATA_DIR.exists() else Path.cwd()))
    return {
        "status": "ok",
        "version": APP_VERSION,
        "db_mode": settings.db_mode,
        "is_shadow": settings.is_shadow,
        "database": db_path.name,
        "auth_required": auth_required(),
        "user_count": user_count(),
        "disk": {
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
        },
        "last_backup": last_backup,
    }


@app.get("/api/meta", tags=["系统"], summary="前端元信息")
def meta(
    user: Optional[dict] = Depends(get_optional_user),
) -> dict[str, object]:
    """库模式标签、是否需要登录等，供前端页头展示。"""
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
        "auth_required": auth_required(),
        "version": APP_VERSION,
        "user": user,
        "deposit_rate": get_settings().deposit_rate,
    }


# --- Auth ---


@app.post("/api/auth/login", response_model=UserOut, tags=["账号"], summary="登录")
def auth_login(payload: LoginIn, response: Response) -> dict:
    row = get_user_by_email(payload.email)
    if not row or not verify_password(payload.password, row.get("_password_hash") or ""):
        raise HTTPException(status_code=401, detail="invalid email or password")
    if not row.get("is_active", True):
        raise HTTPException(status_code=403, detail="account disabled")
    create_session(int(row["id"]), response)
    return {k: v for k, v in row.items() if not k.startswith("_")}


@app.post("/api/auth/logout", tags=["账号"], summary="登出")
def auth_logout(
    response: Response,
    stockgood_session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, bool]:
    clear_session(response, stockgood_session)
    return {"ok": True}


@app.get("/api/auth/me", response_model=Optional[UserOut], tags=["账号"], summary="当前用户")
def auth_me(user: Optional[dict] = Depends(get_optional_user)) -> Optional[dict]:
    return user


@app.post(
    "/api/auth/register",
    response_model=UserOut,
    tags=["账号"],
    summary="客户自助注册",
)
def auth_register(payload: RegisterCustomerIn, response: Response) -> dict:
    user = create_user(
        email=payload.email,
        password=payload.password,
        role="customer",
        display_name=payload.display_name,
    )
    create_session(int(user["id"]), response)
    return user


@app.post(
    "/api/auth/change-password",
    tags=["账号"],
    summary="修改自己的密码",
)
def auth_change_password(
    payload: ChangePasswordIn,
    user: dict = Depends(get_optional_user),
) -> dict[str, bool]:
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="login required")
    change_password(int(user["id"]), payload.password)
    return {"ok": True}


@app.get("/api/users", response_model=list[UserOut], tags=["账号"], summary="用户列表")
def api_list_users(_: dict = Depends(require_admin_role)) -> list[dict]:
    return list_users()


@app.post("/api/users", response_model=UserOut, tags=["账号"], summary="创建员工/客户")
def api_create_user(
    payload: CreateUserIn, _: dict = Depends(require_admin_role)
) -> dict:
    return create_user(
        email=payload.email,
        password=payload.password,
        role=payload.role,
        display_name=payload.display_name,
    )


@app.patch(
    "/api/users/{user_id}/active",
    response_model=UserOut,
    tags=["账号"],
    summary="启用/停用用户",
)
def api_set_user_active(
    user_id: int,
    payload: SetActiveIn,
    _: dict = Depends(require_admin_role),
) -> dict:
    return set_user_active(user_id, payload.is_active)


@app.get("/api/product-kinds", tags=["货品"], summary="商品种类列表")
def list_product_kinds(_: dict = Depends(require_staff)) -> dict[str, object]:
    """返回可选种类标签及关键字别名（日文为主，来自 product_kinds.json）。"""
    from app.product_kind import ProductKindNormalizer

    detector = ProductKindNormalizer(get_settings().product_kind_path)
    return {
        "labels": detector.known_kinds(),
        "aliases": detector.kinds,
    }


@app.get("/api/tunnel", tags=["系统"], summary="隧道状态")
def tunnel_status(_: dict = Depends(require_staff)) -> dict[str, object]:
    """查询本机 cloudflared 临时隧道是否开启，以及公开 URL。"""
    return get_tunnel_status()


@app.post("/api/tunnel/start", tags=["系统"], summary="开启隧道")
def tunnel_start(_: dict = Depends(require_admin_role)) -> dict[str, object]:
    """启动 Cloudflare 快速隧道（需管理员）。"""
    return start_tunnel()


@app.post("/api/tunnel/stop", tags=["系统"], summary="关闭隧道")
def tunnel_stop(_: dict = Depends(require_admin_role)) -> dict[str, object]:
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
    summary="提交申请（需登录，先待付定金）",
)
def public_create_order_request(
    payload: OrderRequestCreate,
    request: Request,
    user: Optional[dict] = Depends(get_optional_user),
) -> dict:
    """须登录。创建为 pending_payment；确认 30% 定金后变为 submitted。"""
    rate_limit(request, limit=10, window=60.0)
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="login required to submit order")
    return order_requests_svc.create_request(payload, user_id=int(user["id"]))


@app.get(
    "/api/public/order-requests",
    response_model=list[OrderRequestPublicOut],
    tags=["顾客申请（公开）"],
    summary="公开申请列表",
)
def public_list_order_requests(
    request: Request,
    status: Optional[str] = Query(
        default=None,
        description="状态筛选：submitted / ordered / rejected（不含待付定金）",
    ),
) -> list[dict]:
    """顾客端可见的申请列表（字段已脱敏；不含未付定金草稿）。"""
    rate_limit(request, limit=30, window=60.0)
    return order_requests_svc.list_public_requests(status=status)


@app.get(
    "/api/public/order-requests/{code}",
    response_model=OrderRequestPublicOut,
    tags=["顾客申请（公开）"],
    summary="按编号查申请",
)
def public_get_order_request(code: str, request: Request) -> dict:
    """用申请编号（如 SG5-0001）查询进度。"""
    rate_limit(request, limit=30, window=60.0)
    return order_requests_svc.get_by_code(code)


@app.get(
    "/api/me/order-requests",
    response_model=list[OrderRequestPublicOut],
    tags=["顾客（登录）"],
    summary="我的申请",
)
def my_order_requests(
    user: Optional[dict] = Depends(get_optional_user),
    status: Optional[str] = Query(default=None),
) -> list[dict]:
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="login required")
    return order_requests_svc.list_for_user(int(user["id"]), status=status)


@app.post(
    "/api/me/order-requests/{code}/confirm-deposit",
    response_model=OrderRequestPublicOut,
    tags=["顾客（登录）"],
    summary="确认定金已付（正式提交）",
)
def my_confirm_deposit(
    code: str,
    payload: DepositConfirmIn = DepositConfirmIn(),
    user: Optional[dict] = Depends(get_optional_user),
) -> dict:
    """定金确认后 status → submitted。财务系统对接后由支付回调调用同等逻辑。"""
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="login required")
    return order_requests_svc.confirm_deposit(
        code=code, user_id=int(user["id"]), payment_ref=payload.payment_ref or "", staff=False
    )


@app.post(
    "/api/order-requests/{request_id}/confirm-deposit",
    response_model=OrderRequestOut,
    tags=["申请单（管理）"],
    summary="员工确认定金已付",
)
def staff_confirm_deposit(
    request_id: int,
    payload: DepositConfirmIn = DepositConfirmIn(),
    _: dict = Depends(require_warehouse),
) -> dict:
    return order_requests_svc.confirm_deposit(
        request_id=request_id, payment_ref=payload.payment_ref or "", staff=True
    )


@app.get(
    "/api/order-requests",
    response_model=list[OrderRequestOut],
    tags=["申请单（管理）"],
    summary="申请单列表",
)
def list_order_requests(
    status: Optional[str] = Query(default=None, description="状态筛选：submitted / ordered / rejected"),
    _: dict = Depends(require_staff),
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
    request_id: int, _: dict = Depends(require_staff)
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
    _: dict = Depends(require_warehouse),
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
    _: dict = Depends(require_warehouse),
) -> dict:
    """拒绝顾客申请并填写原因。"""
    return order_requests_svc.reject_request(request_id, payload)


@app.get("/api/stats", tags=["订单"], summary="状态统计", response_model=StatsOut)
def stats(_: dict = Depends(require_staff)) -> dict:
    """各订单/货品状态数量汇总。"""
    return orders_svc.get_stats()


@app.get("/api/shops", tags=["订单"], summary="店铺列表")
def shops(_: dict = Depends(require_staff)) -> list[str]:
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
    _: dict = Depends(require_staff),
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
    payload: OrderCreate, _: dict = Depends(require_warehouse)
) -> dict:
    """创建库存订单及明细行。"""
    return orders_svc.create_order(payload)


@app.get(
    "/api/orders/{order_id}",
    response_model=OrderOut,
    tags=["订单"],
    summary="订单详情",
)
def get_order(order_id: int, _: dict = Depends(require_staff)) -> dict:
    """按 ID 获取订单及明细。"""
    return orders_svc.get_order(order_id)


@app.patch(
    "/api/orders/{order_id}",
    response_model=OrderOut,
    tags=["订单"],
    summary="更新订单",
)
def update_order(
    order_id: int, payload: OrderUpdate, _: dict = Depends(require_warehouse)
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
    order_id: int, lines: list[LineCreate], _: dict = Depends(require_warehouse)
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
    order_id: int, payload: InboundCreate, _: dict = Depends(require_warehouse)
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
    _: dict = Depends(require_staff),
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
    payload: ItemCreate, _: dict = Depends(require_warehouse)
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
    payload: ItemBatchCreate, _: dict = Depends(require_warehouse)
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
    payload: ScrapeRequest, _: dict = Depends(require_warehouse)
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
def get_item(item_id: int, _: dict = Depends(require_staff)) -> dict:
    """按 ID 获取单条货品。"""
    return items_svc.get_item(item_id)


@app.patch(
    "/api/items/{item_id}",
    response_model=ItemOut,
    tags=["货品"],
    summary="更新货品",
)
def update_item(
    item_id: int, payload: ItemUpdate, _: dict = Depends(require_warehouse)
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
    _: dict = Depends(require_staff),
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
    payload: ShipmentCreate, _: dict = Depends(require_warehouse)
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
def get_shipment(shipment_id: int, _: dict = Depends(require_staff)) -> dict:
    """按 ID 获取运单。"""
    return shipments_svc.get_shipment(shipment_id)


@app.post(
    "/api/shipments/{shipment_id}/confirm",
    response_model=ShipmentOut,
    tags=["进库"],
    summary="确认到仓 / 签收",
)
def confirm_shipment(
    shipment_id: int, _: dict = Depends(require_warehouse)
) -> dict:
    """将运单标为已送达，并推进关联货品状态。"""
    return shipments_svc.confirm_shipment(shipment_id)


@app.get(
    "/api/stock-boxes",
    response_model=list[StockBoxOut],
    tags=["库存合箱"],
    summary="库存合箱列表",
)
def list_stock_boxes(_: dict = Depends(require_staff)) -> list[dict]:
    """在库合箱组（不走出库、不改货品状态）。"""
    return stock_boxes_svc.list_boxes()


@app.post(
    "/api/stock-boxes",
    response_model=StockBoxOut,
    tags=["库存合箱"],
    summary="创建库存合箱",
)
def create_stock_box(
    payload: StockBoxCreate, _: dict = Depends(require_warehouse)
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
    payload: StockBoxCreate, _: dict = Depends(require_warehouse)
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
    _: dict = Depends(require_warehouse),
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
    child_id: int, _: dict = Depends(require_warehouse)
) -> dict:
    """子箱变为独立主箱，订单仍在该箱内。"""
    return stock_boxes_svc.detach_child(child_id)


@app.get(
    "/api/stock-boxes/{box_id}",
    response_model=StockBoxOut,
    tags=["库存合箱"],
    summary="库存合箱详情",
)
def get_stock_box(box_id: int, _: dict = Depends(require_staff)) -> dict:
    return stock_boxes_svc.get_box(box_id)


@app.patch(
    "/api/stock-boxes/{box_id}",
    response_model=StockBoxOut,
    tags=["库存合箱"],
    summary="更新库存合箱",
)
def update_stock_box(
    box_id: int, payload: StockBoxUpdate, _: dict = Depends(require_warehouse)
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
    _: dict = Depends(require_warehouse),
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
    _: dict = Depends(require_warehouse),
) -> Optional[dict]:
    """移出后若箱空则自动删除并返回 null。"""
    return stock_boxes_svc.remove_orders(box_id, payload.order_ids)


@app.delete(
    "/api/stock-boxes/{box_id}",
    tags=["库存合箱"],
    summary="解散库存合箱",
)
def delete_stock_box(
    box_id: int, _: dict = Depends(require_warehouse)
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
    _: dict = Depends(require_staff),
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
    payload: OutboundBatchCreate, _: dict = Depends(require_warehouse)
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
def get_outbound_batch(batch_id: int, _: dict = Depends(require_staff)) -> dict:
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
    _: dict = Depends(require_finance),
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
    batch_id: int, _: dict = Depends(require_finance)
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
    _: dict = Depends(require_staff),
) -> dict:
    """按下单月与出库月分别汇总金额。"""
    return finance_svc.month_summary(month)


@app.get(
    "/api/reports/apply",
    tags=["统计"],
    summary="申请单日/月统计",
)
def report_apply(
    period: str = Query(default="month", description="day 或 month"),
    day: Optional[str] = Query(default=None, description="YYYY-MM-DD（period=day）"),
    month: Optional[str] = Query(default=None, description="YYYY-MM（period=month）"),
    limit: int = Query(default=10, ge=1, le=50),
    _: dict = Depends(require_staff),
) -> dict:
    """统计下单量、热门链接、花费最多用户、商品 IP（按申请创建时间）。"""
    if period not in ("day", "month"):
        raise HTTPException(status_code=400, detail="period must be day or month")
    return apply_stats_svc.apply_summary(
        period=period, day=day, month=month, limit=limit  # type: ignore[arg-type]
    )


@app.post(
    "/api/outbound-batches/{batch_id}/confirm",
    response_model=OutboundBatchOut,
    tags=["出库"],
    summary="确认出库批次签收",
)
def confirm_outbound_batch(
    batch_id: int, _: dict = Depends(require_warehouse)
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
    _: dict = Depends(require_staff),
) -> list[dict]:
    """最近写操作记录。"""
    return action_log_svc.list_logs(limit=limit)


@app.get(
    "/api/action-logs/latest",
    response_model=Optional[ActionLogOut],
    tags=["操作日志"],
    summary="最近可撤销操作",
)
def latest_action_log(_: dict = Depends(require_staff)) -> Optional[dict]:
    """返回最新一条尚未撤销、可撤销的操作（若有）。"""
    return action_log_svc.get_latest_undoable()


@app.post(
    "/api/action-logs/{log_id}/undo",
    response_model=ActionLogOut,
    tags=["操作日志"],
    summary="撤销操作",
)
def undo_action_log(
    log_id: int, _: dict = Depends(require_warehouse)
) -> dict:
    """按日志 ID 撤销对应写操作（若仍允许）。"""
    return action_log_svc.undo(log_id)


def _mount_spa() -> None:
    settings = get_settings()
    static_dir = settings.static_dir
    if not static_dir:
        # Default Docker / local prod path relative to backend root
        candidate = BACKEND_ROOT_PARENT / "frontend" / "dist"
        if candidate.is_dir():
            static_dir = candidate
    if not static_dir or not Path(static_dir).is_dir():
        return
    root = Path(static_dir)
    assets = root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="spa_assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api/") or full_path.startswith("media/"):
            raise HTTPException(status_code=404)
        target = root / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        index = root / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=404, detail="SPA not built")
        return FileResponse(index)


# Late import path for SPA (backend parent = stockgood root)
BACKEND_ROOT_PARENT = Path(__file__).resolve().parent.parent.parent
_mount_spa()
