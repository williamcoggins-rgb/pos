"""
POS API endpoints
Handles sales, payments, refunds, voids, and the full Square-like sale lifecycle.
"""

from fastapi import APIRouter, HTTPException, Depends, Header, Query
from typing import Optional, List
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from square_like_pos import POSRuntime, PaymentMethod, HardwareMode
from event_store import Money
from api.models import (
    CreateSaleRequest,
    AddLineItemRequest,
    RemoveLineItemRequest,
    ApplyDiscountRequest,
    CalculateTaxRequest,
    AddTipRequest,
    ProcessPaymentRequest,
    CreateRefundRequest,
    VoidSaleRequest,
    CancelSaleRequest,
    SaleResponse,
    SalePaymentResponse,
    RefundResponse,
    PaymentResponse,
    LineItemResponse,
    MoneyModel,
    ErrorResponse,
)
from api.database import get_cloud_store, get_local_queue, get_eligibility_engine
from api.services.payment_service import PaymentService
from api.services.auth_service import AuthService

router = APIRouter(prefix="/api/pos", tags=["POS"])

# Services
payment_service = PaymentService()
auth_service = AuthService()


def get_current_barber(authorization: Optional[str] = Header(None)) -> str:
    """Extract barber_id from Authorization header"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")

    # Extract token from "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = parts[1]
    barber_id = auth_service.get_barber_id_from_token(token)

    if not barber_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    return barber_id


def get_pos_runtime(barber_id: str) -> POSRuntime:
    """Get POS runtime for barber with eligibility engine for auto-score"""
    return POSRuntime(
        barber_id=barber_id,
        cloud_store=get_cloud_store(),
        local_queue=get_local_queue(),
        hardware_mode=HardwareMode.SOFTWARE_ONLY,
        is_online=True,
        eligibility_engine=get_eligibility_engine(),
    )


def _money_model(m: Money) -> MoneyModel:
    """Convert Money to MoneyModel"""
    return MoneyModel(amount_minor=m.amount_minor, currency=m.currency)


def _sale_to_response(sale) -> SaleResponse:
    """Convert Sale aggregate to SaleResponse"""
    return SaleResponse(
        sale_id=sale.sale_id,
        barber_id=sale.barber_id,
        state=sale.state.value,
        version=sale.version,
        line_items=[
            LineItemResponse(
                item_id=item.item_id,
                name=item.name,
                quantity=item.quantity,
                unit_price=_money_model(item.unit_price),
                total=_money_model(item.total),
            )
            for item in sale.line_items
        ],
        subtotal=_money_model(sale.subtotal),
        tax=_money_model(sale.tax),
        tip=_money_model(sale.tip),
        discounts=_money_model(sale.discounts),
        total=_money_model(sale.total),
        payments=[
            SalePaymentResponse(
                payment_id=p["payment_id"],
                amount=MoneyModel(**p["amount"]),
                tip=MoneyModel(**p["tip"]) if p.get("tip") else None,
                captured_at=p.get("captured_at"),
                method=p.get("method"),
            )
            for p in sale.payments
        ],
        refunds=[
            RefundResponse(
                refund_id=r.refund_id,
                amount=_money_model(r.amount),
                reason=r.reason,
                created_at=r.created_at,
                payment_id=r.payment_id,
            )
            for r in sale.refunds
        ],
        refunded_amount=_money_model(sale.refunded_amount),
        created_at=sale.created_at,
        completed_at=sale.completed_at,
        canceled_at=sale.canceled_at,
        customer_id=sale.customer_id,
        metadata=sale.metadata,
    )


# ==========================================================================
# SALE LIFECYCLE
# ==========================================================================

@router.post("/sales", response_model=dict)
async def create_sale(
    request: CreateSaleRequest,
    barber_id: str = Depends(get_current_barber)
):
    """Create a new sale in DRAFT state"""
    try:
        pos = get_pos_runtime(barber_id)
        sale_id = pos.create_sale(
            metadata=request.metadata,
            customer_id=request.customer_id,
        )
        return {"sale_id": sale_id, "state": "DRAFT"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sales/{sale_id}/open", response_model=dict)
async def open_sale(
    sale_id: str,
    barber_id: str = Depends(get_current_barber)
):
    """Transition sale from DRAFT to OPEN (locks order for payment)"""
    try:
        pos = get_pos_runtime(barber_id)
        pos.open_sale(sale_id)
        return {"success": True, "state": "OPEN"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sales/{sale_id}/cancel", response_model=dict)
async def cancel_sale(
    sale_id: str,
    request: CancelSaleRequest,
    barber_id: str = Depends(get_current_barber)
):
    """Cancel a sale (must be DRAFT or OPEN, before payment)"""
    try:
        pos = get_pos_runtime(barber_id)
        pos.cancel_sale(sale_id, reason=request.reason)
        return {"success": True, "state": "CANCELED"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==========================================================================
# LINE ITEMS
# ==========================================================================

@router.post("/sales/{sale_id}/items", response_model=dict)
async def add_line_item(
    sale_id: str,
    request: AddLineItemRequest,
    barber_id: str = Depends(get_current_barber)
):
    """Add line item to sale (must be DRAFT)"""
    try:
        pos = get_pos_runtime(barber_id)
        item_id = pos.add_line_item(
            sale_id,
            name=request.name,
            quantity=request.quantity,
            unit_price=Money(amount_minor=request.unit_price_cents),
        )
        return {"item_id": item_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/sales/{sale_id}/items/{item_id}", response_model=dict)
async def remove_line_item(
    sale_id: str,
    item_id: str,
    barber_id: str = Depends(get_current_barber)
):
    """Remove line item from sale (must be DRAFT)"""
    try:
        pos = get_pos_runtime(barber_id)
        pos.remove_line_item(sale_id, item_id)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==========================================================================
# DISCOUNTS, TAX, TIPS
# ==========================================================================

@router.post("/sales/{sale_id}/discount", response_model=dict)
async def apply_discount(
    sale_id: str,
    request: ApplyDiscountRequest,
    barber_id: str = Depends(get_current_barber)
):
    """Apply discount to sale (must be DRAFT)"""
    try:
        pos = get_pos_runtime(barber_id)
        pos.apply_discount(
            sale_id,
            amount=Money(amount_minor=request.amount_cents),
            reason=request.reason,
        )
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sales/{sale_id}/tax", response_model=dict)
async def calculate_tax(
    sale_id: str,
    request: CalculateTaxRequest,
    barber_id: str = Depends(get_current_barber)
):
    """Calculate tax for sale (must be DRAFT)"""
    try:
        pos = get_pos_runtime(barber_id)
        pos.calculate_tax(sale_id, tax_rate=request.tax_rate)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sales/{sale_id}/tip", response_model=dict)
async def add_tip(
    sale_id: str,
    request: AddTipRequest,
    barber_id: str = Depends(get_current_barber)
):
    """Add tip to sale (DRAFT, OPEN, or COMPLETED for post-auth adjust)"""
    try:
        pos = get_pos_runtime(barber_id)
        pos.add_tip(sale_id, tip_amount=Money(amount_minor=request.amount_cents))
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==========================================================================
# PAYMENT
# ==========================================================================

@router.post("/sales/{sale_id}/payment", response_model=PaymentResponse)
async def process_payment(
    sale_id: str,
    request: ProcessPaymentRequest,
    barber_id: str = Depends(get_current_barber)
):
    """Process payment for sale (auto-opens DRAFT sales)"""
    try:
        pos = get_pos_runtime(barber_id)
        sale = pos.get_sale(sale_id)

        # Determine payment method
        payment_method = PaymentMethod(request.payment_method)

        # Process based on method
        if payment_method == PaymentMethod.CASH:
            payment_id, state = pos.take_payment(
                sale_id,
                amount=sale.total,
                method=payment_method,
            )

        elif payment_method == PaymentMethod.CARD_PRESENT and request.reader_id:
            # Card present with reader
            intent_id = payment_service.create_payment_intent(
                sale.total,
                description=f"Sale {sale_id}"
            )

            payment_service.process_payment_on_reader(
                request.reader_id,
                intent_id
            )

            success, card_last_four = payment_service.capture_payment(intent_id)
            if not success:
                raise Exception("Payment capture failed")

            payment_id, state = pos.take_payment(
                sale_id,
                amount=sale.total,
                method=payment_method,
                card_last_four=card_last_four,
            )

        else:
            # Simulated card payment (for testing without reader)
            intent_id, card_last_four = payment_service.simulate_card_present_payment(
                sale.total,
                description=f"Sale {sale_id}"
            )

            payment_id, state = pos.take_payment(
                sale_id,
                amount=sale.total,
                method=PaymentMethod.CARD_PRESENT,
                card_last_four=card_last_four,
            )

        # Get payment details
        payment = pos.get_payment(payment_id)

        return PaymentResponse(
            payment_id=payment.payment_id,
            sale_id=payment.sale_id,
            amount=_money_model(payment.amount),
            tip=_money_model(payment.tip),
            state=payment.state.value,
            method=payment.method.value,
            created_at=payment.created_at,
            captured_at=payment.captured_at,
            card_last_four=payment.card_last_four,
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==========================================================================
# REFUNDS & VOIDS
# ==========================================================================

@router.post("/sales/{sale_id}/refund", response_model=dict)
async def create_refund(
    sale_id: str,
    request: CreateRefundRequest,
    barber_id: str = Depends(get_current_barber)
):
    """Create refund for completed sale (supports partial refunds)"""
    try:
        pos = get_pos_runtime(barber_id)

        refund_id = pos.create_refund(
            sale_id,
            amount=Money(amount_minor=request.amount_cents),
            reason=request.reason,
        )

        # Process Stripe refund if payment_intent_id is provided
        stripe_refund_id = None
        if request.payment_intent_id:
            try:
                stripe_refund_id = payment_service.create_refund(
                    payment_intent_id=request.payment_intent_id,
                    amount=Money(amount_minor=request.amount_cents) if request.amount_cents else None
                )
            except Exception as stripe_error:
                print(f"Stripe refund failed: {stripe_error}")

        return {
            "refund_id": refund_id,
            "stripe_refund_id": stripe_refund_id
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sales/{sale_id}/void", response_model=dict)
async def void_sale(
    sale_id: str,
    request: VoidSaleRequest,
    barber_id: str = Depends(get_current_barber)
):
    """Void a sale (must be DRAFT or OPEN, before payment)"""
    try:
        pos = get_pos_runtime(barber_id)
        success = pos.void_sale(sale_id, reason=request.reason)
        return {"success": success, "state": "VOIDED"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==========================================================================
# QUERIES
# ==========================================================================

@router.get("/sales", response_model=List[SaleResponse])
async def list_sales(
    barber_id: str = Depends(get_current_barber),
    since: Optional[str] = Query(None, description="ISO 8601 date filter"),
    limit: Optional[int] = Query(50, description="Max results"),
):
    """List all sales for the current barber"""
    try:
        pos = get_pos_runtime(barber_id)
        sales = pos.list_barber_sales(since=since, limit=limit)
        return [_sale_to_response(sale) for sale in sales]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/analytics", response_model=dict)
async def get_analytics(
    barber_id: str = Depends(get_current_barber),
    since: Optional[str] = Query(None, description="ISO 8601 date filter"),
):
    """Get aggregated analytics for the current barber"""
    try:
        pos = get_pos_runtime(barber_id)
        sales = pos.list_barber_sales(since=since)

        completed_sales = [s for s in sales if s.state.value == "COMPLETED"]
        total_revenue = sum(s.total.amount_minor for s in completed_sales)
        total_tips = sum(s.tip.amount_minor for s in completed_sales)
        total_refunded = sum(s.refunded_amount.amount_minor for s in completed_sales)
        total_transactions = len(completed_sales)
        avg_transaction = total_revenue // total_transactions if total_transactions > 0 else 0

        recent = sorted(completed_sales, key=lambda s: s.completed_at or s.created_at or "", reverse=True)[:20]
        recent_list = []
        for s in recent:
            services = [item.name for item in s.line_items]
            recent_list.append({
                "sale_id": s.sale_id,
                "date": s.completed_at or s.created_at,
                "services": services,
                "total_cents": s.total.amount_minor,
                "tip_cents": s.tip.amount_minor,
                "metadata": s.metadata,
            })

        return {
            "total_revenue_cents": total_revenue,
            "total_tips_cents": total_tips,
            "total_refunded_cents": total_refunded,
            "net_revenue_cents": total_revenue - total_refunded,
            "total_transactions": total_transactions,
            "avg_transaction_cents": avg_transaction,
            "recent_transactions": recent_list,
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sales/{sale_id}", response_model=SaleResponse)
async def get_sale(
    sale_id: str,
    barber_id: str = Depends(get_current_barber)
):
    """Get sale details"""
    try:
        pos = get_pos_runtime(barber_id)
        sale = pos.get_sale(sale_id)
        return _sale_to_response(sale)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ==========================================================================
# HARDWARE
# ==========================================================================

@router.get("/readers", response_model=list)
async def list_readers(
    barber_id: str = Depends(get_current_barber)
):
    """List available card readers"""
    try:
        readers = payment_service.list_readers()
        return readers
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/readers/{reader_id}", response_model=dict)
async def get_reader_status(
    reader_id: str,
    barber_id: str = Depends(get_current_barber)
):
    """Get card reader status"""
    try:
        status = payment_service.get_reader_status(reader_id)
        return status
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
