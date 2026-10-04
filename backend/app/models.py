"""Pydantic v2 request/response schemas.

Every response model exposes ids as plain strings: ObjectId is converted at the
serialisation boundary so FastAPI never tries to JSON-encode a BSON type.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def serialize_doc(document: dict[str, Any] | None) -> dict[str, Any] | None:
    """Recursively convert ObjectId values to str so responses are JSON safe."""
    if document is None:
        return None
    output: dict[str, Any] = {}
    for key, value in document.items():
        out_key = "id" if key == "_id" else key
        output[out_key] = _serialize_value(value)
    return output


def _serialize_value(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {("id" if k == "_id" else k): _serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    return value


def to_object_id(value: str, field_name: str = "id") -> ObjectId:
    from fastapi import HTTPException, status

    if not ObjectId.is_valid(value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field_name}: {value!r} is not a valid identifier",
        )
    return ObjectId(value)


class StockStatus(str, Enum):
    ALL = "ALL"
    IN_STOCK = "IN_STOCK"
    LOW_STOCK = "LOW_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"


class PaymentMethod(str, Enum):
    CASH = "CASH"
    CARD = "CARD"
    SPLIT = "SPLIT"


class LedgerType(str, Enum):
    """Returns live in the `sales` collection as negative-value documents.

    Keeping them in one ledger means every existing aggregation — revenue,
    profit, category mix, sales velocity — nets refunds out automatically,
    instead of each report having to remember to subtract a second collection.
    """

    SALE = "SALE"
    RETURN = "RETURN"


class RefundMethod(str, Enum):
    CASH = "CASH"
    CARD = "CARD"


class UserRole(str, Enum):
    OWNER = "OWNER"
    CASHIER = "CASHIER"


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    username: str
    full_name: str
    role: UserRole
    email: str | None = None
    phone: str | None = None
    # A small square data: URI. The frontend downscales before upload, so this
    # stays well inside the document size limit and needs no file storage.
    avatar_url: str | None = None


AVATAR_PREFIXES = ("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,")
AVATAR_MAX_CHARS = 400_000


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    # Pass null to clear the photo; omit the field to leave it untouched.
    avatar_url: str | None = Field(default=None, max_length=AVATAR_MAX_CHARS)

    @field_validator("avatar_url")
    @classmethod
    def avatar_must_be_an_inline_image(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        if not value.startswith(AVATAR_PREFIXES):
            raise ValueError("Photo must be a PNG, JPEG or WebP image")
        return value

    @field_validator("email")
    @classmethod
    def email_must_look_like_one(cls, value: str | None) -> str | None:
        if not value:
            return None
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Enter a valid email address")
        return value


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# --------------------------------------------------------------------------- #
# Products
# --------------------------------------------------------------------------- #
class ProductBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    barcode: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    # A supermarket stocks the same item under several brands, so the
    # brand is its own field rather than being buried in the name.
    brand: str | None = Field(default=None, max_length=64)
    category: str = Field(min_length=1, max_length=64)
    buying_price: float = Field(ge=0)
    market_price: float = Field(ge=0)
    selling_price: float = Field(ge=0)
    discount_percentage: float = Field(default=0.0, ge=0, le=100)
    stock_shelf: int = Field(default=0, ge=0)
    stock_warehouse: int = Field(default=0, ge=0)
    reorder_threshold: int = Field(default=10, ge=0)
    image_url: str | None = Field(default=None, max_length=512)
    is_active: bool = True

    @field_validator("barcode")
    @classmethod
    def barcode_has_no_spaces(cls, value: str) -> str:
        cleaned = value.strip()
        if " " in cleaned:
            raise ValueError("Barcode cannot contain spaces")
        return cleaned


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    barcode: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    brand: str | None = Field(default=None, max_length=64)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    buying_price: float | None = Field(default=None, ge=0)
    market_price: float | None = Field(default=None, ge=0)
    selling_price: float | None = Field(default=None, ge=0)
    discount_percentage: float | None = Field(default=None, ge=0, le=100)
    stock_shelf: int | None = Field(default=None, ge=0)
    stock_warehouse: int | None = Field(default=None, ge=0)
    reorder_threshold: int | None = Field(default=None, ge=0)
    image_url: str | None = Field(default=None, max_length=512)
    is_active: bool | None = None


class ProductOut(BaseModel):
    id: str
    barcode: str
    name: str
    brand: str | None = None
    category: str
    buying_price: float
    market_price: float
    selling_price: float
    discount_percentage: float
    stock_shelf: int
    stock_warehouse: int
    stock_total: int
    reorder_threshold: int
    image_url: str | None = None
    is_active: bool
    effective_selling_price: float
    unit_profit: float
    margin_percent: float
    status: StockStatus
    updated_at: datetime | None = None


class ProductPage(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int


class StockAdjustRequest(BaseModel):
    delta_shelf: int = 0
    delta_warehouse: int = 0
    reason: str = Field(default="Manual adjustment", min_length=1, max_length=200)


class StockTransferRequest(BaseModel):
    quantity: int = Field(gt=0)
    reason: str = Field(default="Warehouse to shelf replenishment", min_length=1, max_length=200)


# --------------------------------------------------------------------------- #
# Sales / POS
# --------------------------------------------------------------------------- #
class CheckoutItem(BaseModel):
    product_id: str
    quantity: int = Field(gt=0, le=10_000)
    # Optional per-line override; falls back to the product discount when omitted.
    discount_percentage: float | None = Field(default=None, ge=0, le=100)


class PaymentBreakdown(BaseModel):
    cash: float = Field(default=0.0, ge=0)
    card: float = Field(default=0.0, ge=0)


class CheckoutRequest(BaseModel):
    items: list[CheckoutItem] = Field(min_length=1)
    payment_method: PaymentMethod = PaymentMethod.CASH
    payment_breakdown: PaymentBreakdown | None = None
    customer_id: str | None = None
    amount_tendered: float | None = Field(default=None, ge=0)


class SaleItemOut(BaseModel):
    product_id: str
    barcode: str
    name: str
    quantity: int
    unit_buying_price: float
    unit_selling_price: float
    discount_percentage: float
    line_total: float
    line_profit: float


class ReturnItem(BaseModel):
    product_id: str
    quantity: int = Field(gt=0, le=10_000)


class ReturnRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    items: list[ReturnItem] = Field(min_length=1)
    reason: str = Field(min_length=3, max_length=200)
    # Damaged or spoiled goods go back out of circulation, not onto the shelf.
    restock: bool = True
    refund_method: RefundMethod = RefundMethod.CASH


class ReturnableLine(BaseModel):
    product_id: str
    barcode: str
    name: str
    quantity_sold: int
    quantity_returned: int
    quantity_remaining: int
    unit_selling_price: float
    discount_percentage: float
    refund_per_unit: float


class ReturnableSale(BaseModel):
    sale_id: str
    receipt_number: str
    timestamp: datetime
    customer_name: str | None = None
    grand_total: float
    lines: list[ReturnableLine]
    fully_returned: bool


class SaleOut(BaseModel):
    id: str
    receipt_number: str
    cashier_id: str
    customer_id: str | None = None
    customer_name: str | None = None
    items: list[SaleItemOut]
    subtotal: float
    discount_total: float
    tax_amount: float
    grand_total: float
    net_profit: float
    payment_method: PaymentMethod
    payment_breakdown: PaymentBreakdown | None = None
    amount_tendered: float | None = None
    change_due: float | None = None
    loyalty_points_earned: int = 0
    timestamp: datetime
    # Ledger fields. Sales written before returns existed have no `type`, so it
    # defaults to SALE rather than being required.
    type: LedgerType = LedgerType.SALE
    original_sale_id: str | None = None
    original_receipt_number: str | None = None
    reason: str | None = None
    restocked: bool | None = None


class SalePage(BaseModel):
    items: list[SaleOut]
    total: int
    page: int
    page_size: int


class SalesStats(BaseModel):
    revenue: float
    refunds: float
    net_revenue: float
    profit: float
    transactions: int
    returns: int
    items_sold: int
    average_basket: float


# --------------------------------------------------------------------------- #
# Customers
# --------------------------------------------------------------------------- #
class CustomerCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=3, max_length=32)
    email: str | None = Field(default=None, max_length=160)
    credit_due: float = Field(default=0.0, ge=0)


class CustomerUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, min_length=3, max_length=32)
    email: str | None = Field(default=None, max_length=160)
    credit_due: float | None = Field(default=None, ge=0)


class CustomerOut(BaseModel):
    id: str
    name: str
    phone: str
    email: str | None = None
    total_visits: int
    total_spend: float
    credit_due: float
    loyalty_points: int
    last_visit: datetime | None = None


class CustomerPage(BaseModel):
    items: list[CustomerOut]
    total: int
    page: int
    page_size: int


# --------------------------------------------------------------------------- #
# Store settings
# --------------------------------------------------------------------------- #
class StoreOut(BaseModel):
    id: str
    name: str
    address: str = ""
    tax_id: str = ""
    currency: str = "LKR"
    tax_rate: float = 0.0
    default_discount: float = 0.0
    shelf_capacity_max: int
    warehouse_capacity_max: int
    loyalty_spend_per_point: float = 100.0


class StoreUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=300)
    tax_id: str | None = Field(default=None, max_length=64)
    currency: str | None = Field(default=None, min_length=1, max_length=8)
    tax_rate: float | None = Field(default=None, ge=0, le=100)
    default_discount: float | None = Field(default=None, ge=0, le=100)
    shelf_capacity_max: int | None = Field(default=None, gt=0)
    warehouse_capacity_max: int | None = Field(default=None, gt=0)
    loyalty_spend_per_point: float | None = Field(default=None, gt=0)


# --------------------------------------------------------------------------- #
# Dashboard & reports
# --------------------------------------------------------------------------- #
class CapacityGauge(BaseModel):
    used: int
    maximum: int
    percent: float


class CapacityOut(BaseModel):
    shelf: CapacityGauge
    warehouse: CapacityGauge


class DashboardMetrics(BaseModel):
    inventory_value_cost: float
    inventory_value_retail: float
    gross_revenue_today: float
    refunds_today: float
    net_revenue_today: float
    cogs_today: float
    net_profit_today: float
    profit_margin_today: float
    profit_change_percent: float
    transactions_today: int
    returns_today: int
    low_stock_count: int
    out_of_stock_count: int


class ForecastRow(BaseModel):
    product_id: str
    name: str
    category: str
    image_url: str | None = None
    current_stock: int
    daily_velocity: float
    projected_demand: float
    recommended_order: int
    days_of_cover: float | None = None


class ProfitPoint(BaseModel):
    label: str
    date: str
    revenue: float
    profit: float


class ReportSummary(BaseModel):
    gross_revenue: float
    refunds: float
    net_revenue: float
    cost_of_goods: float
    net_profit: float
    profit_margin: float
    transactions: int
    returns: int
    items_sold: int


class MonthlyPoint(BaseModel):
    month: str
    revenue: float
    profit: float


class CategorySlice(BaseModel):
    category: str
    revenue: float
    profit: float
    units: int


# --------------------------------------------------------------------------- #
# Items Prices in Future (IPF)
# --------------------------------------------------------------------------- #
class PriceRecommendation(str, Enum):
    PRICE_UP = "PRICE_UP"
    HOLD = "HOLD"
    LOSS_RISK = "LOSS_RISK"


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class IpfModelStatus(BaseModel):
    """What the trained model is, and how well it actually scored."""

    trained: bool
    trained_at: str | None = None
    horizon_days: int | None = None
    lookback_days: int | None = None
    n_samples: int | None = None
    n_train: int | None = None
    n_test: int | None = None
    mae: float | None = None
    baseline_mae: float | None = None
    improvement_percent: float | None = None
    r2: float | None = None
    beats_baseline: bool | None = None
    feature_count: int | None = None
    categories: list[str] | None = None
    algorithm: str | None = None


class IpfRow(BaseModel):
    product_id: str
    name: str
    brand: str | None = None
    category: str
    image_url: str | None = None
    current_price: float
    list_price: float
    buying_price: float
    market_price: float
    discount_percentage: float
    unit_profit: float
    margin_percent: float
    recent_units: float
    predicted_units: float
    demand_change_percent: float
    days_of_cover: float
    headroom_percent: float
    recommendation: PriceRecommendation
    suggested_price: float
    price_change_percent: float
    extra_profit_per_unit: float
    projected_profit_impact: float
    confidence: Confidence
    reason: str


class IpfForecast(BaseModel):
    horizon_days: int
    generated_rows: int
    opportunities: list[IpfRow]
    risks: list[IpfRow]
    steady: int
    projected_upside: float
    projected_exposure: float
    model: IpfModelStatus
