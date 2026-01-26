"""
BarberScore Eligibility Engine
Consumes POS events, calculates score with anti-gaming, outputs entitlements.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from event_store import (
    Event,
    EventType,
    Money,
    CloudEventStore,
    utc_now,
    generate_event_id,
)


@dataclass
class BarberMetrics:
    """Calculated metrics for a barber"""
    barber_id: str
    qualified_transactions: int = 0
    total_revenue_cents: int = 0
    refund_count: int = 0
    void_count: int = 0
    chargeback_count: int = 0
    active_days: int = 0
    avg_ticket_cents: float = 0.0
    refund_rate: float = 0.0
    void_rate: float = 0.0
    chargeback_rate: float = 0.0
    payment_methods_used: int = 0
    transaction_count_total: int = 0


@dataclass
class BarberScore:
    """Complete BarberScore with tier and flags"""
    barber_id: str
    score: int
    tier: str
    metrics: BarberMetrics
    flags: List[str] = field(default_factory=list)
    hard_gate_blocks: List[str] = field(default_factory=list)
    calculated_at: str = field(default_factory=utc_now)


@dataclass
class Entitlement:
    """Entitlement for procurement access"""
    barber_id: str
    entitlement_type: str  # "STORE_ACCESS_PREPAID", "TERMS_ELIGIBLE", etc.
    tier: str
    access_list: List[str]
    caps: Dict[str, int]
    granted_at: str
    expires_at: Optional[str] = None
    reason: str = ""


class EligibilityEngine:
    """
    BarberScore calculation engine with anti-gaming.
    Consumes POS events, produces entitlement events.
    """

    def __init__(
        self,
        cloud_store: CloudEventStore,
        config_dir: str = "config",
    ):
        self.cloud_store = cloud_store
        self.config_dir = Path(config_dir)

        # Load configurations
        self.score_rules = self._load_json("score_rules.json")
        self.entitlement_levels = self._load_json("entitlement_levels.json")
        self.anti_gaming_rules = self._load_json("anti_gaming_rules.json")

    def _load_json(self, filename: str) -> Dict:
        """Load configuration from JSON file"""
        path = self.config_dir / filename
        with open(path, 'r') as f:
            return json.load(f)

    def calculate_barberscore(self, barber_id: str) -> BarberScore:
        """
        Calculate BarberScore for a barber from their event history.
        Returns BarberScore with tier, metrics, and flags.
        """
        # Get all events for this barber
        events = self._get_barber_events(barber_id)

        # Calculate metrics
        metrics = self._calculate_metrics(barber_id, events)

        # Detect gaming patterns
        flags = self._detect_gaming_patterns(events)

        # Check hard gates
        hard_gate_blocks = self._apply_hard_gates(metrics, flags)

        # Calculate score
        score = self._calculate_score(metrics, flags, hard_gate_blocks)

        # Determine tier
        tier = self._determine_tier(score)

        return BarberScore(
            barber_id=barber_id,
            score=score,
            tier=tier,
            metrics=metrics,
            flags=flags,
            hard_gate_blocks=hard_gate_blocks,
        )

    def update_and_emit_entitlements(self, barber_id: str):
        """
        Calculate BarberScore and emit entitlement events.
        This is the main entry point for score updates.
        """
        # Calculate score
        barberscore = self.calculate_barberscore(barber_id)

        # Emit BARBERSCORE_UPDATED event
        score_event = Event(
            event_id=generate_event_id(),
            event_type=EventType.BARBERSCORE_UPDATED,
            aggregate_id=barber_id,
            aggregate_type="barber",
            payload={
                "barber_id": barber_id,
                "score": barberscore.score,
                "tier": barberscore.tier,
                "metrics": {
                    "qualified_transactions": barberscore.metrics.qualified_transactions,
                    "total_revenue_cents": barberscore.metrics.total_revenue_cents,
                    "refund_rate": barberscore.metrics.refund_rate,
                    "void_rate": barberscore.metrics.void_rate,
                    "chargeback_rate": barberscore.metrics.chargeback_rate,
                    "active_days": barberscore.metrics.active_days,
                    "avg_ticket_cents": barberscore.metrics.avg_ticket_cents,
                },
                "flags": barberscore.flags,
                "hard_gate_blocks": barberscore.hard_gate_blocks,
            },
            created_at=utc_now(),
        )
        self.cloud_store.append(score_event)

        # Generate entitlements if not blocked
        if not barberscore.hard_gate_blocks:
            self._emit_entitlement_events(barberscore)
        else:
            # Revoke entitlements if hard gates triggered
            self._revoke_entitlements(barber_id, barberscore.hard_gate_blocks)

    def _get_barber_events(self, barber_id: str) -> List[Event]:
        """Get all POS events for a barber"""
        # Get events where barber is in the payload
        all_events = self.cloud_store.get_events()

        barber_events = []
        for event in all_events:
            if event.payload.get("barber_id") == barber_id:
                barber_events.append(event)

        return barber_events

    def _calculate_metrics(self, barber_id: str, events: List[Event]) -> BarberMetrics:
        """Calculate barber metrics from events"""
        metrics = BarberMetrics(barber_id=barber_id)

        # Categorize events
        payment_events = []
        refund_events = []
        void_events = []

        for event in events:
            if event.event_type == EventType.PAYMENT_CAPTURED:
                payment_events.append(event)
            elif event.event_type == EventType.REFUND_CREATED:
                refund_events.append(event)
            elif event.event_type == EventType.VOID_APPLIED:
                void_events.append(event)

        # Calculate qualified transactions
        qualified_payments = []
        for payment_event in payment_events:
            if self._is_qualified_transaction(payment_event, events):
                qualified_payments.append(payment_event)

        metrics.qualified_transactions = len(qualified_payments)
        metrics.transaction_count_total = len(payment_events)

        # Calculate revenue from qualified transactions
        total_revenue = 0
        for payment in qualified_payments:
            amount = payment.payload.get("amount", {}).get("amount_minor", 0)
            total_revenue += amount
        metrics.total_revenue_cents = total_revenue

        # Average ticket
        if metrics.qualified_transactions > 0:
            metrics.avg_ticket_cents = total_revenue / metrics.qualified_transactions
        else:
            metrics.avg_ticket_cents = 0.0

        # Refund metrics
        metrics.refund_count = len(refund_events)
        if metrics.transaction_count_total > 0:
            metrics.refund_rate = metrics.refund_count / metrics.transaction_count_total
        else:
            metrics.refund_rate = 0.0

        # Void metrics
        metrics.void_count = len(void_events)
        if metrics.transaction_count_total > 0:
            metrics.void_rate = metrics.void_count / metrics.transaction_count_total
        else:
            metrics.void_rate = 0.0

        # Active days (unique dates with transactions)
        dates = set()
        for event in payment_events:
            date = event.created_at[:10]  # YYYY-MM-DD
            dates.add(date)
        metrics.active_days = len(dates)

        # Payment method diversity
        methods = set()
        for event in payment_events:
            # Look for associated payment initiated events
            payment_id = event.aggregate_id
            initiated_events = [
                e for e in events
                if e.event_type == EventType.PAYMENT_INITIATED
                and e.aggregate_id == payment_id
            ]
            if initiated_events:
                method = initiated_events[0].payload.get("method")
                if method:
                    methods.add(method)
        metrics.payment_methods_used = len(methods)

        # Chargebacks (placeholder - would come from payment processor)
        metrics.chargeback_count = 0
        metrics.chargeback_rate = 0.0

        return metrics

    def _is_qualified_transaction(self, payment_event: Event, all_events: List[Event]) -> bool:
        """
        Determine if a transaction is qualified based on rules.
        Returns True if it meets quality thresholds.
        """
        rules = self.score_rules["qualified_transaction_rules"]

        # Must be PAYMENT_CAPTURED
        if payment_event.event_type != EventType.PAYMENT_CAPTURED:
            return False

        # Get payment amount
        amount = payment_event.payload.get("amount", {}).get("amount_minor", 0)

        # Check minimum amount
        if amount < rules["min_amount_cents"]:
            return False

        # Check if refunded within quarantine period
        sale_id = payment_event.payload.get("sale_id")
        payment_time = datetime.fromisoformat(payment_event.created_at.replace('Z', '+00:00'))
        quarantine_days = rules["refund_quarantine_days"]
        quarantine_end = payment_time + timedelta(days=quarantine_days)

        # Look for refunds within quarantine window
        for event in all_events:
            if event.event_type == EventType.REFUND_CREATED:
                if event.payload.get("sale_id") == sale_id:
                    refund_time = datetime.fromisoformat(event.created_at.replace('Z', '+00:00'))
                    if refund_time <= quarantine_end:
                        return False  # Refunded too soon, not qualified

        return True

    def _detect_gaming_patterns(self, events: List[Event]) -> List[str]:
        """
        Detect suspicious patterns that indicate gaming.
        Returns list of flag strings.
        """
        flags = []
        patterns = self.anti_gaming_rules["pattern_detection"]

        # Get payment events
        payments = [e for e in events if e.event_type == EventType.PAYMENT_CAPTURED]

        if len(payments) == 0:
            return flags

        # 1. Identical amounts
        if patterns["identical_amounts"]["enabled"]:
            amounts = [e.payload.get("amount", {}).get("amount_minor", 0) for e in payments]
            unique_amounts = len(set(amounts))
            if (len(amounts) >= patterns["identical_amounts"]["min_occurrences"] and
                unique_amounts <= patterns["identical_amounts"]["uniqueness_threshold"]):
                flags.append(patterns["identical_amounts"]["flag"])

        # 2. Excessive refund rate
        if patterns["excessive_refund_rate"]["enabled"]:
            refunds = [e for e in events if e.event_type == EventType.REFUND_CREATED]
            if len(payments) > 0:
                refund_rate = len(refunds) / len(payments)
                if refund_rate > patterns["excessive_refund_rate"]["threshold"]:
                    flags.append(patterns["excessive_refund_rate"]["flag"])

        # 3. Refund clusters
        if patterns["refund_clusters"]["enabled"]:
            refunds = [e for e in events if e.event_type == EventType.REFUND_CREATED]
            window_hours = patterns["refund_clusters"]["window_hours"]

            # Check for clusters
            for i, refund in enumerate(refunds):
                cluster_count = 1
                refund_time = datetime.fromisoformat(refund.created_at.replace('Z', '+00:00'))

                for other_refund in refunds[i+1:]:
                    other_time = datetime.fromisoformat(other_refund.created_at.replace('Z', '+00:00'))
                    if (other_time - refund_time).total_seconds() / 3600 <= window_hours:
                        cluster_count += 1

                if cluster_count >= patterns["refund_clusters"]["min_refunds"]:
                    flags.append(patterns["refund_clusters"]["flag"])
                    break

        # 4. Void spike
        if patterns["void_spike"]["enabled"]:
            voids = [e for e in events if e.event_type == EventType.VOID_APPLIED]
            if len(voids) >= patterns["void_spike"]["min_voids"]:
                void_rate = len(voids) / len(payments) if len(payments) > 0 else 0
                if void_rate > patterns["void_spike"]["threshold"]:
                    flags.append(patterns["void_spike"]["flag"])

        # 5. Round number bias
        if patterns["round_number_bias"]["enabled"]:
            amounts = [e.payload.get("amount", {}).get("amount_minor", 0) for e in payments]
            round_amounts = patterns["round_number_bias"]["round_amounts"]
            round_count = sum(1 for amt in amounts if amt in round_amounts)
            if len(amounts) > 0:
                round_rate = round_count / len(amounts)
                if round_rate > patterns["round_number_bias"]["threshold"]:
                    flags.append(patterns["round_number_bias"]["flag"])

        # 6. Rapid sequence
        if patterns["rapid_sequence"]["enabled"]:
            window_minutes = patterns["rapid_sequence"]["window_minutes"]
            min_transactions = patterns["rapid_sequence"]["min_transactions"]

            for i, payment in enumerate(payments):
                rapid_count = 1
                payment_time = datetime.fromisoformat(payment.created_at.replace('Z', '+00:00'))

                for other_payment in payments[i+1:]:
                    other_time = datetime.fromisoformat(other_payment.created_at.replace('Z', '+00:00'))
                    if (other_time - payment_time).total_seconds() / 60 <= window_minutes:
                        rapid_count += 1

                if rapid_count >= min_transactions:
                    flags.append(patterns["rapid_sequence"]["flag"])
                    break

        # 7. Late night spike
        if patterns["late_night_spike"]["enabled"]:
            late_night_count = 0
            hours_start = patterns["late_night_spike"]["hours_start"]
            hours_end = patterns["late_night_spike"]["hours_end"]

            for payment in payments:
                payment_time = datetime.fromisoformat(payment.created_at.replace('Z', '+00:00'))
                hour = payment_time.hour
                if hours_start <= hour < hours_end:
                    late_night_count += 1

            if len(payments) > 0:
                late_night_rate = late_night_count / len(payments)
                if late_night_rate > patterns["late_night_spike"]["threshold"]:
                    flags.append(patterns["late_night_spike"]["flag"])

        # 8. Manual entry bias
        if patterns["manual_entry_bias"]["enabled"]:
            manual_count = 0
            for payment in payments:
                # Look for associated payment initiated events
                payment_id = payment.aggregate_id
                initiated_events = [
                    e for e in events
                    if e.event_type == EventType.PAYMENT_INITIATED
                    and e.aggregate_id == payment_id
                ]
                if initiated_events:
                    method = initiated_events[0].payload.get("method")
                    if method == "CARD_MANUAL":
                        manual_count += 1

            if len(payments) > 0:
                manual_rate = manual_count / len(payments)
                if manual_rate > patterns["manual_entry_bias"]["threshold"]:
                    flags.append(patterns["manual_entry_bias"]["flag"])

        return flags

    def _apply_hard_gates(self, metrics: BarberMetrics, flags: List[str]) -> List[str]:
        """
        Apply hard gates (P0 risk tripwires).
        Returns list of block reasons.
        """
        blocks = []
        hard_gates = self.score_rules["hard_gates"]

        # Excessive refund rate
        if metrics.refund_rate > hard_gates["excessive_refund_rate"]["threshold"]:
            blocks.append(hard_gates["excessive_refund_rate"]["reason"])

        # Chargeback spike
        if metrics.chargeback_rate > hard_gates["chargeback_spike"]["threshold"]:
            blocks.append(hard_gates["chargeback_spike"]["reason"])

        # Insufficient history
        insufficient = hard_gates["insufficient_history"]
        if (metrics.qualified_transactions < insufficient["min_qualified_transactions"] or
            metrics.active_days < insufficient["min_active_days"]):
            blocks.append(insufficient["reason"])

        return blocks

    def _calculate_score(
        self,
        metrics: BarberMetrics,
        flags: List[str],
        hard_gate_blocks: List[str],
    ) -> int:
        """
        Calculate BarberScore from metrics.
        Uses weighted composite with time decay.
        """
        if hard_gate_blocks:
            # Hard blocked, return minimum score
            return self.score_rules["score_calculation"]["min_score"]

        weights = self.score_rules["metric_weights"]
        base_score = self.score_rules["score_calculation"]["base_score"]

        # Start with base score
        score = float(base_score)

        # Completed transactions (normalized to 100 transactions = max contribution)
        tx_contribution = min(metrics.qualified_transactions / 100.0, 1.0) * 100 * weights["completed_transactions"]
        score += tx_contribution

        # Revenue consistency (normalized to $10k = max contribution)
        revenue_dollars = metrics.total_revenue_cents / 100.0
        revenue_contribution = min(revenue_dollars / 10000.0, 1.0) * 100 * weights["revenue_consistency"]
        score += revenue_contribution

        # Refund rate (negative impact)
        refund_penalty = metrics.refund_rate * 100 * weights["refund_rate"]
        score += refund_penalty  # Note: weight is negative

        # Void rate (negative impact)
        void_penalty = metrics.void_rate * 100 * weights["void_rate"]
        score += void_penalty  # Note: weight is negative

        # Chargeback rate (negative impact)
        chargeback_penalty = metrics.chargeback_rate * 100 * weights["chargeback_rate"]
        score += chargeback_penalty  # Note: weight is negative

        # Active days (normalized to 90 days = max contribution)
        active_contribution = min(metrics.active_days / 90.0, 1.0) * 100 * weights["active_days"]
        score += active_contribution

        # Average ticket size (normalized to $100 = max contribution)
        avg_ticket_dollars = metrics.avg_ticket_cents / 100.0
        ticket_contribution = min(avg_ticket_dollars / 100.0, 1.0) * 100 * weights["avg_ticket_size"]
        score += ticket_contribution

        # Payment method diversity (normalized to 4 methods = max contribution)
        diversity_contribution = min(metrics.payment_methods_used / 4.0, 1.0) * 100 * weights["payment_method_diversity"]
        score += diversity_contribution

        # Apply flag penalties
        flag_penalty = len(flags) * 5  # Each flag reduces score by 5
        score -= flag_penalty

        # Clamp to min/max
        min_score = self.score_rules["score_calculation"]["min_score"]
        max_score = self.score_rules["score_calculation"]["max_score"]
        score = max(min_score, min(max_score, int(score)))

        return score

    def _determine_tier(self, score: int) -> str:
        """Determine tier from score"""
        levels = self.entitlement_levels["levels"]

        for tier_name, tier_config in levels.items():
            if tier_config["score_min"] <= score <= tier_config["score_max"]:
                return tier_name

        return "Level 0"  # Default

    def _emit_entitlement_events(self, barberscore: BarberScore):
        """Emit entitlement events based on tier"""
        tier_config = self.entitlement_levels["levels"][barberscore.tier]

        entitlement = Entitlement(
            barber_id=barberscore.barber_id,
            entitlement_type="STORE_ACCESS" if barberscore.score >= 50 else "POS_ONLY",
            tier=barberscore.tier,
            access_list=tier_config["access"],
            caps=tier_config["caps"],
            granted_at=utc_now(),
            reason=f"BarberScore {barberscore.score} qualifies for {barberscore.tier}",
        )

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.ENTITLEMENT_GRANTED,
            aggregate_id=barberscore.barber_id,
            aggregate_type="barber",
            payload={
                "barber_id": barberscore.barber_id,
                "entitlement_type": entitlement.entitlement_type,
                "tier": entitlement.tier,
                "access": entitlement.access_list,
                "caps": entitlement.caps,
                "granted_at": entitlement.granted_at,
                "reason": entitlement.reason,
            },
            created_at=utc_now(),
        )

        self.cloud_store.append(event)

    def _revoke_entitlements(self, barber_id: str, reasons: List[str]):
        """Revoke entitlements due to hard gates"""
        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.ENTITLEMENT_REVOKED,
            aggregate_id=barber_id,
            aggregate_type="barber",
            payload={
                "barber_id": barber_id,
                "reasons": reasons,
                "revoked_at": utc_now(),
            },
            created_at=utc_now(),
        )

        self.cloud_store.append(event)
