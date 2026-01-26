"""
Pydantic models for API requests and responses
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ============================================================================
# Money Model
# ============================================================================

class MoneyModel(BaseModel):
    """Money representation"""
    amount_minor: int = Field(..., description="Amount in cents")
    currency: str = Field(default="USD", description="Currency code")

    @property
    def amount_dollars(self) -> float:
        return self.amount_minor / 100.0


# ============================================================================
# POS Request Models
# ============================================================================

class CreateSaleRequest(BaseModel):
    """Request to create a new sale"""
    barber_id: str = Field(..., description="Barber's unique ID")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class AddLineItemRequest(BaseModel):
    """Request to add item to sale"""
    name: str = Field(..., description="Item name", min_length=1)
    quantity: int = Field(..., description="Quantity", ge=1)
    unit_price_cents: int = Field(..., description="Price per unit in cents", ge=0)


class ApplyDiscountRequest(BaseModel):
    """Request to apply discount"""
    amount_cents: int = Field(..., description="Discount amount in cents", ge=0)
    reason: str = Field(default="", description="Reason for discount")


class CalculateTaxRequest(BaseModel):
    """Request to calculate tax"""
    tax_rate: float = Field(default=0.08, description="Tax rate", ge=0, le=1)


class ProcessPaymentRequest(BaseModel):
    """Request to process payment"""
    payment_method: str = Field(..., description="Payment method: CARD_PRESENT, CASH, etc")
    reader_id: Optional[str] = Field(None, description="Stripe Terminal reader ID")
    card_last_four: Optional[str] = Field(None, description="Last 4 digits of card")


class CreateRefundRequest(BaseModel):
    """Request to create refund"""
    amount_cents: int = Field(..., description="Refund amount in cents", ge=0)
    reason: str = Field(default="", description="Reason for refund")


class VoidSaleRequest(BaseModel):
    """Request to void sale"""
    reason: str = Field(default="", description="Reason for void")


# ============================================================================
# POS Response Models
# ============================================================================

class LineItemResponse(BaseModel):
    """Line item in response"""
    item_id: str
    name: str
    quantity: int
    unit_price: MoneyModel
    total: MoneyModel


class SaleResponse(BaseModel):
    """Sale details response"""
    sale_id: str
    barber_id: str
    state: str
    line_items: List[LineItemResponse]
    subtotal: MoneyModel
    tax: MoneyModel
    discounts: MoneyModel
    total: MoneyModel
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PaymentResponse(BaseModel):
    """Payment result response"""
    payment_id: str
    sale_id: str
    amount: MoneyModel
    state: str
    method: str
    created_at: str
    captured_at: Optional[str] = None
    card_last_four: Optional[str] = None


# ============================================================================
# Eligibility Request/Response Models
# ============================================================================

class BarberMetricsResponse(BaseModel):
    """Barber metrics response"""
    qualified_transactions: int
    total_revenue_cents: int
    refund_count: int
    void_count: int
    chargeback_count: int
    active_days: int
    avg_ticket_cents: float
    refund_rate: float
    void_rate: float
    chargeback_rate: float


class BarberScoreResponse(BaseModel):
    """BarberScore response"""
    barber_id: str
    score: int
    tier: str
    metrics: BarberMetricsResponse
    flags: List[str]
    hard_gate_blocks: List[str]
    calculated_at: str


class EntitlementResponse(BaseModel):
    """Entitlement summary response"""
    barber_id: str
    tier: str
    score: int
    is_active: bool
    access: List[str]
    caps: Dict[str, int]
    store_access: bool
    terms_access: bool
    pricing_tier: str
    fulfillment_sla: str
    next_tier: str
    points_to_next: int
    blocked_reasons: List[str]
    granted_at: Optional[str] = None
    last_updated: Optional[str] = None


# ============================================================================
# Procurement Request/Response Models
# ============================================================================

class ProcurementLineItemRequest(BaseModel):
    """Line item for procurement order"""
    sku: str
    name: str
    quantity: int = Field(..., ge=1)
    unit_price_cents: int = Field(..., ge=0)


class CreateOrderRequest(BaseModel):
    """Request to create procurement order"""
    barber_id: str
    line_items: List[ProcurementLineItemRequest]
    sla: str = Field(default="STANDARD", description="STANDARD or PRIORITY")


class OrderLineItemResponse(BaseModel):
    """Order line item response"""
    sku: str
    name: str
    quantity: int
    unit_price: MoneyModel
    total: MoneyModel


class OrderResponse(BaseModel):
    """Procurement order response"""
    order_id: str
    barber_id: str
    state: str
    line_items: List[OrderLineItemResponse]
    subtotal: MoneyModel
    tax: MoneyModel
    shipping: MoneyModel
    total: MoneyModel
    sla: str
    created_at: Optional[str] = None
    shipped_at: Optional[str] = None
    delivered_at: Optional[str] = None
    tracking_number: Optional[str] = None


# ============================================================================
# Auth Models
# ============================================================================

class RegisterRequest(BaseModel):
    """Registration request"""
    email: str = Field(..., description="Email address")
    password: str = Field(..., min_length=8, description="Password (min 8 chars)")
    shop_name: str = Field(..., min_length=1, description="Shop name")


class LoginRequest(BaseModel):
    """Login request"""
    email: str
    password: str


class TokenResponse(BaseModel):
    """Auth token response"""
    access_token: str
    token_type: str = "bearer"
    barber_id: str
    shop_name: str


# ============================================================================
# Error Response
# ============================================================================

class ErrorResponse(BaseModel):
    """Error response"""
    error: str
    detail: Optional[str] = None
    blocked_by: Optional[str] = None
