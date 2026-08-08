from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ProductOut(BaseModel):
    """前台展示用的单条商品信息。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "product_name": "【渋谷店受取】Ado『よだか』通常盤(DVD)",
                "series": "よだか",
                "ip": "未分类",
                "shop": "SHIBUYA TSUTAYA",
                "source_url": "https://shibuyatsutaya.stores.jp/items/6a49f2e550f81de53c4c910d",
                "price": 6600,
                "stock_status": "可购买",
                "release_date": None,
                "preorder_date": None,
                "image_url": "https://example.com/image.jpg",
                "first_seen": "2026-07-06T03:00:00+00:00",
                "source_platform": "base-stores",
            }
        }
    )

    id: int = Field(description="商品 ID，数据库自增主键")
    product_name: str = Field(description="商品名称（日文原名）")
    display_name_zh: str | None = Field(
        default=None,
        description="中文展示名；由本地术语表 name_glossary.json 替换生成",
    )
    series: str = Field(
        default="",
        description="从商品名解析的系列名，如「クリスマス」「よだか」；解析不到为空字符串",
    )
    ip: str = Field(description="归一化后的 IP 名称，如「明日方舟」「女神异闻录」")
    shop: str = Field(description="来源店铺名称")
    source_url: str = Field(description="商品在原站的详情页链接")
    price: int | None = Field(default=None, description="价格（日元）；未解析到时为 null")
    stock_status: str = Field(
        default="未知",
        description="库存状态：可购买 / 未开售 / 缺货 / 已结束 / 未知",
    )
    release_date: str | None = Field(default=None, description="发售日期，格式 YYYY-MM-DD 或 YYYY-MM-上旬 等")
    preorder_date: str | None = Field(default=None, description="预约开始日期")
    image_url: str | None = Field(default=None, description="商品主图 URL")
    first_seen: str = Field(description="本系统首次发现该商品的时间（UTC ISO 8601）")
    source_platform: str = Field(
        description="抓取平台类型，如 shopify、ec-cube、base-stores",
    )
    favorite_count: int = Field(default=0, description="全站收藏次数，用于热度展示")


class ProductList(BaseModel):
    """分页商品列表响应。"""

    items: list[ProductOut] = Field(description="当前页商品列表")
    total: int = Field(default=0, description="符合当前筛选条件的总条数（不受分页影响）")
    limit: int = Field(description="本次请求每页条数上限")
    offset: int = Field(description="分页偏移量，从 0 开始")


class AdminStatusOut(BaseModel):
    """前端据此判断管理操作是否需要口令。"""

    auth_required: bool = Field(description="为 true 时抓取/清空须带 X-Admin-Token")
    scrape_interval_hours: float = Field(description="定时抓取间隔（小时）；0 表示关闭")


class EventOut(BaseModel):
    """活动资讯条目，用于首页轮播展示。"""

    id: int
    title: str
    summary: str = ""
    ip: str = "未分类"
    shop: str
    source_url: str
    image_url: str | None = None
    published_at: str | None = None
    ends_at: str | None = None
    first_seen: str
    source_platform: str


class EventList(BaseModel):
    items: list[EventOut]
    limit: int
    offset: int


class FilterOptions(BaseModel):
    """前端筛选下拉框的可选项，由已入库商品动态汇总。"""

    ips: list[str] = Field(default_factory=list, description="可选 IP 列表（去重排序）")
    shops: list[str] = Field(default_factory=list, description="可选店铺列表（去重排序）")
    release_months: list[str] = Field(
        default_factory=list,
        description="可选发售月份列表，格式 YYYY-MM",
    )
    series: list[str] = Field(
        default_factory=list,
        description="可选系列名列表（从商品名解析，去重排序）",
    )


class SourceRunOut(BaseModel):
    """单次数据源抓取运行的历史记录。"""

    id: int = Field(description="运行记录 ID")
    source_id: str = Field(description="数据源 ID，对应 sources.json 中的 id")
    shop: str = Field(description="店铺名称")
    source_platform: str = Field(description="平台类型，如 shopify、base-stores")
    status: str = Field(description="运行结果：成功 / 失败")
    message: str | None = Field(default=None, description="失败时的错误信息；成功时通常为 null")
    product_count: int = Field(description="本次运行新入库或更新的商品条数")
    started_at: str = Field(description="抓取开始时间（UTC ISO 8601）")
    finished_at: str = Field(description="抓取结束时间（UTC ISO 8601）")


class ScrapeRunOut(BaseModel):
    """批量抓取全部已启用数据源的汇总结果。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"sources": 10, "stored": 85, "skipped": 40, "failed": 1},
        }
    )

    sources: int = Field(description="参与抓取的数据源总数（仅 enabled=true）")
    stored: int = Field(description="本次新入库（增量）或写入/更新（全量）的商品条数")
    skipped: int = Field(default=0, description="增量模式下因已存在而跳过的条数")
    failed: int = Field(description="抓取失败的数据源数量")
    events_stored: int = Field(default=0, description="活动资讯入库条数")
    events_skipped: int = Field(default=0, description="活动增量跳过条数")


class ScrapeSourceRunOut(BaseModel):
    """单个数据源的抓取结果。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "source_id": "shibuyatsutaya",
                "status": "成功",
                "stored": 5,
                "skipped": 12,
                "message": None,
            }
        }
    )

    source_id: str = Field(description="数据源 ID")
    status: str = Field(description="运行结果：成功 / 失败")
    stored: int = Field(description="本次入库商品条数")
    skipped: int = Field(default=0, description="增量模式下跳过的已有商品条数")
    message: str | None = Field(default=None, description="失败时的错误信息；成功时为 null")


class SourceRegistryItem(BaseModel):
    """网站收录表中的单行记录，合并配置与运行统计。"""

    id: str = Field(description="数据源 ID")
    shop: str = Field(description="店铺显示名称")
    base_url: str = Field(description="网站首页地址")
    source_platform: str = Field(description="平台类型：shopify / base-stores / ec-cube 等")
    enabled: bool = Field(description="是否在 sources.json 中启用抓取")
    inclusion_status: str = Field(description="收录状态：已收录（enabled=true）/ 未收录")
    difficulty: str = Field(description="抓取难度：极低 / 低 / 中低 / 中 / 中高 / 高")
    priority: int = Field(description="抓取优先级，数字越小越优先")
    core_ips: list[str] = Field(default_factory=list, description="该站重点关注的 IP 列表")
    notes: str | None = Field(default=None, description="人工备注，如接入说明或限制")
    product_count: int = Field(description="当前数据库中该数据源的商品总数")
    last_run_status: str | None = Field(default=None, description="最近一次抓取状态：成功 / 失败")
    last_run_at: str | None = Field(default=None, description="最近一次抓取完成时间")
    last_run_message: str | None = Field(default=None, description="最近一次抓取的错误或备注")


class SourceRegistry(BaseModel):
    """网站收录总览，供前端收录表展示。"""

    items: list[SourceRegistryItem] = Field(description="全部已登记网站列表")
    included_count: int = Field(description="已收录（enabled=true）的网站数")
    excluded_count: int = Field(description="未收录（enabled=false）的网站数")
    easy_pending_count: int = Field(
        description="未收录但难度为极低/低/中低的网站数，适合优先接入",
    )


class SourceConfigOut(BaseModel):
    """sources.json 中的单条数据源配置。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "shibuyatsutaya",
                "shop": "SHIBUYA TSUTAYA",
                "source_platform": "base-stores",
                "base_url": "https://shibuyatsutaya.stores.jp/",
                "collections": [],
                "enabled": True,
                "priority": 3,
                "difficulty": "低",
                "core_ips": [],
                "notes": "STORES 源，需 Playwright 渲染首页列表。",
            }
        }
    )

    id: str = Field(description="唯一标识，用于 /api/scrape/run/{source_id}")
    shop: str = Field(description="店铺名称")
    source_platform: Literal[
        "shopify",
        "ec-cube",
        "base-stores",
        "ochanoko",
        "color-me",
        "futureshop",
        "large-ec",
    ] = Field(description="解析器模板类型")
    base_url: HttpUrl = Field(description="网站根地址")
    collections: list[str] = Field(default_factory=list, description="子分类或集合路径（Shopify 等使用）")
    enabled: bool = Field(default=True, description="是否参与定时/批量抓取")
    priority: int = Field(default=3, description="抓取优先级，数字越小越靠前")
    difficulty: str = Field(default="中", description="抓取难度标签")
    core_ips: list[str] = Field(default_factory=list, description="重点 IP 列表")
    notes: str | None = Field(default=None, description="备注说明")


class HealthOut(BaseModel):
    """服务健康状态。"""

    status: str = Field(description="运行状态，正常时为「正常」")


class ClearDataOut(BaseModel):
    """清空抓取数据后的统计。"""

    deleted_products: int = Field(description="删除的商品记录数")
    deleted_runs: int = Field(description="删除的抓取运行记录数")


class ClearDataPrepareOut(BaseModel):
    """清空数据的第一步：获取确认令牌。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "token": "abc123-example-token",
                "wait_seconds": 3,
                "expires_in": 120,
                "message": "已发起清空准备，请等待 3 秒后调用确认接口。",
            }
        }
    )

    token: str = Field(description="确认令牌，须在等待后携带到确认接口")
    wait_seconds: int = Field(description="确认前必须等待的秒数，用于防止误触")
    expires_in: int = Field(description="令牌有效时间（秒），超时需重新准备")
    message: str = Field(description="操作提示")


class ExchangeRateOut(BaseModel):
    """支付宝日元汇率，供首页右上角展示。"""

    display: str = Field(description="展示文案，如「100 日元 ≈ 4.204 元（支付宝）」")
    cny_per_100_jpy: float = Field(description="100 日元兑换人民币（支付宝汇率）")
    spot_cny_per_100_jpy: float = Field(description="100 日元兑换人民币（中间价，未加支付宝 markup）")
    currency_name: str = Field(default="日元", description="外币名称")
    updated_at: str | None = Field(default=None, description="本系统最近抓取时间（JST）")
    source_url: str = Field(description="汇率来源页面")
    cached: bool = Field(default=False, description="本次响应是否来自服务端缓存")
