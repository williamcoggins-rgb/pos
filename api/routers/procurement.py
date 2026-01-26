"""
Procurement API endpoints
Handles warehouse orders with entitlement enforcement
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional, List
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.models import (
    CreateOrderRequest,
    ProcurementLineItemRequest,
    OrderResponse,
    OrderLineItemResponse,
    MoneyModel,
    ErrorResponse,
)
from api.database import (
    get_cloud_store,
    get_entitlement_ledger,
    get_procurement_service
)
from enforcement_middleware import EnforcementMiddleware
from event_store import Money
from procurement_service import FulfillmentSLA
from api.services.auth_service import AuthService

router = APIRouter(prefix="/api/procurement", tags=["Procurement"])

auth_service = AuthService()


def get_current_barber(authorization: Optional[str] = Header(None)) -> str:
    """Extract barber_id from Authorization header"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = parts[1]
    barber_id = auth_service.get_barber_id_from_token(token)

    if not barber_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    return barber_id


@router.post("/orders", response_model=OrderResponse)
async def create_order(
    request: CreateOrderRequest,
    current_user: str = Depends(get_current_barber)
):
    """Create a procurement order (with entitlement enforcement)"""

    # Ensure user can only order for themselves
    if request.barber_id != current_user:
        raise HTTPException(status_code=403, detail="Cannot create orders for other barbers")

    try:
        # Check entitlements
        ledger = get_entitlement_ledger()
        procurement = get_procurement_service()
        enforcement = EnforcementMiddleware(ledger, procurement)

        # Validate order before creation
        line_items_dict = [
            {
                "sku": item.sku,
                "name": item.name,
                "quantity": item.quantity,
                "unit_price": {"amount_minor": item.unit_price_cents, "currency": "USD"}
            }
            for item in request.line_items
        ]

        validation = enforcement.validate_order_creation(
            request.barber_id,
            line_items_dict
        )

        if not validation.allowed:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Order blocked",
                    "reason": validation.reason,
                    "blocked_by": validation.blocked_by,
                }
            )

        # Create order
        sla = FulfillmentSLA(request.sla)
        order_id = procurement.create_order(
            request.barber_id,
            line_items_dict,
            sla=sla
        )

        # Get order details
        order = procurement.get_order(order_id)

        return OrderResponse(
            order_id=order.order_id,
            barber_id=order.barber_id,
            state=order.state.value,
            line_items=[
                OrderLineItemResponse(
                    sku=item.sku,
                    name=item.name,
                    quantity=item.quantity,
                    unit_price=MoneyModel(
                        amount_minor=item.unit_price.amount_minor,
                        currency=item.unit_price.currency
                    ),
                    total=MoneyModel(
                        amount_minor=item.total.amount_minor,
                        currency=item.total.currency
                    )
                )
                for item in order.line_items
            ],
            subtotal=MoneyModel(
                amount_minor=order.subtotal.amount_minor,
                currency=order.subtotal.currency
            ),
            tax=MoneyModel(
                amount_minor=order.tax.amount_minor,
                currency=order.tax.currency
            ),
            shipping=MoneyModel(
                amount_minor=order.shipping.amount_minor,
                currency=order.shipping.currency
            ),
            total=MoneyModel(
                amount_minor=order.total.amount_minor,
                currency=order.total.currency
            ),
            sla=order.sla.value,
            created_at=order.created_at,
            shipped_at=order.shipped_at,
            delivered_at=order.delivered_at,
            tracking_number=order.tracking_number,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/orders", response_model=List[OrderResponse])
async def list_orders(
    current_user: str = Depends(get_current_barber)
):
    """List all orders for current barber"""
    try:
        procurement = get_procurement_service()
        orders = procurement.get_barber_orders(current_user)

        return [
            OrderResponse(
                order_id=order.order_id,
                barber_id=order.barber_id,
                state=order.state.value,
                line_items=[
                    OrderLineItemResponse(
                        sku=item.sku,
                        name=item.name,
                        quantity=item.quantity,
                        unit_price=MoneyModel(
                            amount_minor=item.unit_price.amount_minor,
                            currency=item.unit_price.currency
                        ),
                        total=MoneyModel(
                            amount_minor=item.total.amount_minor,
                            currency=item.total.currency
                        )
                    )
                    for item in order.line_items
                ],
                subtotal=MoneyModel(
                    amount_minor=order.subtotal.amount_minor,
                    currency=order.subtotal.currency
                ),
                tax=MoneyModel(
                    amount_minor=order.tax.amount_minor,
                    currency=order.tax.currency
                ),
                shipping=MoneyModel(
                    amount_minor=order.shipping.amount_minor,
                    currency=order.shipping.currency
                ),
                total=MoneyModel(
                    amount_minor=order.total.amount_minor,
                    currency=order.total.currency
                ),
                sla=order.sla.value,
                created_at=order.created_at,
                shipped_at=order.shipped_at,
                delivered_at=order.delivered_at,
                tracking_number=order.tracking_number,
            )
            for order in orders
        ]

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    current_user: str = Depends(get_current_barber)
):
    """Get order details"""
    try:
        procurement = get_procurement_service()
        order = procurement.get_order(order_id)

        # Ensure user can only view their own orders
        if order.barber_id != current_user:
            raise HTTPException(status_code=403, detail="Cannot view other barbers' orders")

        return OrderResponse(
            order_id=order.order_id,
            barber_id=order.barber_id,
            state=order.state.value,
            line_items=[
                OrderLineItemResponse(
                    sku=item.sku,
                    name=item.name,
                    quantity=item.quantity,
                    unit_price=MoneyModel(
                        amount_minor=item.unit_price.amount_minor,
                        currency=item.unit_price.currency
                    ),
                    total=MoneyModel(
                        amount_minor=item.total.amount_minor,
                        currency=item.total.currency
                    )
                )
                for item in order.line_items
            ],
            subtotal=MoneyModel(
                amount_minor=order.subtotal.amount_minor,
                currency=order.subtotal.currency
            ),
            tax=MoneyModel(
                amount_minor=order.tax.amount_minor,
                currency=order.tax.currency
            ),
            shipping=MoneyModel(
                amount_minor=order.shipping.amount_minor,
                currency=order.shipping.currency
            ),
            total=MoneyModel(
                amount_minor=order.total.amount_minor,
                currency=order.total.currency
            ),
            sla=order.sla.value,
            created_at=order.created_at,
            shipped_at=order.shipped_at,
            delivered_at=order.delivered_at,
            tracking_number=order.tracking_number,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/orders/{order_id}/cancel", response_model=dict)
async def cancel_order(
    order_id: str,
    current_user: str = Depends(get_current_barber)
):
    """Cancel an order"""
    try:
        procurement = get_procurement_service()
        order = procurement.get_order(order_id)

        # Ensure user can only cancel their own orders
        if order.barber_id != current_user:
            raise HTTPException(status_code=403, detail="Cannot cancel other barbers' orders")

        procurement.cancel_order(order_id, reason="Customer requested")
        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
