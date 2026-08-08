from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


ItemStatus = Literal[
    "ordered",
    "inbound_shipped",
    "in_stock",
    "outbound_shipped",
    "delivered",
    "cancelled",
]
OrderStatus = ItemStatus
ShipmentStatus = Literal["shipped", "delivered"]
ShipmentDirection = Literal["inbound", "outbound"]
Carrier = Literal["yamato", "sagawa", "other"]
ExpectedShipPeriod = Literal["early", "mid", "late"]


class LineCreate(BaseModel):
    name: str = Field(min_length=1)
    shop: str = ""
    qty: int = Field(default=1, ge=1)
    unit_cost: Optional[float] = None
    note: str = ""
    animegood_product_id: Optional[int] = None
    ip: str = ""
    product_kind: str = ""
    image_url: str = ""
    source_url: str = ""
    expected_ship_at: Optional[str] = None
    expected_ship_period: Optional[ExpectedShipPeriod] = None
    barcode: str = ""


class LineOut(BaseModel):
    id: int
    order_id: int
    name: str
    shop: str
    order_ref: str
    qty: int
    unit_cost: Optional[float]
    status: ItemStatus
    ordered_at: str
    arrived_at: Optional[str]
    expected_ship_at: Optional[str] = None
    expected_ship_period: Optional[ExpectedShipPeriod] = None
    barcode: str = ""
    note: str
    animegood_product_id: Optional[int]
    ip: str
    product_kind: str = ""
    image_url: str
    source_url: str = ""
    inbound_tracking_no: Optional[str] = None
    inbound_carrier: Optional[Carrier] = None
    inbound_tracking_url: Optional[str] = None
    inbound_shipment_id: Optional[int] = None
    outbound_tracking_no: Optional[str] = None
    outbound_carrier: Optional[Carrier] = None
    outbound_tracking_url: Optional[str] = None
    outbound_shipment_id: Optional[int] = None
    outbound_box_no: Optional[int] = None


class OrderCreate(BaseModel):
    order_ref: str = ""
    shop: str = ""
    order_qty: Optional[int] = None
    shipping_fee: Optional[float] = Field(default=None, ge=0)
    exchange_rate: Optional[float] = Field(default=None, gt=0)
    order_image_url: str = ""
    note: str = ""
    expected_ship_at: Optional[str] = None
    expected_ship_period: Optional[ExpectedShipPeriod] = None
    lines: list[LineCreate] = Field(min_length=1)


class OrderUpdate(BaseModel):
    order_ref: Optional[str] = None
    shop: Optional[str] = None
    order_qty: Optional[int] = None
    shipping_fee: Optional[float] = Field(default=None, ge=0)
    # None clears rate; positive validated in service
    exchange_rate: Optional[float] = None
    order_image_url: Optional[str] = None
    note: Optional[str] = None
    expected_ship_at: Optional[str] = None
    expected_ship_period: Optional[ExpectedShipPeriod] = None
    status: Optional[OrderStatus] = None  # only cancelled via PATCH


class OrderOut(BaseModel):
    id: int
    order_ref: str
    shop: str
    status: OrderStatus
    ordered_at: str
    order_qty: Optional[int] = None
    shipping_fee: Optional[float] = None
    exchange_rate: Optional[float] = None
    order_image_url: str = ""
    note: str = ""
    expected_ship_at: Optional[str] = None
    expected_ship_period: Optional[ExpectedShipPeriod] = None
    line_count: int = 0
    total_qty: int = 0
    goods_total: Optional[float] = None
    order_total: Optional[float] = None
    goods_total_cny: Optional[float] = None
    shipping_fee_cny: Optional[float] = None
    order_total_cny: Optional[float] = None
    lines: list[LineOut] = []


class ItemCreate(BaseModel):
    """Legacy flat create — attaches/creates an order by order_ref."""
    name: str = Field(min_length=1)
    shop: str = ""
    order_ref: str = ""
    qty: int = Field(default=1, ge=1)
    unit_cost: Optional[float] = None
    note: str = ""
    animegood_product_id: Optional[int] = None
    ip: str = ""
    product_kind: str = ""
    image_url: str = ""
    source_url: str = ""
    expected_ship_at: Optional[str] = None
    expected_ship_period: Optional[ExpectedShipPeriod] = None
    barcode: str = ""
    order_qty: Optional[int] = None
    order_image_url: str = ""


class ItemUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    shop: Optional[str] = None
    order_ref: Optional[str] = None
    qty: Optional[int] = Field(default=None, ge=1)
    unit_cost: Optional[float] = None
    note: Optional[str] = None
    status: Optional[ItemStatus] = None
    animegood_product_id: Optional[int] = None
    ip: Optional[str] = None
    product_kind: Optional[str] = None
    image_url: Optional[str] = None
    source_url: Optional[str] = None
    expected_ship_at: Optional[str] = None
    expected_ship_period: Optional[ExpectedShipPeriod] = None
    barcode: Optional[str] = None


class ItemOut(LineOut):
    order_qty: Optional[int] = None
    order_image_url: str = ""


class ScrapeRequest(BaseModel):
    url: str = ""
    html: Optional[str] = None

    @model_validator(mode="after")
    def require_url_or_html(self) -> "ScrapeRequest":
        if not (self.url or "").strip() and not (self.html or "").strip():
            raise ValueError("url or html required")
        return self


class ScrapeProduct(BaseModel):
    name: str
    shop: str = ""
    unit_cost: Optional[float] = None
    image_url: str = ""
    source_url: str = ""
    ip: str = ""
    barcode: str = ""
    qty: Optional[int] = Field(default=None, ge=1)
    expected_ship_at: Optional[str] = None
    expected_ship_period: Optional[ExpectedShipPeriod] = None
    release_date: Optional[str] = None


class ScrapeResult(BaseModel):
    kind: Literal["list"] = "list"
    products: list[ScrapeProduct]
    message: str = ""
    order_ref: str = ""
    shipping_fee: Optional[float] = None
    order_total: Optional[float] = None


class ItemBatchCreate(BaseModel):
    items: list[ItemCreate] = Field(min_length=1)


class InboundCreate(BaseModel):
    tracking_no: str = ""
    carrier: Carrier = "other"
    item_ids: list[int] = Field(min_length=1)


class ShipmentCreate(BaseModel):
    """Legacy; inbound should prefer /orders/{id}/inbound."""
    tracking_no: str = ""
    direction: ShipmentDirection = "inbound"
    carrier: Carrier = "other"
    item_ids: list[int] = Field(min_length=1)
    order_id: Optional[int] = None


class ShipmentItemOut(BaseModel):
    id: int
    order_id: Optional[int] = None
    order_ref: str = ""
    name: str
    shop: str
    qty: int
    status: ItemStatus
    barcode: str = ""


class OrderGroupOut(BaseModel):
    order_id: Optional[int] = None
    order_ref: str = ""
    items: list[ShipmentItemOut] = []


class ShipmentOut(BaseModel):
    id: int
    direction: ShipmentDirection
    carrier: Carrier
    tracking_no: str
    tracking_url: Optional[str] = None
    shipped_at: str
    delivered_at: Optional[str]
    status: ShipmentStatus
    order_id: Optional[int] = None
    batch_id: Optional[int] = None
    box_no: Optional[int] = None
    items: list[ShipmentItemOut] = []
    order_groups: list[OrderGroupOut] = []


class OutboundBoxCreate(BaseModel):
    box_no: Optional[int] = Field(default=None, ge=1)
    carrier: Carrier = "other"
    tracking_no: str = Field(min_length=1)
    item_ids: list[int] = Field(min_length=1)


class OutboundBatchCreate(BaseModel):
    note: str = ""
    boxes: list[OutboundBoxCreate] = Field(min_length=1)
    allow_missing_barcode: bool = False
    missing_barcode_note: str = ""
    freight_exchange_rate: Optional[float] = Field(default=None, gt=0)
    freight_unit_price_jpy: Optional[float] = Field(default=None, ge=0)
    chargeable_weight: Optional[float] = Field(default=None, ge=0)


class OutboundBatchFinanceUpdate(BaseModel):
    freight_exchange_rate: Optional[float] = Field(default=None, gt=0)
    freight_unit_price_jpy: Optional[float] = Field(default=None, ge=0)
    chargeable_weight: Optional[float] = Field(default=None, ge=0)
    amount_received_cny: Optional[float] = Field(default=None, ge=0)
    payment_note: Optional[str] = None


class OutboundBoxOut(BaseModel):
    id: int
    batch_id: int
    box_no: int
    carrier: Carrier
    tracking_no: str
    tracking_url: Optional[str] = None
    status: ShipmentStatus
    shipped_at: str
    delivered_at: Optional[str] = None
    items: list[ShipmentItemOut] = []
    order_groups: list[OrderGroupOut] = []


class OutboundBatchOut(BaseModel):
    id: int
    note: str
    created_at: str
    boxes: list[OutboundBoxOut] = []
    box_count: int = 0
    item_count: int = 0
    goods_jpy: Optional[float] = None
    order_shipping_jpy: Optional[float] = None
    goods_receivable_cny: Optional[float] = None
    freight_exchange_rate: Optional[float] = None
    freight_unit_price_jpy: Optional[float] = None
    chargeable_weight: Optional[float] = None
    freight_cny: Optional[float] = None
    amount_receivable_cny: Optional[float] = None
    amount_received_cny: float = 0
    amount_unreceived_cny: Optional[float] = None
    payment_status: Literal["unpaid", "partial", "paid"] = "unpaid"
    payment_note: str = ""


class FinanceMonthBucket(BaseModel):
    goods_jpy: float = 0
    shipping_jpy: float = 0
    total_jpy: float = 0
    goods_cny: Optional[float] = None
    shipping_cny: Optional[float] = None
    total_cny: Optional[float] = None
    order_count: int = 0
    missing_rate_count: int = 0


class FinanceOutboundBucket(BaseModel):
    goods_jpy: float = 0
    goods_receivable_cny: Optional[float] = None
    freight_cny: Optional[float] = None
    amount_receivable_cny: Optional[float] = None
    amount_received_cny: float = 0
    amount_unreceived_cny: Optional[float] = None
    batch_count: int = 0


class FinanceSummaryOut(BaseModel):
    month: str
    ordered: FinanceMonthBucket
    outbound: FinanceOutboundBucket


class StockBoxLineOut(BaseModel):
    id: int
    order_id: int
    name: str
    shop: str = ""
    order_ref: str = ""
    qty: int
    status: ItemStatus
    image_url: str = ""
    barcode: str = ""
    ip: str = ""
    product_kind: str = ""
    note: str = ""
    source_url: str = ""


class StockBoxOrderOut(BaseModel):
    id: int
    order_ref: str = ""
    shop: str = ""
    status: OrderStatus
    line_count: int = 0
    total_qty: int = 0
    lines: list[StockBoxLineOut] = []


class StockBoxCreate(BaseModel):
    order_ids: list[int] = Field(min_length=1)
    note: str = ""
    box_no: Optional[int] = Field(default=None, ge=1)


class StockBoxUpdate(BaseModel):
    note: Optional[str] = None
    box_no: Optional[int] = Field(default=None, ge=1)


class StockBoxOrdersPayload(BaseModel):
    order_ids: list[int] = Field(min_length=1)


class StockBoxMergeChild(BaseModel):
    child_box_id: int = Field(ge=1)


class StockBoxChildOut(BaseModel):
    id: int
    box_no: int
    note: str = ""
    order_count: int = 0
    item_count: int = 0


class StockBoxOut(BaseModel):
    id: int
    box_no: int
    note: str = ""
    created_at: str
    parent_id: Optional[int] = None
    parent_box_no: Optional[int] = None
    child_boxes: list[StockBoxChildOut] = []
    order_ids: list[int] = []
    order_count: int = 0
    item_count: int = 0
    orders: list[StockBoxOrderOut] = []


class StatsOut(BaseModel):
    ordered: int
    inbound_shipped: int
    in_stock: int
    outbound_shipped: int
    delivered: int
    cancelled: int
    inbound_shipments_shipped: int
    outbound_shipments_shipped: int
    shipments_delivered: int
    orders_total: int = 0


class ActionLogOut(BaseModel):
    id: int
    action_type: str
    summary: str
    created_at: str
    undone_at: Optional[str] = None
    undoable: bool = False


# --- Customer order requests (C-end apply) ---

OrderRequestStatus = Literal["submitted", "ordered", "rejected"]


class OrderRequestCreate(BaseModel):
    name: str = Field(min_length=1)
    shop: str = ""
    unit_cost: Optional[float] = None
    image_url: str = ""
    source_url: str = Field(min_length=1)
    ip: str = ""
    barcode: str = ""
    qty: int = Field(default=1, ge=1)
    contact: str = ""
    note: str = ""


class OrderRequestConfirm(BaseModel):
    shop_order_ref: str = Field(min_length=1)
    staff_note: str = ""
    create_stock_order: bool = True
    shipping_fee: Optional[float] = Field(default=0, ge=0)
    exchange_rate: Optional[float] = Field(default=None, gt=0)


class OrderRequestReject(BaseModel):
    reject_reason: str = Field(min_length=1)


class OrderRequestOut(BaseModel):
    id: int
    request_code: str
    status: OrderRequestStatus
    name: str
    shop: str
    unit_cost: Optional[float] = None
    image_url: str = ""
    source_url: str = ""
    ip: str = ""
    barcode: str = ""
    qty: int
    contact: str = ""
    note: str = ""
    shop_order_ref: str = ""
    ordered_at: Optional[str] = None
    staff_note: str = ""
    reject_reason: str = ""
    stock_order_id: Optional[int] = None
    created_at: str
    updated_at: str


class OrderRequestPublicOut(BaseModel):
    """Customer-facing subset."""

    request_code: str
    status: OrderRequestStatus
    name: str
    shop: str
    unit_cost: Optional[float] = None
    amount: Optional[float] = None
    image_url: str = ""
    source_url: str = ""
    qty: int
    shop_order_ref: str = ""
    ordered_at: Optional[str] = None
    staff_note: str = ""
    reject_reason: str = ""
    created_at: str
    updated_at: str
    status_label: str = ""
