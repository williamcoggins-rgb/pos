"""
POS → BarberScore → Procurement Integration
Event-sourced system for tier-based access control.
"""

__version__ = "1.0.0"

from event_store import (
    CloudEventStore,
    LocalEventQueue,
    Event,
    EventType,
    Money,
)

from square_like_pos import (
    POSRuntime,
    PaymentMethod,
    PaymentState,
    SaleState,
    HardwareMode,
)

from eligibility_engine import (
    EligibilityEngine,
    BarberScore,
    BarberMetrics,
)

from entitlement_ledger import (
    EntitlementLedger,
    CurrentEntitlement,
)

from enforcement_middleware import (
    EnforcementMiddleware,
    EnforcementResult,
)

from procurement_service import (
    ProcurementService,
    ProcurementOrder,
    OrderState,
    FulfillmentSLA,
)

__all__ = [
    # Event Store
    "CloudEventStore",
    "LocalEventQueue",
    "Event",
    "EventType",
    "Money",
    # POS
    "POSRuntime",
    "PaymentMethod",
    "PaymentState",
    "SaleState",
    "HardwareMode",
    # Eligibility
    "EligibilityEngine",
    "BarberScore",
    "BarberMetrics",
    # Entitlements
    "EntitlementLedger",
    "CurrentEntitlement",
    # Enforcement
    "EnforcementMiddleware",
    "EnforcementResult",
    # Procurement
    "ProcurementService",
    "ProcurementOrder",
    "OrderState",
    "FulfillmentSLA",
]
