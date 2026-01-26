"""
Procurement Service
Handles warehouse orders and fulfillment with event-driven workflow.
"""

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any

from event_store import (
    Event,
    EventType,
    Money,
    CloudEventStore,
    utc_now,
    generate_event_id,
)


class OrderState(str, Enum):
    """Procurement order lifecycle states"""
    CREATED = "CREATED"
    PAID = "PAID"
    PICKING = "PICKING"
    PICKED = "PICKED"
    PACKED = "PACKED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELED = "CANCELED"
    RETURNED = "RETURNED"


class FulfillmentSLA(str, Enum):
    """Fulfillment service levels"""
    STANDARD = "STANDARD"  # 3-5 business days
    PRIORITY = "PRIORITY"  # 24-48 hours (Level 4 barbers)


@dataclass
class OrderLineItem:
    """Line item in a procurement order"""
    sku: str
    name: str
    quantity: int
    unit_price: Money
    total: Money


@dataclass
class ProcurementOrder:
    """Procurement order aggregate"""
    order_id: str
    barber_id: str
    state: OrderState
    line_items: List[OrderLineItem] = field(default_factory=list)
    subtotal: Money = field(default_factory=lambda: Money(amount_minor=0))
    tax: Money = field(default_factory=lambda: Money(amount_minor=0))
    shipping: Money = field(default_factory=lambda: Money(amount_minor=0))
    total: Money = field(default_factory=lambda: Money(amount_minor=0))
    sla: FulfillmentSLA = FulfillmentSLA.STANDARD
    created_at: Optional[str] = None
    paid_at: Optional[str] = None
    shipped_at: Optional[str] = None
    delivered_at: Optional[str] = None
    tracking_number: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ProcurementService:
    """
    Procurement and warehouse service.
    Event-sourced order management with fulfillment workflow.
    """

    def __init__(self, cloud_store: CloudEventStore):
        self.cloud_store = cloud_store

    def create_order(
        self,
        barber_id: str,
        line_items: List[Dict[str, Any]],
        sla: FulfillmentSLA = FulfillmentSLA.STANDARD,
    ) -> str:
        """
        Create a new procurement order.
        Returns order_id.
        """
        order_id = str(uuid.uuid4())
        idempotency_key = f"order_created_{order_id}"

        # Calculate totals
        subtotal = 0
        items = []
        for item_data in line_items:
            unit_price = Money(**item_data["unit_price"])
            quantity = item_data["quantity"]
            total = Money(amount_minor=unit_price.amount_minor * quantity)
            subtotal += total.amount_minor

            items.append({
                "sku": item_data["sku"],
                "name": item_data["name"],
                "quantity": quantity,
                "unit_price": unit_price.to_dict(),
                "total": total.to_dict(),
            })

        # Calculate tax (8% for example)
        tax = int(subtotal * 0.08)

        # Calculate shipping
        shipping = 1000 if sla == FulfillmentSLA.STANDARD else 2500  # $10 or $25

        total = subtotal + tax + shipping

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.PROCUREMENT_ORDER_CREATED,
            aggregate_id=order_id,
            aggregate_type="procurement_order",
            payload={
                "order_id": order_id,
                "barber_id": barber_id,
                "line_items": items,
                "subtotal": {"amount_minor": subtotal, "currency": "USD"},
                "tax": {"amount_minor": tax, "currency": "USD"},
                "shipping": {"amount_minor": shipping, "currency": "USD"},
                "total": {"amount_minor": total, "currency": "USD"},
                "sla": sla.value,
            },
            created_at=utc_now(),
            idempotency_key=idempotency_key,
        )

        self.cloud_store.append(event)
        return order_id

    def pay_order(
        self,
        order_id: str,
        payment_method: str,
        payment_id: str,
    ):
        """
        Mark order as paid.
        Triggers warehouse fulfillment workflow.
        """
        order = self.get_order(order_id)
        if order.state != OrderState.CREATED:
            raise ValueError(f"Cannot pay order in state {order.state}")

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.PROCUREMENT_ORDER_PAID,
            aggregate_id=order_id,
            aggregate_type="procurement_order",
            payload={
                "order_id": order_id,
                "payment_method": payment_method,
                "payment_id": payment_id,
                "paid_at": utc_now(),
            },
            created_at=utc_now(),
        )

        self.cloud_store.append(event)

        # Trigger warehouse workflow
        self._create_picklist(order_id, order.barber_id)

    def cancel_order(self, order_id: str, reason: str = ""):
        """Cancel an order (before shipping)"""
        order = self.get_order(order_id)
        if order.state in [OrderState.SHIPPED, OrderState.DELIVERED]:
            raise ValueError(f"Cannot cancel order in state {order.state}. Use return instead.")

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.PROCUREMENT_ORDER_CANCELED,
            aggregate_id=order_id,
            aggregate_type="procurement_order",
            payload={
                "order_id": order_id,
                "reason": reason,
                "canceled_at": utc_now(),
            },
            created_at=utc_now(),
        )

        self.cloud_store.append(event)

    def _create_picklist(self, order_id: str, barber_id: str):
        """Create warehouse picklist (internal)"""
        picklist_id = str(uuid.uuid4())

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.PICKLIST_CREATED,
            aggregate_id=picklist_id,
            aggregate_type="warehouse_picklist",
            payload={
                "picklist_id": picklist_id,
                "order_id": order_id,
                "barber_id": barber_id,
                "created_at": utc_now(),
            },
            created_at=utc_now(),
        )

        self.cloud_store.append(event)
        return picklist_id

    def mark_order_picked(self, order_id: str):
        """Mark order as picked by warehouse"""
        order = self.get_order(order_id)
        if order.state != OrderState.PAID:
            raise ValueError(f"Cannot pick order in state {order.state}")

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.ORDER_PICKED,
            aggregate_id=order_id,
            aggregate_type="procurement_order",
            payload={
                "order_id": order_id,
                "picked_at": utc_now(),
            },
            created_at=utc_now(),
        )

        self.cloud_store.append(event)

    def mark_order_packed(self, order_id: str):
        """Mark order as packed"""
        order = self.get_order(order_id)
        if order.state != OrderState.PICKED:
            raise ValueError(f"Cannot pack order in state {order.state}")

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.ORDER_PACKED,
            aggregate_id=order_id,
            aggregate_type="procurement_order",
            payload={
                "order_id": order_id,
                "packed_at": utc_now(),
            },
            created_at=utc_now(),
        )

        self.cloud_store.append(event)

    def dispatch_shipment(
        self,
        order_id: str,
        tracking_number: str,
        carrier: str = "USPS",
    ):
        """Dispatch shipment to customer"""
        order = self.get_order(order_id)
        if order.state != OrderState.PACKED:
            raise ValueError(f"Cannot ship order in state {order.state}")

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.SHIPMENT_DISPATCHED,
            aggregate_id=order_id,
            aggregate_type="procurement_order",
            payload={
                "order_id": order_id,
                "tracking_number": tracking_number,
                "carrier": carrier,
                "shipped_at": utc_now(),
            },
            created_at=utc_now(),
        )

        self.cloud_store.append(event)

    def confirm_delivery(self, order_id: str):
        """Confirm order delivery"""
        order = self.get_order(order_id)
        if order.state != OrderState.SHIPPED:
            raise ValueError(f"Cannot confirm delivery for order in state {order.state}")

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.DELIVERY_CONFIRMED,
            aggregate_id=order_id,
            aggregate_type="procurement_order",
            payload={
                "order_id": order_id,
                "delivered_at": utc_now(),
            },
            created_at=utc_now(),
        )

        self.cloud_store.append(event)

    def receive_return(
        self,
        order_id: str,
        reason: str,
        refund_amount: Money,
    ):
        """Process order return"""
        order = self.get_order(order_id)
        if order.state != OrderState.DELIVERED:
            raise ValueError(f"Cannot return order in state {order.state}")

        return_id = str(uuid.uuid4())

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.RETURN_RECEIVED,
            aggregate_id=return_id,
            aggregate_type="warehouse_return",
            payload={
                "return_id": return_id,
                "order_id": order_id,
                "reason": reason,
                "refund_amount": refund_amount.to_dict(),
                "received_at": utc_now(),
            },
            created_at=utc_now(),
        )

        self.cloud_store.append(event)
        return return_id

    def get_order(self, order_id: str) -> ProcurementOrder:
        """Reconstruct order from events"""
        events = self.cloud_store.get_events(
            aggregate_type="procurement_order",
            aggregate_id=order_id
        )

        if not events:
            raise ValueError(f"Order {order_id} not found")

        order = ProcurementOrder(
            order_id=order_id,
            barber_id="",
            state=OrderState.CREATED,
        )

        for event in events:
            self._apply_event_to_order(order, event)

        return order

    def _apply_event_to_order(self, order: ProcurementOrder, event: Event):
        """Apply event to order aggregate"""
        if event.event_type == EventType.PROCUREMENT_ORDER_CREATED:
            order.barber_id = event.payload["barber_id"]
            order.created_at = event.created_at

            # Line items
            for item_data in event.payload["line_items"]:
                item = OrderLineItem(
                    sku=item_data["sku"],
                    name=item_data["name"],
                    quantity=item_data["quantity"],
                    unit_price=Money(**item_data["unit_price"]),
                    total=Money(**item_data["total"]),
                )
                order.line_items.append(item)

            order.subtotal = Money(**event.payload["subtotal"])
            order.tax = Money(**event.payload["tax"])
            order.shipping = Money(**event.payload["shipping"])
            order.total = Money(**event.payload["total"])
            order.sla = FulfillmentSLA(event.payload["sla"])

        elif event.event_type == EventType.PROCUREMENT_ORDER_PAID:
            order.state = OrderState.PAID
            order.paid_at = event.payload["paid_at"]

        elif event.event_type == EventType.PROCUREMENT_ORDER_CANCELED:
            order.state = OrderState.CANCELED

        elif event.event_type == EventType.ORDER_PICKED:
            order.state = OrderState.PICKED

        elif event.event_type == EventType.ORDER_PACKED:
            order.state = OrderState.PACKED

        elif event.event_type == EventType.SHIPMENT_DISPATCHED:
            order.state = OrderState.SHIPPED
            order.tracking_number = event.payload["tracking_number"]
            order.shipped_at = event.payload["shipped_at"]

        elif event.event_type == EventType.DELIVERY_CONFIRMED:
            order.state = OrderState.DELIVERED
            order.delivered_at = event.payload["delivered_at"]

    def get_barber_orders(self, barber_id: str) -> List[ProcurementOrder]:
        """Get all orders for a barber"""
        events = self.cloud_store.get_events(aggregate_type="procurement_order")

        order_ids = set()
        for event in events:
            if event.payload.get("barber_id") == barber_id:
                order_ids.add(event.aggregate_id)

        orders = []
        for order_id in order_ids:
            try:
                order = self.get_order(order_id)
                orders.append(order)
            except ValueError:
                continue

        return orders
