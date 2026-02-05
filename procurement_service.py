"""
Procurement Readiness Service
Signals that a barber is ready for the next tier of procurement access.
Administration monitors these signals and reaches out via notification/email.
This is NOT an ordering system — it's a readiness notification pipeline.
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


class SignalStatus(str, Enum):
    """Status of a procurement readiness signal"""
    PENDING = "PENDING"        # Barber expressed interest, awaiting admin review
    CONTACTED = "CONTACTED"    # Admin has reached out to barber
    ACTIVE = "ACTIVE"          # Procurement relationship is active
    DECLINED = "DECLINED"      # Barber declined or didn't respond
    EXPIRED = "EXPIRED"        # Signal expired without action


class FulfillmentSLA(str, Enum):
    """Fulfillment service levels (used for tier display)"""
    STANDARD = "STANDARD"    # 3-5 business days
    PRIORITY = "PRIORITY"    # 24-48 hours (Level 4 barbers)


@dataclass
class ReadinessSignal:
    """A procurement readiness signal from a barber"""
    signal_id: str
    barber_id: str
    tier: str
    score: int
    status: SignalStatus
    contact_preference: str = "email"  # email, phone, both
    message: str = ""                  # optional message from barber
    created_at: Optional[str] = None
    contacted_at: Optional[str] = None
    resolved_at: Optional[str] = None
    admin_notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class ProcurementService:
    """
    Procurement readiness signal service.
    Barbers signal interest → admin gets notified → admin reaches out.
    No direct ordering or fulfillment tracking.
    """

    def __init__(self, cloud_store: CloudEventStore):
        self.cloud_store = cloud_store

    def signal_readiness(
        self,
        barber_id: str,
        tier: str,
        score: int,
        contact_preference: str = "email",
        message: str = "",
    ) -> str:
        """
        Barber signals they are ready for procurement access.
        Emits a PROCUREMENT_READINESS_SIGNAL event for admin monitoring.
        Returns signal_id.
        """
        signal_id = str(uuid.uuid4())
        idempotency_key = f"readiness_signal_{barber_id}_{tier}"

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.PROCUREMENT_READINESS_SIGNAL,
            aggregate_id=signal_id,
            aggregate_type="procurement_signal",
            payload={
                "signal_id": signal_id,
                "barber_id": barber_id,
                "tier": tier,
                "score": score,
                "status": SignalStatus.PENDING.value,
                "contact_preference": contact_preference,
                "message": message,
            },
            created_at=utc_now(),
            idempotency_key=idempotency_key,
        )

        self.cloud_store.append(event)
        return signal_id

    def mark_contacted(
        self,
        signal_id: str,
        admin_notes: str = "",
    ):
        """Admin marks a signal as contacted (admin-side action)."""
        signal = self.get_signal(signal_id)
        if signal.status != SignalStatus.PENDING:
            raise ValueError(f"Cannot mark signal in status {signal.status} as contacted")

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.PROCUREMENT_ADMIN_CONTACTED,
            aggregate_id=signal_id,
            aggregate_type="procurement_signal",
            payload={
                "signal_id": signal_id,
                "barber_id": signal.barber_id,
                "admin_notes": admin_notes,
                "contacted_at": utc_now(),
            },
            created_at=utc_now(),
        )

        self.cloud_store.append(event)

    def mark_active(self, signal_id: str, admin_notes: str = ""):
        """Admin activates procurement relationship after contact."""
        signal = self.get_signal(signal_id)
        if signal.status not in (SignalStatus.PENDING, SignalStatus.CONTACTED):
            raise ValueError(f"Cannot activate signal in status {signal.status}")

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.PROCUREMENT_ACTIVATED,
            aggregate_id=signal_id,
            aggregate_type="procurement_signal",
            payload={
                "signal_id": signal_id,
                "barber_id": signal.barber_id,
                "admin_notes": admin_notes,
                "activated_at": utc_now(),
            },
            created_at=utc_now(),
        )

        self.cloud_store.append(event)

    def get_signal(self, signal_id: str) -> ReadinessSignal:
        """Reconstruct signal from events."""
        events = self.cloud_store.get_events(
            aggregate_type="procurement_signal",
            aggregate_id=signal_id,
        )

        if not events:
            raise ValueError(f"Signal {signal_id} not found")

        signal = ReadinessSignal(
            signal_id=signal_id,
            barber_id="",
            tier="",
            score=0,
            status=SignalStatus.PENDING,
        )

        for event in events:
            self._apply_event(signal, event)

        return signal

    def _apply_event(self, signal: ReadinessSignal, event: Event):
        """Apply event to signal aggregate."""
        if event.event_type == EventType.PROCUREMENT_READINESS_SIGNAL:
            signal.barber_id = event.payload["barber_id"]
            signal.tier = event.payload["tier"]
            signal.score = event.payload["score"]
            signal.status = SignalStatus(event.payload["status"])
            signal.contact_preference = event.payload.get("contact_preference", "email")
            signal.message = event.payload.get("message", "")
            signal.created_at = event.created_at

        elif event.event_type == EventType.PROCUREMENT_ADMIN_CONTACTED:
            signal.status = SignalStatus.CONTACTED
            signal.contacted_at = event.payload.get("contacted_at")
            signal.admin_notes = event.payload.get("admin_notes", "")

        elif event.event_type == EventType.PROCUREMENT_ACTIVATED:
            signal.status = SignalStatus.ACTIVE
            signal.resolved_at = event.payload.get("activated_at")
            if event.payload.get("admin_notes"):
                signal.admin_notes = event.payload["admin_notes"]

    def get_barber_signals(self, barber_id: str) -> List[ReadinessSignal]:
        """Get all readiness signals for a barber."""
        events = self.cloud_store.get_events(aggregate_type="procurement_signal")

        signal_ids = set()
        for event in events:
            if event.payload.get("barber_id") == barber_id:
                signal_ids.add(event.aggregate_id)

        signals = []
        for signal_id in signal_ids:
            try:
                signal = self.get_signal(signal_id)
                signals.append(signal)
            except ValueError:
                continue

        return signals

    def get_pending_signals(self) -> List[ReadinessSignal]:
        """Get all pending signals (admin dashboard query)."""
        events = self.cloud_store.get_events(
            event_type=EventType.PROCUREMENT_READINESS_SIGNAL,
        )

        signals = []
        for event in events:
            try:
                signal = self.get_signal(event.aggregate_id)
                if signal.status == SignalStatus.PENDING:
                    signals.append(signal)
            except ValueError:
                continue

        return signals

    def has_active_signal(self, barber_id: str) -> bool:
        """Check if barber already has a pending or active signal."""
        signals = self.get_barber_signals(barber_id)
        return any(
            s.status in (SignalStatus.PENDING, SignalStatus.CONTACTED, SignalStatus.ACTIVE)
            for s in signals
        )

    # Legacy compatibility: used by enforcement middleware
    def get_barber_orders(self, barber_id: str) -> list:
        """Legacy compat — returns empty list since we no longer track orders."""
        return []

    def get_order(self, order_id: str):
        """Legacy compat — raises not found."""
        raise ValueError(f"Order system has been replaced by readiness signals. Signal ID: {order_id}")
