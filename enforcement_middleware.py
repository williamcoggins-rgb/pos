"""
Enforcement Middleware
Gates procurement actions based on BarberScore entitlements.
"""

from dataclasses import dataclass
from typing import Tuple, Optional, List, Dict, Any

from event_store import Money
from entitlement_ledger import EntitlementLedger, CurrentEntitlement
from procurement_service import ProcurementService


@dataclass
class EnforcementResult:
    """Result of enforcement check"""
    allowed: bool
    reason: str = ""
    blocked_by: Optional[str] = None  # "cap", "access", "tier", "blocked"
    current_entitlement: Optional[CurrentEntitlement] = None


class EnforcementMiddleware:
    """
    Entitlement enforcement for procurement operations.
    Checks tier-based access and caps before allowing actions.
    """

    def __init__(
        self,
        entitlement_ledger: EntitlementLedger,
        procurement_service: ProcurementService,
    ):
        self.entitlement_ledger = entitlement_ledger
        self.procurement_service = procurement_service

    def can_place_order(
        self,
        barber_id: str,
        order_value: Money,
    ) -> EnforcementResult:
        """
        Check if barber can place a procurement order.

        Returns:
            EnforcementResult with allowed=True if permitted, False with reason if blocked.
        """
        # Get current entitlement
        entitlement = self.entitlement_ledger.get_entitlement(barber_id)

        if not entitlement:
            return EnforcementResult(
                allowed=False,
                reason="No entitlement found. Use POS to build your BarberScore.",
                blocked_by="access",
            )

        # Check if active
        if not entitlement.is_active:
            reasons = ", ".join(entitlement.blocked_reasons)
            return EnforcementResult(
                allowed=False,
                reason=f"Store access locked: {reasons}",
                blocked_by="blocked",
                current_entitlement=entitlement,
            )

        # Check store access
        if not self.entitlement_ledger.has_access(barber_id, "STORE_PREPAID"):
            return EnforcementResult(
                allowed=False,
                reason=f"Store access not available for {entitlement.tier}. "
                       f"Build your score to Level 1 (50+) to unlock.",
                blocked_by="access",
                current_entitlement=entitlement,
            )

        # Check order value cap
        max_order_value = entitlement.caps.get("max_order_value")
        if max_order_value is not None:
            if order_value.amount_minor > max_order_value:
                return EnforcementResult(
                    allowed=False,
                    reason=f"Order value ${order_value.amount_dollars:.2f} exceeds "
                           f"your cap of ${max_order_value/100:.2f}. "
                           f"Upgrade to {self._next_tier(entitlement.tier)} to increase limit.",
                    blocked_by="cap",
                    current_entitlement=entitlement,
                )

        # All checks passed
        return EnforcementResult(
            allowed=True,
            reason="Order approved",
            current_entitlement=entitlement,
        )

    def can_use_terms(
        self,
        barber_id: str,
        invoice_amount: Money,
        outstanding_balance: Money,
    ) -> EnforcementResult:
        """
        Check if barber can use net terms (credit).

        Returns:
            EnforcementResult with allowed=True if permitted, False with reason if blocked.
        """
        # Get current entitlement
        entitlement = self.entitlement_ledger.get_entitlement(barber_id)

        if not entitlement or not entitlement.is_active:
            return EnforcementResult(
                allowed=False,
                reason="Terms not available. No active entitlement.",
                blocked_by="access",
                current_entitlement=entitlement,
            )

        # Check terms access
        if not self.entitlement_ledger.has_access(barber_id, "TERMS_ELIGIBLE"):
            return EnforcementResult(
                allowed=False,
                reason=f"Net terms not available for {entitlement.tier}. "
                       f"Build your score to Level 3 (85+) to unlock.",
                blocked_by="access",
                current_entitlement=entitlement,
            )

        # Check outstanding balance cap
        max_outstanding = entitlement.caps.get("max_terms_outstanding")
        if max_outstanding is not None:
            new_balance = outstanding_balance.amount_minor + invoice_amount.amount_minor
            if new_balance > max_outstanding:
                available = max_outstanding - outstanding_balance.amount_minor
                return EnforcementResult(
                    allowed=False,
                    reason=f"Outstanding balance limit exceeded. "
                           f"Available credit: ${available/100:.2f}. "
                           f"Pay down existing invoices or upgrade to {self._next_tier(entitlement.tier)}.",
                    blocked_by="cap",
                    current_entitlement=entitlement,
                )

        return EnforcementResult(
            allowed=True,
            reason="Terms approved",
            current_entitlement=entitlement,
        )

    def get_pricing_tier(self, barber_id: str) -> str:
        """Get pricing tier for barber (for discount calculation)"""
        entitlement = self.entitlement_ledger.get_entitlement(barber_id)

        if not entitlement or not entitlement.is_active:
            return "STANDARD"  # No discount

        if "BEST_PRICING" in entitlement.access_list:
            return "BEST"  # 15% discount
        elif "BETTER_PRICING" in entitlement.access_list:
            return "BETTER"  # 10% discount or 5% depending on tier
        else:
            return "STANDARD"  # No discount

    def get_fulfillment_sla(self, barber_id: str) -> str:
        """Get fulfillment SLA for barber"""
        entitlement = self.entitlement_ledger.get_entitlement(barber_id)

        if not entitlement or not entitlement.is_active:
            return "STANDARD"

        if "PRIORITY_FULFILLMENT" in entitlement.access_list:
            return "PRIORITY"  # 24hr SLA
        else:
            return "STANDARD"  # 3-5 days

    def get_entitlement_summary(self, barber_id: str) -> Dict[str, Any]:
        """
        Get comprehensive entitlement summary for UI display.

        Returns:
            Dictionary with current tier, access, caps, next tier info, etc.
        """
        entitlement = self.entitlement_ledger.get_entitlement(barber_id)

        if not entitlement:
            return {
                "barber_id": barber_id,
                "tier": "Level 0",
                "score": 0,
                "is_active": False,
                "access": ["POS_ONLY"],
                "caps": {},
                "store_access": False,
                "terms_access": False,
                "pricing_tier": "STANDARD",
                "fulfillment_sla": "STANDARD",
                "next_tier": "Level 1",
                "points_to_next": 50,
                "blocked_reasons": ["No entitlement found. Use POS to build score."],
            }

        next_tier, points_needed = self._calculate_next_tier_progress(entitlement)

        return {
            "barber_id": barber_id,
            "tier": entitlement.tier,
            "score": entitlement.score,
            "is_active": entitlement.is_active,
            "access": entitlement.access_list,
            "caps": entitlement.caps,
            "store_access": "STORE_PREPAID" in entitlement.access_list,
            "terms_access": "TERMS_ELIGIBLE" in entitlement.access_list or "TERMS_MATURE" in entitlement.access_list,
            "pricing_tier": self.get_pricing_tier(barber_id),
            "fulfillment_sla": self.get_fulfillment_sla(barber_id),
            "next_tier": next_tier,
            "points_to_next": points_needed,
            "blocked_reasons": entitlement.blocked_reasons,
            "granted_at": entitlement.granted_at,
            "last_updated": entitlement.last_updated,
        }

    def _next_tier(self, current_tier: str) -> str:
        """Get next tier name"""
        tier_progression = {
            "Level 0": "Level 1",
            "Level 1": "Level 2",
            "Level 2": "Level 3",
            "Level 3": "Level 4",
            "Level 4": "Level 4",  # Already at max
        }
        return tier_progression.get(current_tier, "Unknown")

    def _calculate_next_tier_progress(
        self,
        entitlement: CurrentEntitlement
    ) -> Tuple[str, int]:
        """
        Calculate progress to next tier.

        Returns:
            (next_tier_name, points_needed)
        """
        tier_thresholds = {
            "Level 0": 50,
            "Level 1": 70,
            "Level 2": 85,
            "Level 3": 95,
            "Level 4": 100,  # Max tier
        }

        current = entitlement.tier
        next_tier = self._next_tier(current)

        if next_tier == current:
            # Already at max
            return (next_tier, 0)

        next_threshold = tier_thresholds[next_tier]
        points_needed = max(0, next_threshold - entitlement.score)

        return (next_tier, points_needed)

    def validate_order_creation(
        self,
        barber_id: str,
        line_items: List[Dict[str, Any]],
    ) -> EnforcementResult:
        """
        Validate order before creation (convenience method).

        Calculates total and checks enforcement.
        """
        # Calculate order total
        total = 0
        for item in line_items:
            unit_price = item["unit_price"]["amount_minor"]
            quantity = item["quantity"]
            total += unit_price * quantity

        # Add tax and shipping estimate
        tax = int(total * 0.08)
        shipping = 1000  # $10 standard
        total_with_fees = total + tax + shipping

        order_value = Money(amount_minor=total_with_fees)

        return self.can_place_order(barber_id, order_value)

    def get_unlock_requirements(self, barber_id: str, desired_tier: str) -> Dict[str, Any]:
        """
        Get requirements to unlock a specific tier.

        Returns:
            Dictionary with current status, requirements, and gap analysis.
        """
        entitlement = self.entitlement_ledger.get_entitlement(barber_id)
        current_score = entitlement.score if entitlement else 0

        tier_requirements = {
            "Level 1": {
                "score": 50,
                "benefits": [
                    "Procurement store access",
                    "Prepaid orders up to $500",
                ],
            },
            "Level 2": {
                "score": 70,
                "benefits": [
                    "5% discount on supplies",
                    "Orders up to $1,500",
                ],
            },
            "Level 3": {
                "score": 85,
                "benefits": [
                    "10% discount on supplies",
                    "Net-30 terms up to $1,000",
                    "Orders up to $3,000",
                ],
            },
            "Level 4": {
                "score": 95,
                "benefits": [
                    "15% discount on supplies",
                    "Net-60 terms up to $5,000",
                    "Priority fulfillment (24hr SLA)",
                    "Dedicated account manager",
                ],
            },
        }

        requirements = tier_requirements.get(desired_tier, {})
        required_score = requirements.get("score", 0)
        gap = max(0, required_score - current_score)

        return {
            "desired_tier": desired_tier,
            "required_score": required_score,
            "current_score": current_score,
            "points_needed": gap,
            "benefits": requirements.get("benefits", []),
            "is_unlocked": current_score >= required_score,
        }
