"""
POS API endpoints
Handles sales, payments, refunds, and voids
"""

from fastapi import APIRouter, HTTPException, Depends

from square_like_pos import POSRuntime, PaymentMethod, HardwareMode
from event_store import Money
from api.models import (
    CreateSaleRequest,
    AddLineItemRequest,
    ApplyDiscountRequest,
    CalculateTaxRequest,
    ProcessPaymentRequest,
    CreateRefundRequest,
    VoidSaleRequest,
    SaleResponse,
    PaymentResponse,
    LineItemResponse,
    MoneyModel,
)
from api.database import get_cloud_store, get_local_queue
from api.services.payment_service import PaymentService
from api.dependencies import get_current_barber

router = APIRouter(prefix="/api/pos", tags=["POS"])

payment_service = PaymentService()


def get_pos_runtime(barber_id: str) -> POSRuntime:
    """Get POS runtime for barber"""
    return POSRuntime(
        barber_id=barber_id,
        cloud_store=get_cloud_store(),
        local_queue=get_local_queue(),
        hardware_mode=HardwareMode.SOFTWARE_ONLY,  # Will upgrade when reader connected
        is_online=True,
    )


@router.post("/sales", response_model=dict)
async def create_sale(
    request: CreateSaleRequest,
    barber_id: str = Depends(get_current_barber)
):
    """Create a new sale"""
    try:
        pos = get_pos_runtime(barber_id)
        sale_id = pos.create_sale(metadata=request.metadata)
        return {"sale_id": sale_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sales/{sale_id}/items", response_model=dict)
async def add_line_item(
    sale_id: str,
    request: AddLineItemRequest,
    barber_id: str = Depends(get_current_barber)
):
    """Add line item to sale"""
    try:
        pos = get_pos_runtime(barber_id)
        item_id = pos.add_line_item(
            sale_id,
            name=request.name,
            quantity=request.quantity,
            unit_price=Money(amount_minor=request.unit_price_cents),
        )
        return {"item_id": item_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sales/{sale_id}/discount", response_model=dict)
async def apply_discount(
    sale_id: str,
    request: ApplyDiscountRequest,
    barber_id: str = Depends(get_current_barber)
):
    """Apply discount to sale"""
    try:
        pos = get_pos_runtime(barber_id)
        pos.apply_discount(
            sale_id,
            amount=Money(amount_minor=request.amount_cents),
            reason=request.reason,
        )
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sales/{sale_id}/tax", response_model=dict)
async def calculate_tax(
    sale_id: str,
    request: CalculateTaxRequest,
    barber_id: str = Depends(get_current_barber)
):
    """Calculate tax for sale"""
    try:
        pos = get_pos_runtime(barber_id)
        pos.calculate_tax(sale_id, tax_rate=request.tax_rate)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sales/{sale_id}/payment", response_model=PaymentResponse)
async def process_payment(
    sale_id: str,
    request: ProcessPaymentRequest,
    barber_id: str = Depends(get_current_barber)
):
    """Process payment for sale"""
    try:
        pos = get_pos_runtime(barber_id)
        sale = pos.get_sale(sale_id)

        # Determine payment method
        payment_method = PaymentMethod(request.payment_method)

        # Process based on method
        if payment_method == PaymentMethod.CASH:
            # Cash payment - no Stripe processing
            payment_id, state = pos.take_payment(
                sale_id,
                amount=sale.total,
                method=payment_method,
            )

        elif payment_method == PaymentMethod.CARD_PRESENT and request.reader_id:
            # Card present with reader
            # 1. Create Stripe payment intent
            intent_id = payment_service.create_payment_intent(
                sale.total,
                description=f"Sale {sale_id}"
            )

            # 2. Process on reader
            payment_service.process_payment_on_reader(
                request.reader_id,
                intent_id
            )

            # 3. Capture payment
            success, card_last_four = payment_service.capture_payment(intent_id)

            if not success:
                raise Exception("Payment capture failed")

            # 4. Record in POS
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
            amount=MoneyModel(
                amount_minor=payment.amount.amount_minor,
                currency=payment.amount.currency
            ),
            state=payment.state.value,
            method=payment.method.value,
            created_at=payment.created_at,
            captured_at=payment.captured_at,
            card_last_four=payment.card_last_four,
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sales/{sale_id}/refund", response_model=dict)
async def create_refund(
    sale_id: str,
    request: CreateRefundRequest,
    barber_id: str = Depends(get_current_barber)
):
    """Create refund for sale"""
    try:
        pos = get_pos_runtime(barber_id)
        sale = pos.get_sale(sale_id)

        # Create refund in POS system
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
                # Log error but don't fail the refund record
                print(f"Stripe refund failed: {stripe_error}")

        return {
            "refund_id": refund_id,
            "stripe_refund_id": stripe_refund_id
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sales/{sale_id}/void", response_model=dict)
async def void_sale(
    sale_id: str,
    request: VoidSaleRequest,
    barber_id: str = Depends(get_current_barber)
):
    """Void a sale"""
    try:
        pos = get_pos_runtime(barber_id)
        success = pos.void_sale(sale_id, reason=request.reason)
        return {"success": success}
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

        return SaleResponse(
            sale_id=sale.sale_id,
            barber_id=sale.barber_id,
            state=sale.state.value,
            line_items=[
                LineItemResponse(
                    item_id=item.item_id,
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
                for item in sale.line_items
            ],
            subtotal=MoneyModel(
                amount_minor=sale.subtotal.amount_minor,
                currency=sale.subtotal.currency
            ),
            tax=MoneyModel(
                amount_minor=sale.tax.amount_minor,
                currency=sale.tax.currency
            ),
            discounts=MoneyModel(
                amount_minor=sale.discounts.amount_minor,
                currency=sale.discounts.currency
            ),
            total=MoneyModel(
                amount_minor=sale.total.amount_minor,
                currency=sale.total.currency
            ),
            created_at=sale.created_at,
            completed_at=sale.completed_at,
            metadata=sale.metadata,
        )

    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


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
