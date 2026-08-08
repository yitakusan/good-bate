from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware

from app.admin_auth import require_admin
from app.clear_confirm import consume_clear_token, issue_clear_token
from app.database import (
    adjust_favorite_count,
    clear_scraped_data,
    connect,
    count_products,
    get_products_by_ids,
    init_db,
    latest_runs,
    list_events,
    list_filters,
    list_products,
)
from app.event_pipeline import EventPipeline
from app.exchange_rate import fetch_exchange_rate
from app.models import (
    AdminStatusOut,
    ClearDataOut,
    ClearDataPrepareOut,
    EventList,
    ExchangeRateOut,
    FilterOptions,
    HealthOut,
    ProductList,
    ScrapeRunOut,
    ScrapeSourceRunOut,
    SourceConfigOut,
    SourceRegistry,
    SourceRunOut,
)
from app.pipeline import ScrapePipeline
from app.product_display import enrich_product_display_names
from app.settings import get_settings
from app.source_config import load_sources
from app.source_registry import build_source_registry

logger = logging.getLogger(__name__)
settings = get_settings()


async def _run_full_scrape(
    limit_per_source: int | None = None,
    *,
    source_ids: list[str] | None = None,
    incremental: bool = False,
    include_events: bool = True,
) -> ScrapeRunOut:
    pipeline = ScrapePipeline(settings)
    try:
        product_result = await pipeline.run_all(
            limit_per_source=limit_per_source,
            source_ids=source_ids,
            incremental=incremental,
        )
    except Exception:
        logger.exception("product scrape failed")
        product_result = {"sources": 0, "stored": 0, "skipped": 0, "failed": 1}

    event_result: dict[str, int] = {"sources": 0, "stored": 0, "skipped": 0, "failed": 0}
    if include_events:
        try:
            event_result = await EventPipeline(settings).run_all(
                limit_per_source=limit_per_source,
                incremental=incremental,
            )
        except Exception:
            logger.exception("event scrape failed")
            event_result = {"sources": 0, "stored": 0, "skipped": 0, "failed": 1}

    return ScrapeRunOut(
        sources=product_result["sources"],
        stored=product_result["stored"],
        skipped=int(product_result.get("skipped") or 0),
        failed=product_result["failed"],
        events_stored=event_result["stored"],
        events_skipped=int(event_result.get("skipped") or 0),
    )


async def _scheduled_scrape_loop() -> None:
    hours = settings.scrape_interval_hours
    if hours <= 0:
        return
    interval = max(hours * 3600.0, 60.0)
    # 启动后稍等再跑，避免与健康检查/部署探测抢资源
    await asyncio.sleep(min(60.0, interval))
    while True:
        logger.info("scheduled scrape starting (interval=%.2fh, incremental=True)", hours)
        try:
            result = await _run_full_scrape(limit_per_source=None, incremental=True)
            logger.info(
                "scheduled scrape finished: sources=%s stored=%s skipped=%s failed=%s events=%s",
                result.sources,
                result.stored,
                result.skipped,
                result.failed,
                result.events_stored,
            )
        except Exception:
            logger.exception("scheduled scrape crashed")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db(settings.database_path)
    task: asyncio.Task[None] | None = None
    if settings.scrape_interval_hours > 0:
        logger.info(
            "enabling scheduled scrape every %.2f hours",
            settings.scrape_interval_hours,
        )
        task = asyncio.create_task(_scheduled_scrape_loop())
    yield
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.app_name,
    description=(
        "聚合日本电商与官方店的动漫周边新品与联动预告。\n\n"
        "- **商品**：查询已入库商品，支持搜索与筛选\n"
        "- **数据源**：查看 sources.json 配置、网站收录表与抓取历史\n"
        "- **抓取**：手动触发全部或单个数据源的抓取任务\n"
        "- **管理**：维护本地 SQLite 数据\n\n"
        "前端地址默认 http://localhost:5173 ，API 前缀为 `/api`。"
        "公网部署请设置环境变量 `ANIMEGOOD_ADMIN_TOKEN`。"
    ),
    version="0.1.0",
    lifespan=lifespan,
    openapi_tags=[
        {
            "name": "系统",
            "description": "健康检查等基础接口，用于确认后端是否正常运行。",
        },
        {
            "name": "商品",
            "description": "已入库商品的查询、发现页统计与筛选选项。",
        },
        {
            "name": "活动",
            "description": "联动预告、POP UP 等活动资讯。",
        },
        {
            "name": "数据源",
            "description": "抓取源配置、网站收录状态与历史运行记录。",
        },
        {
            "name": "抓取",
            "description": "手动触发抓取。STORES 类源需要本机已安装 Playwright Chromium。",
        },
        {
            "name": "管理",
            "description": "数据维护接口，请谨慎调用。配置 ANIMEGOOD_ADMIN_TOKEN 后需带口令。",
        },
        {
            "name": "工具",
            "description": "汇率等辅助信息，供前端展示。",
        },
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")


def _admin_dep(
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> None:
    require_admin(settings, x_admin_token)


@app.get(
    "/health",
    response_model=HealthOut,
    tags=["系统"],
    summary="健康检查",
    description="返回服务是否存活。`status` 为「正常」表示后端已启动且可接受请求。",
)
def health() -> HealthOut:
    return HealthOut(status="正常")


@api.get("/health", response_model=HealthOut, tags=["系统"], summary="健康检查", include_in_schema=False)
def api_health() -> HealthOut:
    return health()


@api.get(
    "/admin/status",
    response_model=AdminStatusOut,
    tags=["管理"],
    summary="管理鉴权状态",
    description="返回是否需要管理口令，以及定时抓取间隔（不泄露口令本身）。",
)
def admin_status() -> AdminStatusOut:
    return AdminStatusOut(
        auth_required=bool(settings.admin_token),
        scrape_interval_hours=settings.scrape_interval_hours,
    )


@api.get(
    "/products",
    response_model=ProductList,
    tags=["商品"],
    summary="商品列表",
    description=(
        "分页查询已入库商品。\n\n"
        "支持按关键词、IP、店铺、发售月份组合筛选。"
        "关键词会匹配商品名、IP 与店铺字段。"
    ),
)
def products(
    q: str | None = Query(default=None, max_length=100, description="搜索关键词，匹配商品名 / IP / 店铺 / 系列"),
    ip: str | None = Query(default=None, description="按归一化 IP 精确筛选，如「明日方舟」"),
    shop: str | None = Query(default=None, description="按店铺名称精确筛选"),
    series: str | None = Query(default=None, description="按系列名精确筛选，如「クリスマス」「よだか」"),
    release_month: str | None = Query(
        default=None,
        pattern=r"^\d{4}-\d{2}$",
        description="按发售月份筛选，格式 YYYY-MM，如 2026-07",
    ),
    stock_status: str | None = Query(
        default=None,
        description="按库存状态筛选，如 可购买 / 未开售 / 缺货",
    ),
    available_only: bool = Query(default=False, description="为 true 时仅返回可购买商品"),
    sort: str = Query(
        default="newest",
        pattern=r"^(newest|popular|price_asc|price_desc)$",
        description="排序：newest 最新 / popular 热度 / price_asc 价格升序 / price_desc 价格降序",
    ),
    limit: int = Query(default=60, ge=1, le=200, description="每页最多返回条数，默认 60，上限 200"),
    offset: int = Query(default=0, ge=0, description="分页偏移量，从 0 开始"),
) -> ProductList:
    with connect(settings.database_path) as conn:
        total = count_products(
            conn,
            q=q,
            ip=ip,
            shop=shop,
            series=series,
            release_month=release_month,
            stock_status=stock_status,
            available_only=available_only,
        )
        items = list_products(
            conn,
            q=q,
            ip=ip,
            shop=shop,
            series=series,
            release_month=release_month,
            stock_status=stock_status,
            available_only=available_only,
            sort=sort,
            limit=limit,
            offset=offset,
        )
        enrich_product_display_names(items, settings.name_glossary_path)
    return ProductList(items=items, total=total, limit=limit, offset=offset)


@api.get(
    "/products/by-ids",
    response_model=ProductList,
    tags=["商品"],
    summary="按 ID 批量取商品",
    description="用于收藏夹刷新价格/库存。最多 200 个 ID；不存在或已下架的 ID 会跳过。",
)
def products_by_ids(
    ids: list[int] = Query(default=[], max_length=200, description="商品 ID 列表"),
) -> ProductList:
    cleaned = [pid for pid in ids if pid >= 1][:200]
    with connect(settings.database_path) as conn:
        items = get_products_by_ids(conn, cleaned)
        enrich_product_display_names(items, settings.name_glossary_path)
    return ProductList(items=items, total=len(items), limit=len(cleaned), offset=0)


@api.post("/products/{product_id}/favorite", tags=["商品"], summary="更新收藏热度")
def update_favorite(
    product_id: int = Path(description="商品 ID", ge=1),
    delta: int = Query(description="收藏变化量，+1 或 -1", ge=-1, le=1),
) -> dict[str, int]:
    if delta == 0:
        raise HTTPException(status_code=400, detail="delta 不能为 0")
    try:
        with connect(settings.database_path) as conn:
            favorite_count = adjust_favorite_count(conn, product_id, delta)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"product_id": product_id, "favorite_count": favorite_count}


@api.get(
    "/filters",
    response_model=FilterOptions,
    tags=["商品"],
    summary="筛选选项",
    description="返回当前数据库中可用于下拉筛选的 IP、店铺、发售月份列表。",
)
def filters() -> FilterOptions:
    with connect(settings.database_path) as conn:
        return FilterOptions(**list_filters(conn))


@api.get("/events", response_model=EventList, tags=["活动"], summary="活动资讯列表")
def events(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> EventList:
    with connect(settings.database_path) as conn:
        items = list_events(conn, limit=limit, offset=offset)
    return EventList(items=items, limit=limit, offset=offset)


@api.get("/exchange-rate", response_model=ExchangeRateOut, tags=["工具"], summary="支付宝日元汇率")
async def exchange_rate() -> ExchangeRateOut:
    data, cached, fetched_at = await fetch_exchange_rate()
    return ExchangeRateOut(
        display=f"100 日元 ≈ {data.cny_per_100_jpy} 元（支付宝）",
        cny_per_100_jpy=data.cny_per_100_jpy,
        spot_cny_per_100_jpy=data.spot_cny_per_100_jpy,
        currency_name=data.currency_name,
        updated_at=fetched_at,
        source_url=data.source_url,
        cached=cached,
    )


@api.get("/sources", response_model=list[SourceConfigOut], tags=["数据源"], summary="数据源配置")
def sources() -> list[SourceConfigOut]:
    return [
        SourceConfigOut(
            id=item.id,
            shop=item.shop,
            source_platform=item.source_platform,
            base_url=str(item.base_url),
            collections=item.collections,
            enabled=item.enabled,
            priority=item.priority,
            difficulty=item.difficulty,
            core_ips=item.core_ips,
            notes=item.notes,
        )
        for item in load_sources(settings.source_config_path)
    ]


@api.get("/source-registry", response_model=SourceRegistry, tags=["数据源"], summary="网站收录表")
def source_registry() -> SourceRegistry:
    return build_source_registry(settings.database_path, settings.source_config_path)


@api.get(
    "/runs",
    response_model=list[SourceRunOut],
    tags=["数据源"],
    summary="最近抓取记录",
    description="按时间倒序返回最近的抓取运行记录，可用于排查某个数据源为何失败。",
)
def runs(limit: int = Query(default=20, ge=1, le=100, description="最多返回多少条记录，默认 20")) -> list[SourceRunOut]:
    with connect(settings.database_path) as conn:
        return latest_runs(conn, limit=limit)


@api.post(
    "/scrape/run",
    response_model=ScrapeRunOut,
    tags=["抓取"],
    summary="抓取已启用数据源",
    description=(
        "并发抓取商品源（可按 `source_ids` 勾选），可选同时抓活动。\n\n"
        "- `incremental=true`：只入库库中尚不存在的商品/活动（按 dedupe_key 查重），已有数据跳过不更新\n"
        "- `incremental=false`（默认）：全量 upsert，会刷新已有商品的价格/库存\n"
        "- `include_events=false`：只抓商品\n"
        "- 若配置了 `ANIMEGOOD_ADMIN_TOKEN`，须带请求头 `X-Admin-Token`"
    ),
    dependencies=[Depends(_admin_dep)],
)
async def run_scrape(
    limit_per_source: int | None = Query(
        default=None,
        ge=1,
        le=500,
        description="每个数据源最多抓取条数；留空表示不限制",
    ),
    source_ids: list[str] | None = Query(
        default=None,
        description="只抓这些商品源 ID；留空表示全部已启用源",
    ),
    incremental: bool = Query(
        default=False,
        description="为 true 时仅入库新数据，跳过已有 dedupe_key",
    ),
    include_events: bool = Query(
        default=True,
        description="是否同时抓取活动资讯源",
    ),
) -> ScrapeRunOut:
    return await _run_full_scrape(
        limit_per_source=limit_per_source,
        source_ids=source_ids,
        incremental=incremental,
        include_events=include_events,
    )


@api.post(
    "/scrape/events/run",
    tags=["抓取"],
    summary="抓取全部已启用活动源",
    description="仅抓取 `event_sources.json` 中 enabled=true 的活动资讯源，不影响商品数据。",
    dependencies=[Depends(_admin_dep)],
)
async def run_event_scrape(
    limit_per_source: int | None = Query(default=None, ge=1, le=500),
    incremental: bool = Query(default=False, description="仅入库新活动"),
) -> dict[str, int]:
    return await EventPipeline(settings).run_all(
        limit_per_source=limit_per_source,
        incremental=incremental,
    )


@api.post(
    "/scrape/run/{source_id}",
    response_model=ScrapeSourceRunOut,
    tags=["抓取"],
    summary="抓取指定数据源",
    description=(
        "只抓取某一个数据源，适合单独测试某家店。\n\n"
        "常见 `source_id` 示例：`mono-mo`、`shibuyatsutaya`、`csmcanvas`。"
        "可在「数据源配置」接口中查看完整列表。"
    ),
    dependencies=[Depends(_admin_dep)],
)
async def run_scrape_source(
    source_id: str = Path(description="数据源 ID，对应 sources.json 中的 id 字段"),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=500,
        description="本次最多抓取条数；留空表示不限制",
    ),
    incremental: bool = Query(default=False, description="仅入库新商品"),
) -> ScrapeSourceRunOut:
    source = next(
        (item for item in load_sources(settings.source_config_path) if item.id == source_id),
        None,
    )
    if source is None:
        raise HTTPException(status_code=404, detail=f"未找到数据源：{source_id}")

    pipeline = ScrapePipeline(settings)
    result = await pipeline.run_source(source, limit=limit, incremental=incremental)
    return ScrapeSourceRunOut(**result)


@api.post(
    "/admin/clear-scraped-data/prepare",
    response_model=ClearDataPrepareOut,
    tags=["管理"],
    summary="准备清空抓取数据（第一步）",
    description=(
        "发起清空前的准备请求，返回确认令牌。\n\n"
        "为防止误触，须等待 **3 秒** 后再调用「确认清空」接口。"
        "令牌有效期 120 秒，超时需重新准备。"
    ),
    dependencies=[Depends(_admin_dep)],
)
def prepare_clear_data() -> ClearDataPrepareOut:
    token, wait_seconds, expires_in = issue_clear_token()
    return ClearDataPrepareOut(
        token=token,
        wait_seconds=wait_seconds,
        expires_in=expires_in,
        message=f"已发起清空准备，请等待 {wait_seconds} 秒后确认。",
    )


@api.post(
    "/admin/clear-scraped-data/confirm",
    response_model=ClearDataOut,
    tags=["管理"],
    summary="确认清空抓取数据（第二步）",
    description=(
        "携带准备接口返回的 `token` 执行清空。\n\n"
        "须距准备请求至少 3 秒，否则返回 400。"
        "此操作不可恢复，会删除全部商品与抓取记录。"
    ),
    dependencies=[Depends(_admin_dep)],
)
def confirm_clear_data(
    token: str = Query(description="准备接口返回的确认令牌"),
) -> ClearDataOut:
    try:
        consume_clear_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with connect(settings.database_path) as conn:
        result = clear_scraped_data(conn)
    return ClearDataOut(**result)


app.include_router(api)
