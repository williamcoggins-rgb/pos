"""
Enforcement Middleware
Gates actions based on BarberScore entitlements.
Checks tier-based access and provides entitlement summaries.
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
    Entitlement enforcement for barber operations.
    Checks tier-based access before allowing actions.
    """

    def __init__(
        self,
        entitlement_ledger: EntitlementLedger,
        procurement_service: ProcurementService,
    ):
        self.entitlement_ledger = entitlement_ledger
        self.procurement_service = procurement_service

    def can_access_procurement(self, barber_id: str) -> EnforcementResult:
        """
        Check if barber can access procurement features.
        Requires Level 1+ (score >= 50).
        """
        entitlement = self.entitlement_ledger.get_entitlement(barber_id)

        if not entitlement:
            return EnforcementResult(
                allowed=False,
                reason="No entitlement found. Use POS to build your BarberScore.",
                blocked_by="access",
            )

        if not entitlement.is_active:
            reasons = ", ".join(entitlement.blocked_reasons)
            return EnforcementResult(
                allowed=False,
                reason=f"Access locked: {reasons}",
                blocked_by="blocked",
                current_entitlement=entitlement,
            )

        if not self.entitlement_ledger.has_access(barber_id, "STORE_PREPAID"):
            return EnforcementResult(
                allowed=False,
                reason=f"Procurement not available for {entitlement.tier}. "
                       f"Build your score to Level 1 (50+) to unlock.",
                blocked_by="access",
                current_entitlement=entitlement,
            )

        return EnforcementResult(
            allowed=True,
            reason="Procurement access available",
            current_entitlement=entitlement,
        )

    def get_pricing_tier(self, barber_id: str) -> str:
        """Get pricing tier for barber (for discount calculation)"""
        entitlement = self.entitlement_ledger.get_entitlement(barber_id)

        if not entitlement or not entitlement.is_active:
            return "STANDARD"

        if "BEST_PRICING" in entitlement.access_list:
            return "BEST"
        elif "BETTER_PRICING" in entitlement.access_list:
            return "BETTER"
        else:
            return "STANDARD"

    def get_fulfillment_sla(self, barber_id: str) -> str:
        """Get fulfillment SLA for barber"""
        entitlement = self.entitlement_ledger.get_entitlement(barber_id)

        if not entitlement or not entitlement.is_active:
            return "STANDARD"

        if "PRIORITY_FULFILLMENT" in entitlement.access_list:
            return "PRIORITY"
        else:
            return "STANDARD"

    def get_entitlement_summary(self, barber_id: str) -> Dict[str, Any]:
        """
        Get comprehensive entitlement summary for UI display.
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
            "Level 4": "Level 4",
        }
        return tier_progression.get(current_tier, "Unknown")

    def _calculate_next_tier_progress(
        self,
        entitlement: CurrentEntitlement
    ) -> Tuple[str, int]:
        """Calculate progress to next tier."""
        tier_thresholds = {
            "Level 0": 50,
            "Level 1": 70,
            "Level 2": 85,
            "Level 3": 95,
            "Level 4": 100,
        }

        current = entitlement.tier
        next_tier = self._next_tier(current)

        if next_tier == current:
            return (next_tier, 0)

        next_threshold = tier_thresholds[next_tier]
        points_needed = max(0, next_threshold - entitlement.score)

        return (next_tier, points_needed)

    def get_unlock_requirements(self, barber_id: str, desired_tier: str) -> Dict[str, Any]:
        """Get requirements to unlock a specific tier."""
        entitlement = self.entitlement_ledger.get_entitlement(barber_id)
        current_score = entitlement.score if entitlement else 0

        tier_requirements = {
            "Level 1": {
                "score": 50,
                "benefits": [
                    "Procurement access (signal readiness)",
                    "Administration outreach for supplies",
                ],
            },
            "Level 2": {
                "score": 70,
                "benefits": [
                    "Better pricing on supplies",
                    "Higher order limits",
                ],
            },
            "Level 3": {
                "score": 85,
                "benefits": [
                    "Net-30 payment terms",
                    "Premium pricing",
                ],
            },
            "Level 4": {
                "score": 95,
                "benefits": [
                    "Best pricing available",
                    "Priority fulfillment",
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

    # Legacy compatibility
    def validate_order_creation(self, barber_id: str, line_items) -> EnforcementResult:
        """Legacy compat — redirects to procurement access check."""
        return self.can_access_procurement(barber_id)
