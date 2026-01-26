"""
Square-Like POS System
Event-sourced point of sale with offline-first architecture and payment state machine.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any

from event_store import (
    Event,
    EventType,
    Money,
    CloudEventStore,
    LocalEventQueue,
    utc_now,
    generate_event_id,
)


class PaymentState(str, Enum):
    """Payment state machine"""
    INITIATED = "INITIATED"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    DECLINED = "DECLINED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    VOIDED = "VOIDED"


class PaymentMethod(str, Enum):
    """Payment method types"""
    CARD_PRESENT = "CARD_PRESENT"
    CARD_MANUAL = "CARD_MANUAL"
    CARD_ON_FILE = "CARD_ON_FILE"
    CASH = "CASH"
    CHECK = "CHECK"
    OTHER = "OTHER"


class SaleState(str, Enum):
    """Sale lifecycle states"""
    DRAFT = "DRAFT"
    COMPLETED = "COMPLETED"
    REFUNDED = "REFUNDED"
    VOIDED = "VOIDED"


class HardwareMode(str, Enum):
    """Hardware availability modes"""
    FULL = "FULL"  # All hardware available
    DEGRADED = "DEGRADED"  # Some hardware unavailable
    SOFTWARE_ONLY = "SOFTWARE_ONLY"  # No hardware


@dataclass
class LineItem:
    """Line item in a sale"""
    item_id: str
    name: str
    quantity: int
    unit_price: Money
    total: Money
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Sale:
    """
    Sale aggregate reconstructed from events.
    Represents a complete transaction.
    """
    sale_id: str
    barber_id: str
    state: SaleState
    line_items: List[LineItem] = field(default_factory=list)
    subtotal: Money = field(default_factory=lambda: Money(amount_minor=0))
    tax: Money = field(default_factory=lambda: Money(amount_minor=0))
    discounts: Money = field(default_factory=lambda: Money(amount_minor=0))
    total: Money = field(default_factory=lambda: Money(amount_minor=0))
    payments: List[Dict[str, Any]] = field(default_factory=list)
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Payment:
    """Payment aggregate reconstructed from events"""
    payment_id: str
    sale_id: str
    barber_id: str
    amount: Money
    state: PaymentState
    method: PaymentMethod
    created_at: str
    authorized_at: Optional[str] = None
    captured_at: Optional[str] = None
    card_last_four: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class POSRuntime:
    """
    Point of Sale Runtime
    Event-sourced system with offline-first support and payment state machine.
    """

    def __init__(
        self,
        barber_id: str,
        cloud_store: CloudEventStore,
        local_queue: LocalEventQueue,
        hardware_mode: HardwareMode = HardwareMode.FULL,
        is_online: bool = True,
    ):
        self.barber_id = barber_id
        self.cloud_store = cloud_store
        self.local_queue = local_queue
        self.hardware_mode = hardware_mode
        self.is_online = is_online

    def create_sale(self, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Create a new sale (draft state).
        Returns sale_id.
        """
        sale_id = str(uuid.uuid4())
        idempotency_key = f"sale_created_{sale_id}"

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.SALE_CREATED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "sale_id": sale_id,
                "barber_id": self.barber_id,
                "metadata": metadata or {},
            },
            created_at=utc_now(),
            idempotency_key=idempotency_key,
        )

        self._emit_event(event)
        return sale_id

    def add_line_item(
        self,
        sale_id: str,
        name: str,
        quantity: int,
        unit_price: Money,
    ) -> str:
        """
        Add line item to sale.
        Sale must be in DRAFT state.
        Returns item_id.
        """
        # Verify sale is still draft
        sale = self.get_sale(sale_id)
        if sale.state != SaleState.DRAFT:
            raise ValueError(f"Cannot modify sale in state {sale.state}")

        item_id = str(uuid.uuid4())
        total = Money(amount_minor=unit_price.amount_minor * quantity)

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.LINE_ITEM_ADDED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "sale_id": sale_id,
                "item_id": item_id,
                "name": name,
                "quantity": quantity,
                "unit_price": unit_price.to_dict(),
                "total": total.to_dict(),
            },
            created_at=utc_now(),
        )

        self._emit_event(event)
        return item_id

    def apply_discount(
        self,
        sale_id: str,
        amount: Money,
        reason: str = "",
    ):
        """Apply discount to sale"""
        sale = self.get_sale(sale_id)
        if sale.state != SaleState.DRAFT:
            raise ValueError(f"Cannot modify sale in state {sale.state}")

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.DISCOUNT_APPLIED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "sale_id": sale_id,
                "amount": amount.to_dict(),
                "reason": reason,
            },
            created_at=utc_now(),
        )

        self._emit_event(event)

    def calculate_tax(self, sale_id: str, tax_rate: float = 0.08):
        """Calculate and apply tax to sale"""
        sale = self.get_sale(sale_id)
        if sale.state != SaleState.DRAFT:
            raise ValueError(f"Cannot modify sale in state {sale.state}")

        # Calculate tax on subtotal minus discounts
        taxable_amount = sale.subtotal.amount_minor - sale.discounts.amount_minor
        tax_amount = int(taxable_amount * tax_rate)
        tax = Money(amount_minor=tax_amount)

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.TAX_CALCULATED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "sale_id": sale_id,
                "tax": tax.to_dict(),
                "tax_rate": tax_rate,
            },
            created_at=utc_now(),
        )

        self._emit_event(event)

    def take_payment(
        self,
        sale_id: str,
        amount: Money,
        method: PaymentMethod,
        card_last_four: Optional[str] = None,
    ) -> Tuple[str, PaymentState]:
        """
        Take payment for a sale.
        Returns (payment_id, final_state).

        For CARD_PRESENT with hardware: INITIATED → AUTHORIZED → CAPTURED
        For CASH or SOFTWARE_ONLY: direct to CAPTURED
        """
        sale = self.get_sale(sale_id)
        if sale.state != SaleState.DRAFT:
            raise ValueError(f"Cannot take payment on sale in state {sale.state}")

        payment_id = str(uuid.uuid4())
        idempotency_key = f"payment_{payment_id}"

        # Emit PAYMENT_INITIATED
        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.PAYMENT_INITIATED,
            aggregate_id=payment_id,
            aggregate_type="payment",
            payload={
                "payment_id": payment_id,
                "sale_id": sale_id,
                "barber_id": self.barber_id,
                "amount": amount.to_dict(),
                "method": method.value,
                "card_last_four": card_last_four,
            },
            created_at=utc_now(),
            idempotency_key=idempotency_key,
        )
        self._emit_event(event)

        # State machine progression
        if method == PaymentMethod.CASH or self.hardware_mode == HardwareMode.SOFTWARE_ONLY:
            # Direct capture for cash or software-only mode
            return self._capture_payment(payment_id, sale_id)
        else:
            # Card payment: authorize then capture
            return self._authorize_and_capture_payment(payment_id, sale_id)

    def _authorize_and_capture_payment(
        self, payment_id: str, sale_id: str
    ) -> Tuple[str, PaymentState]:
        """
        Hardware-based authorization and capture.
        In real system, this would interact with payment terminal.
        """
        # AUTHORIZED event
        auth_event = Event(
            event_id=generate_event_id(),
            event_type=EventType.PAYMENT_AUTHORIZED,
            aggregate_id=payment_id,
            aggregate_type="payment",
            payload={
                "payment_id": payment_id,
                "sale_id": sale_id,
                "authorized_at": utc_now(),
            },
            created_at=utc_now(),
        )
        self._emit_event(auth_event)

        # CAPTURED event
        return self._capture_payment(payment_id, sale_id)

    def _capture_payment(self, payment_id: str, sale_id: str) -> Tuple[str, PaymentState]:
        """Capture (settle) payment"""
        captured_event = Event(
            event_id=generate_event_id(),
            event_type=EventType.PAYMENT_CAPTURED,
            aggregate_id=payment_id,
            aggregate_type="payment",
            payload={
                "payment_id": payment_id,
                "sale_id": sale_id,
                "captured_at": utc_now(),
            },
            created_at=utc_now(),
        )
        self._emit_event(captured_event)

        return (payment_id, PaymentState.CAPTURED)

    def create_refund(
        self,
        sale_id: str,
        amount: Money,
        reason: str = "",
    ) -> str:
        """
        Create refund for a sale.
        Sale must be COMPLETED.
        """
        sale = self.get_sale(sale_id)
        if sale.state != SaleState.COMPLETED:
            raise ValueError(f"Cannot refund sale in state {sale.state}")

        refund_id = str(uuid.uuid4())
        idempotency_key = f"refund_{refund_id}"

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.REFUND_CREATED,
            aggregate_id=refund_id,
            aggregate_type="refund",
            payload={
                "refund_id": refund_id,
                "sale_id": sale_id,
                "amount": amount.to_dict(),
                "reason": reason,
            },
            created_at=utc_now(),
            idempotency_key=idempotency_key,
        )

        self._emit_event(event)
        return refund_id

    def void_sale(self, sale_id: str, reason: str = "") -> bool:
        """
        Void a sale (before completion).
        Sale must be in DRAFT state.
        """
        sale = self.get_sale(sale_id)
        if sale.state != SaleState.DRAFT:
            raise ValueError(f"Cannot void sale in state {sale.state}. Use refund for completed sales.")

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.VOID_APPLIED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "sale_id": sale_id,
                "reason": reason,
            },
            created_at=utc_now(),
        )

        self._emit_event(event)
        return True

    def open_shift(self, starting_cash: Money) -> str:
        """Open a shift"""
        shift_id = str(uuid.uuid4())
        idempotency_key = f"shift_open_{self.barber_id}_{utc_now()[:10]}"

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.SHIFT_OPENED,
            aggregate_id=shift_id,
            aggregate_type="shift",
            payload={
                "shift_id": shift_id,
                "barber_id": self.barber_id,
                "starting_cash": starting_cash.to_dict(),
            },
            created_at=utc_now(),
            idempotency_key=idempotency_key,
        )

        self._emit_event(event)
        return shift_id

    def close_shift(
        self,
        shift_id: str,
        ending_cash: Money,
        total_sales: Money,
    ) -> str:
        """Close a shift"""
        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.SHIFT_CLOSED,
            aggregate_id=shift_id,
            aggregate_type="shift",
            payload={
                "shift_id": shift_id,
                "barber_id": self.barber_id,
                "ending_cash": ending_cash.to_dict(),
                "total_sales": total_sales.to_dict(),
                "closed_at": utc_now(),
            },
            created_at=utc_now(),
        )

        self._emit_event(event)
        return shift_id

    def sync_offline_events(self) -> int:
        """
        Sync local queue to cloud when coming back online.
        Returns number of events synced.
        """
        if not self.is_online:
            raise RuntimeError("Cannot sync while offline")

        return self.local_queue.sync_to_cloud(self.cloud_store)

    def get_sale(self, sale_id: str) -> Sale:
        """Reconstruct sale from events"""
        events = self.cloud_store.get_events(aggregate_type="sale", aggregate_id=sale_id)

        if not events:
            # Check local queue if offline
            raise ValueError(f"Sale {sale_id} not found")

        sale = Sale(
            sale_id=sale_id,
            barber_id=self.barber_id,
            state=SaleState.DRAFT,
        )

        for event in events:
            self._apply_event_to_sale(sale, event)

        return sale

    def _apply_event_to_sale(self, sale: Sale, event: Event):
        """Apply event to sale aggregate"""
        if event.event_type == EventType.SALE_CREATED:
            sale.created_at = event.created_at
            sale.metadata = event.payload.get("metadata", {})

        elif event.event_type == EventType.LINE_ITEM_ADDED:
            item = LineItem(
                item_id=event.payload["item_id"],
                name=event.payload["name"],
                quantity=event.payload["quantity"],
                unit_price=Money(**event.payload["unit_price"]),
                total=Money(**event.payload["total"]),
            )
            sale.line_items.append(item)
            sale.subtotal = Money(
                amount_minor=sale.subtotal.amount_minor + item.total.amount_minor
            )

        elif event.event_type == EventType.DISCOUNT_APPLIED:
            discount_amount = Money(**event.payload["amount"])
            sale.discounts = Money(
                amount_minor=sale.discounts.amount_minor + discount_amount.amount_minor
            )

        elif event.event_type == EventType.TAX_CALCULATED:
            sale.tax = Money(**event.payload["tax"])

        elif event.event_type == EventType.PAYMENT_CAPTURED:
            sale.state = SaleState.COMPLETED
            sale.completed_at = event.created_at
            # Recalculate total
            sale.total = Money(
                amount_minor=(
                    sale.subtotal.amount_minor
                    - sale.discounts.amount_minor
                    + sale.tax.amount_minor
                )
            )

        elif event.event_type == EventType.REFUND_CREATED:
            sale.state = SaleState.REFUNDED

        elif event.event_type == EventType.VOID_APPLIED:
            sale.state = SaleState.VOIDED

    def get_payment(self, payment_id: str) -> Payment:
        """Reconstruct payment from events"""
        events = self.cloud_store.get_events(aggregate_type="payment", aggregate_id=payment_id)

        if not events:
            raise ValueError(f"Payment {payment_id} not found")

        payment_data = None
        state = PaymentState.INITIATED
        authorized_at = None
        captured_at = None

        for event in events:
            if event.event_type == EventType.PAYMENT_INITIATED:
                payment_data = event.payload
                state = PaymentState.INITIATED

            elif event.event_type == EventType.PAYMENT_AUTHORIZED:
                state = PaymentState.AUTHORIZED
                authorized_at = event.payload.get("authorized_at")

            elif event.event_type == EventType.PAYMENT_CAPTURED:
                state = PaymentState.CAPTURED
                captured_at = event.payload.get("captured_at")

            elif event.event_type == EventType.PAYMENT_DECLINED:
                state = PaymentState.DECLINED

            elif event.event_type == EventType.PAYMENT_FAILED:
                state = PaymentState.FAILED

        if not payment_data:
            raise ValueError(f"Payment {payment_id} has no PAYMENT_INITIATED event")

        return Payment(
            payment_id=payment_data["payment_id"],
            sale_id=payment_data["sale_id"],
            barber_id=payment_data["barber_id"],
            amount=Money(**payment_data["amount"]),
            state=state,
            method=PaymentMethod(payment_data["method"]),
            created_at=events[0].created_at,
            authorized_at=authorized_at,
            captured_at=captured_at,
            card_last_four=payment_data.get("card_last_four"),
        )

    def _emit_event(self, event: Event):
        """
        Emit event to appropriate store based on online/offline state.
        Always try cloud first, fallback to local queue if offline.
        """
        if self.is_online:
            try:
                self.cloud_store.append(event)
            except Exception as e:
                print(f"Cloud store failed, using local queue: {e}")
                self.local_queue.enqueue(event)
        else:
            self.local_queue.enqueue(event)

    def get_barber_revenue_today(self) -> Money:
        """Get total revenue for barber today"""
        today = datetime.now(timezone.utc).date().isoformat()
        events = self.cloud_store.get_events(
            aggregate_type="payment",
            event_type=EventType.PAYMENT_CAPTURED,
            since=f"{today}T00:00:00Z",
        )

        total = 0
        for event in events:
            if event.payload["barber_id"] == self.barber_id:
                total += event.payload["amount"]["amount_minor"]

        return Money(amount_minor=total)
