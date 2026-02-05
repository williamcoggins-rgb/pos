"""
Square-Like POS System
Event-sourced point of sale with offline-first architecture and payment state machine.
Follows Square Orders API lifecycle: DRAFT → OPEN → COMPLETED / CANCELED
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
    """
    Sale lifecycle states (Square-aligned)
    DRAFT: Building the order, can add/remove items
    OPEN: Finalized, ready for payment. No more item changes.
    COMPLETED: Fully paid. Terminal state.
    CANCELED: Canceled before payment. Terminal state.
    VOIDED: Voided after payment but before settlement. Terminal state.
    """
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"
    VOIDED = "VOIDED"


class HardwareMode(str, Enum):
    """Hardware availability modes"""
    FULL = "FULL"          # All hardware available
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
    catalog_item_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Refund:
    """Refund record linked to a sale"""
    refund_id: str
    amount: Money
    reason: str
    created_at: str
    payment_id: Optional[str] = None


@dataclass
class Sale:
    """
    Sale aggregate reconstructed from events.
    Represents a complete transaction.
    """
    sale_id: str
    barber_id: str
    state: SaleState
    version: int = 0
    line_items: List[LineItem] = field(default_factory=list)
    subtotal: Money = field(default_factory=lambda: Money(amount_minor=0))
    tax: Money = field(default_factory=lambda: Money(amount_minor=0))
    tip: Money = field(default_factory=lambda: Money(amount_minor=0))
    discounts: Money = field(default_factory=lambda: Money(amount_minor=0))
    total: Money = field(default_factory=lambda: Money(amount_minor=0))
    payments: List[Dict[str, Any]] = field(default_factory=list)
    refunds: List[Refund] = field(default_factory=list)
    refunded_amount: Money = field(default_factory=lambda: Money(amount_minor=0))
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    canceled_at: Optional[str] = None
    customer_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def _recalculate_total(self):
        """Recalculate total from components"""
        self.total = Money(
            amount_minor=max(0,
                self.subtotal.amount_minor
                - self.discounts.amount_minor
                + self.tax.amount_minor
                + self.tip.amount_minor
            )
        )


@dataclass
class Payment:
    """Payment aggregate reconstructed from events"""
    payment_id: str
    sale_id: str
    barber_id: str
    amount: Money
    tip: Money
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
    Follows Square Orders API lifecycle: DRAFT → OPEN → COMPLETED / CANCELED
    """

    def __init__(
        self,
        barber_id: str,
        cloud_store: CloudEventStore,
        local_queue: LocalEventQueue,
        hardware_mode: HardwareMode = HardwareMode.FULL,
        is_online: bool = True,
        eligibility_engine=None,
    ):
        self.barber_id = barber_id
        self.cloud_store = cloud_store
        self.local_queue = local_queue
        self.hardware_mode = hardware_mode
        self.is_online = is_online
        self.eligibility_engine = eligibility_engine

    # =========================================================================
    # SALE LIFECYCLE
    # =========================================================================

    def create_sale(self, metadata: Optional[Dict[str, Any]] = None, customer_id: Optional[str] = None) -> str:
        """
        Create a new sale in DRAFT state.
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
                "customer_id": customer_id,
                "metadata": metadata or {},
            },
            created_at=utc_now(),
            idempotency_key=idempotency_key,
        )

        self._emit_event(event)
        return sale_id

    def open_sale(self, sale_id: str):
        """
        Transition sale from DRAFT to OPEN.
        Locks the order for payment. No more item/discount/tax changes allowed.
        """
        sale = self.get_sale(sale_id)
        self._assert_owner(sale)
        if sale.state != SaleState.DRAFT:
            raise ValueError(f"Cannot open sale in state {sale.state}. Must be DRAFT.")
        if not sale.line_items:
            raise ValueError("Cannot open sale with no line items")

        # Auto-calculate total
        sale._recalculate_total()

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.SALE_OPENED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "sale_id": sale_id,
                "barber_id": self.barber_id,
                "total": sale.total.to_dict(),
            },
            created_at=utc_now(),
            idempotency_key=f"sale_opened_{sale_id}",
        )

        self._emit_event(event)

    def cancel_sale(self, sale_id: str, reason: str = ""):
        """
        Cancel a sale. Must be in DRAFT or OPEN state (no payments captured).
        """
        sale = self.get_sale(sale_id)
        self._assert_owner(sale)
        if sale.state not in (SaleState.DRAFT, SaleState.OPEN):
            raise ValueError(f"Cannot cancel sale in state {sale.state}. Use refund for completed sales.")

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.SALE_CANCELED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "sale_id": sale_id,
                "barber_id": self.barber_id,
                "reason": reason,
            },
            created_at=utc_now(),
            idempotency_key=f"sale_canceled_{sale_id}",
        )

        self._emit_event(event)

    # =========================================================================
    # LINE ITEMS
    # =========================================================================

    def add_line_item(
        self,
        sale_id: str,
        name: str,
        quantity: int,
        unit_price: Money,
        catalog_item_id: Optional[str] = None,
    ) -> str:
        """
        Add line item to sale. Sale must be in DRAFT state.
        Returns item_id.
        """
        sale = self.get_sale(sale_id)
        self._assert_owner(sale)
        if sale.state != SaleState.DRAFT:
            raise ValueError(f"Cannot add items to sale in state {sale.state}. Must be DRAFT.")

        item_id = str(uuid.uuid4())
        total = Money(amount_minor=unit_price.amount_minor * quantity)

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.LINE_ITEM_ADDED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "sale_id": sale_id,
                "barber_id": self.barber_id,
                "item_id": item_id,
                "name": name,
                "quantity": quantity,
                "unit_price": unit_price.to_dict(),
                "total": total.to_dict(),
                "catalog_item_id": catalog_item_id,
            },
            created_at=utc_now(),
            idempotency_key=f"line_item_{item_id}",
        )

        self._emit_event(event)
        return item_id

    def remove_line_item(self, sale_id: str, item_id: str):
        """Remove a line item from sale. Sale must be in DRAFT state."""
        sale = self.get_sale(sale_id)
        self._assert_owner(sale)
        if sale.state != SaleState.DRAFT:
            raise ValueError(f"Cannot remove items from sale in state {sale.state}. Must be DRAFT.")

        # Verify item exists
        item = next((i for i in sale.line_items if i.item_id == item_id), None)
        if not item:
            raise ValueError(f"Item {item_id} not found in sale {sale_id}")

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.LINE_ITEM_REMOVED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "sale_id": sale_id,
                "barber_id": self.barber_id,
                "item_id": item_id,
                "removed_amount": item.total.to_dict(),
            },
            created_at=utc_now(),
            idempotency_key=f"line_item_removed_{item_id}_{sale_id}",
        )

        self._emit_event(event)

    # =========================================================================
    # DISCOUNTS & TAX & TIPS
    # =========================================================================

    def apply_discount(self, sale_id: str, amount: Money, reason: str = ""):
        """Apply discount to sale. Sale must be in DRAFT state."""
        sale = self.get_sale(sale_id)
        self._assert_owner(sale)
        if sale.state != SaleState.DRAFT:
            raise ValueError(f"Cannot apply discount in state {sale.state}")

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.DISCOUNT_APPLIED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "sale_id": sale_id,
                "barber_id": self.barber_id,
                "amount": amount.to_dict(),
                "reason": reason,
            },
            created_at=utc_now(),
            idempotency_key=f"discount_{sale_id}_{generate_event_id()[:8]}",
        )

        self._emit_event(event)

    def calculate_tax(self, sale_id: str, tax_rate: float = 0.08):
        """Calculate and apply tax. Sale must be in DRAFT state."""
        sale = self.get_sale(sale_id)
        self._assert_owner(sale)
        if sale.state != SaleState.DRAFT:
            raise ValueError(f"Cannot calculate tax in state {sale.state}")

        taxable_amount = max(0, sale.subtotal.amount_minor - sale.discounts.amount_minor)
        tax_amount = int(taxable_amount * tax_rate)
        tax = Money(amount_minor=tax_amount)

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.TAX_CALCULATED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "sale_id": sale_id,
                "barber_id": self.barber_id,
                "tax": tax.to_dict(),
                "tax_rate": tax_rate,
            },
            created_at=utc_now(),
            idempotency_key=f"tax_{sale_id}_{generate_event_id()[:8]}",
        )

        self._emit_event(event)

    def add_tip(self, sale_id: str, tip_amount: Money):
        """Add tip to a sale. Can be added in OPEN or COMPLETED state (post-auth tip adjust)."""
        sale = self.get_sale(sale_id)
        self._assert_owner(sale)
        if sale.state not in (SaleState.DRAFT, SaleState.OPEN, SaleState.COMPLETED):
            raise ValueError(f"Cannot add tip in state {sale.state}")

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.TIP_ADDED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "sale_id": sale_id,
                "barber_id": self.barber_id,
                "tip": tip_amount.to_dict(),
            },
            created_at=utc_now(),
            idempotency_key=f"tip_{sale_id}_{generate_event_id()[:8]}",
        )

        self._emit_event(event)

    # =========================================================================
    # PAYMENTS
    # =========================================================================

    def take_payment(
        self,
        sale_id: str,
        amount: Money,
        method: PaymentMethod,
        tip: Optional[Money] = None,
        card_last_four: Optional[str] = None,
    ) -> Tuple[str, PaymentState]:
        """
        Take payment for a sale.
        Sale auto-transitions DRAFT → OPEN if still in DRAFT.
        Must be in OPEN state to accept payment.
        Returns (payment_id, final_state).
        """
        sale = self.get_sale(sale_id)
        self._assert_owner(sale)

        # Auto-open if still DRAFT (convenience for simple flows)
        if sale.state == SaleState.DRAFT:
            self.open_sale(sale_id)
            sale = self.get_sale(sale_id)

        if sale.state != SaleState.OPEN:
            raise ValueError(f"Cannot take payment on sale in state {sale.state}. Must be OPEN.")

        payment_id = str(uuid.uuid4())
        idempotency_key = f"payment_{payment_id}"
        tip_money = tip or Money(amount_minor=0)

        # PAYMENT_INITIATED event - stored under SALE aggregate
        # so get_sale() can see it during reconstruction
        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.PAYMENT_INITIATED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "payment_id": payment_id,
                "sale_id": sale_id,
                "barber_id": self.barber_id,
                "amount": amount.to_dict(),
                "tip": tip_money.to_dict(),
                "method": method.value,
                "card_last_four": card_last_four,
            },
            created_at=utc_now(),
            idempotency_key=idempotency_key,
        )
        self._emit_event(event)

        # State machine progression
        if method == PaymentMethod.CASH or self.hardware_mode == HardwareMode.SOFTWARE_ONLY:
            return self._capture_payment(payment_id, sale_id, amount, tip_money)
        else:
            return self._authorize_and_capture_payment(payment_id, sale_id, amount, tip_money)

    def _authorize_and_capture_payment(
        self, payment_id: str, sale_id: str, amount: Money, tip: Money
    ) -> Tuple[str, PaymentState]:
        """Card authorization then capture."""
        auth_event = Event(
            event_id=generate_event_id(),
            event_type=EventType.PAYMENT_AUTHORIZED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "payment_id": payment_id,
                "sale_id": sale_id,
                "barber_id": self.barber_id,
                "authorized_at": utc_now(),
            },
            created_at=utc_now(),
        )
        self._emit_event(auth_event)
        return self._capture_payment(payment_id, sale_id, amount, tip)

    def _capture_payment(
        self, payment_id: str, sale_id: str, amount: Money, tip: Money
    ) -> Tuple[str, PaymentState]:
        """Capture (settle) payment and mark sale COMPLETED."""
        captured_event = Event(
            event_id=generate_event_id(),
            event_type=EventType.PAYMENT_CAPTURED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "payment_id": payment_id,
                "sale_id": sale_id,
                "barber_id": self.barber_id,
                "amount": amount.to_dict(),
                "tip": tip.to_dict(),
                "captured_at": utc_now(),
            },
            created_at=utc_now(),
        )
        self._emit_event(captured_event)

        # Auto-update BarberScore after successful payment
        if self.eligibility_engine:
            try:
                self.eligibility_engine.update_and_emit_entitlements(self.barber_id)
            except Exception as e:
                print(f"Score auto-update failed (non-blocking): {e}")

        return (payment_id, PaymentState.CAPTURED)

    # =========================================================================
    # REFUNDS & VOIDS
    # =========================================================================

    def create_refund(
        self,
        sale_id: str,
        amount: Money,
        reason: str = "",
        payment_id: Optional[str] = None,
    ) -> str:
        """
        Create a refund for a completed sale.
        Supports partial refunds - sale stays COMPLETED.
        Only changes to VOIDED if full amount is refunded.
        """
        sale = self.get_sale(sale_id)
        self._assert_owner(sale)
        if sale.state != SaleState.COMPLETED:
            raise ValueError(f"Cannot refund sale in state {sale.state}. Must be COMPLETED.")

        # Validate refund amount doesn't exceed remaining
        already_refunded = sale.refunded_amount.amount_minor
        remaining = sale.total.amount_minor - already_refunded
        if amount.amount_minor > remaining:
            raise ValueError(
                f"Refund amount ({amount.amount_minor}) exceeds remaining "
                f"refundable amount ({remaining})"
            )

        refund_id = str(uuid.uuid4())
        idempotency_key = f"refund_{refund_id}"

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.REFUND_CREATED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "refund_id": refund_id,
                "sale_id": sale_id,
                "barber_id": self.barber_id,
                "amount": amount.to_dict(),
                "reason": reason,
                "payment_id": payment_id,
            },
            created_at=utc_now(),
            idempotency_key=idempotency_key,
        )

        self._emit_event(event)
        return refund_id

    def void_sale(self, sale_id: str, reason: str = "") -> bool:
        """
        Void a sale. Must be in DRAFT or OPEN state (before payment capture).
        For post-capture cancellation, use create_refund instead.
        """
        sale = self.get_sale(sale_id)
        self._assert_owner(sale)
        if sale.state not in (SaleState.DRAFT, SaleState.OPEN):
            raise ValueError(
                f"Cannot void sale in state {sale.state}. "
                f"Use refund for completed sales."
            )

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.VOID_APPLIED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "sale_id": sale_id,
                "barber_id": self.barber_id,
                "reason": reason,
            },
            created_at=utc_now(),
            idempotency_key=f"void_{sale_id}",
        )

        self._emit_event(event)
        return True

    # =========================================================================
    # SHIFTS
    # =========================================================================

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

    def close_shift(self, shift_id: str, ending_cash: Money, total_sales: Money) -> str:
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

    # =========================================================================
    # OFFLINE SYNC
    # =========================================================================

    def sync_offline_events(self) -> int:
        """Sync local queue to cloud. Returns number of events synced."""
        if not self.is_online:
            raise RuntimeError("Cannot sync while offline")
        return self.local_queue.sync_to_cloud(self.cloud_store)

    # =========================================================================
    # SALE RECONSTRUCTION FROM EVENTS
    # =========================================================================

    def get_sale(self, sale_id: str) -> Sale:
        """Reconstruct sale from events"""
        events = self.cloud_store.get_events(
            aggregate_type="sale", aggregate_id=sale_id
        )

        if not events:
            raise ValueError(f"Sale {sale_id} not found")

        # Extract barber_id from SALE_CREATED event
        barber_id = self.barber_id
        for e in events:
            if e.event_type == EventType.SALE_CREATED:
                barber_id = e.payload.get("barber_id", self.barber_id)
                break

        sale = Sale(
            sale_id=sale_id,
            barber_id=barber_id,
            state=SaleState.DRAFT,
        )

        for event in events:
            self._apply_event_to_sale(sale, event)

        return sale

    def _apply_event_to_sale(self, sale: Sale, event: Event):
        """Apply event to sale aggregate"""
        sale.version += 1

        if event.event_type == EventType.SALE_CREATED:
            sale.created_at = event.created_at
            sale.metadata = event.payload.get("metadata", {})
            sale.customer_id = event.payload.get("customer_id")

        elif event.event_type == EventType.LINE_ITEM_ADDED:
            item = LineItem(
                item_id=event.payload["item_id"],
                name=event.payload["name"],
                quantity=event.payload["quantity"],
                unit_price=Money(**event.payload["unit_price"]),
                total=Money(**event.payload["total"]),
                catalog_item_id=event.payload.get("catalog_item_id"),
            )
            sale.line_items.append(item)
            sale.subtotal = Money(
                amount_minor=sale.subtotal.amount_minor + item.total.amount_minor
            )

        elif event.event_type == EventType.LINE_ITEM_REMOVED:
            removed_amount = Money(**event.payload["removed_amount"])
            item_id = event.payload["item_id"]
            sale.line_items = [i for i in sale.line_items if i.item_id != item_id]
            sale.subtotal = Money(
                amount_minor=max(0, sale.subtotal.amount_minor - removed_amount.amount_minor)
            )

        elif event.event_type == EventType.DISCOUNT_APPLIED:
            discount_amount = Money(**event.payload["amount"])
            sale.discounts = Money(
                amount_minor=sale.discounts.amount_minor + discount_amount.amount_minor
            )

        elif event.event_type == EventType.TAX_CALCULATED:
            sale.tax = Money(**event.payload["tax"])

        elif event.event_type == EventType.TIP_ADDED:
            sale.tip = Money(**event.payload["tip"])

        elif event.event_type == EventType.SALE_OPENED:
            sale.state = SaleState.OPEN
            sale._recalculate_total()

        elif event.event_type == EventType.SALE_CANCELED:
            sale.state = SaleState.CANCELED
            sale.canceled_at = event.created_at

        elif event.event_type == EventType.PAYMENT_INITIATED:
            pass  # Tracked but doesn't change sale state

        elif event.event_type == EventType.PAYMENT_AUTHORIZED:
            pass  # Tracked but doesn't change sale state

        elif event.event_type == EventType.PAYMENT_CAPTURED:
            amount = Money(**event.payload["amount"])
            tip = Money(**event.payload.get("tip", {"amount_minor": 0}))
            sale.payments.append({
                "payment_id": event.payload["payment_id"],
                "amount": amount.to_dict(),
                "tip": tip.to_dict(),
                "captured_at": event.payload.get("captured_at"),
                "method": event.payload.get("method"),
            })
            sale.state = SaleState.COMPLETED
            sale.completed_at = event.created_at
            sale._recalculate_total()

        elif event.event_type == EventType.REFUND_CREATED:
            refund_amount = Money(**event.payload["amount"])
            sale.refunds.append(Refund(
                refund_id=event.payload["refund_id"],
                amount=refund_amount,
                reason=event.payload.get("reason", ""),
                created_at=event.created_at,
                payment_id=event.payload.get("payment_id"),
            ))
            sale.refunded_amount = Money(
                amount_minor=sale.refunded_amount.amount_minor + refund_amount.amount_minor
            )
            # Sale stays COMPLETED for partial refunds

        elif event.event_type == EventType.VOID_APPLIED:
            sale.state = SaleState.VOIDED

    # =========================================================================
    # PAYMENT RECONSTRUCTION
    # =========================================================================

    def get_payment(self, payment_id: str) -> Payment:
        """Reconstruct payment from events stored under sale aggregate"""
        # Search all sale events for this payment_id
        # Since payments are now stored under sale aggregate, we need to find them
        events = self.cloud_store.get_events(aggregate_type="sale")

        payment_data = None
        state = PaymentState.INITIATED
        authorized_at = None
        captured_at = None
        sale_id = None
        tip = Money(amount_minor=0)

        for event in events:
            pid = event.payload.get("payment_id")
            if pid != payment_id:
                continue

            if event.event_type == EventType.PAYMENT_INITIATED:
                payment_data = event.payload
                state = PaymentState.INITIATED
                sale_id = event.payload.get("sale_id")
                tip = Money(**event.payload.get("tip", {"amount_minor": 0}))

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
            raise ValueError(f"Payment {payment_id} not found")

        return Payment(
            payment_id=payment_data["payment_id"],
            sale_id=payment_data["sale_id"],
            barber_id=payment_data["barber_id"],
            amount=Money(**payment_data["amount"]),
            tip=tip,
            state=state,
            method=PaymentMethod(payment_data["method"]),
            created_at=events[0].created_at if events else utc_now(),
            authorized_at=authorized_at,
            captured_at=captured_at,
            card_last_four=payment_data.get("card_last_four"),
        )

    # =========================================================================
    # QUERIES
    # =========================================================================

    def list_barber_sales(self, since: Optional[str] = None, limit: Optional[int] = None) -> List[Sale]:
        """List all sales for this barber, optionally filtered by date"""
        events = self.cloud_store.get_events(
            event_type=EventType.SALE_CREATED,
            since=since,
        )

        sale_ids = []
        for event in events:
            if event.payload.get("barber_id") == self.barber_id:
                sale_ids.append(event.payload["sale_id"])

        if limit:
            sale_ids = sale_ids[-limit:]

        sales = []
        for sale_id in sale_ids:
            try:
                sale = self.get_sale(sale_id)
                sales.append(sale)
            except ValueError:
                continue

        return sales

    def get_barber_revenue_today(self) -> Money:
        """Get total revenue for barber today from completed sales"""
        today = datetime.now(timezone.utc).date().isoformat()
        sales = self.list_barber_sales(since=f"{today}T00:00:00Z")

        total = 0
        for sale in sales:
            if sale.state == SaleState.COMPLETED:
                total += sale.total.amount_minor

        return Money(amount_minor=total)

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    def _assert_owner(self, sale: Sale):
        """Verify the current barber owns this sale"""
        if sale.barber_id != self.barber_id:
            raise ValueError(f"Sale {sale.sale_id} belongs to barber {sale.barber_id}, not {self.barber_id}")

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
