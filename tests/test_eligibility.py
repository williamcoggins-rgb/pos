"""
Tests for Eligibility Engine and Anti-Gaming Logic
"""

import pytest
from datetime import datetime, timezone, timedelta

from event_store import (
    CloudEventStore,
    Event,
    EventType,
    Money,
    generate_event_id,
)
from eligibility_engine import EligibilityEngine


class TestQualifiedTransactions:
    """Test qualified transaction logic"""

    def setup_method(self):
        self.cloud_store = CloudEventStore(":memory:")
        self.engine = EligibilityEngine(self.cloud_store)
        self.barber_id = "barber_123"

    def test_qualified_transaction_meets_minimum(self):
        """Transaction meets minimum amount and no refund"""
        # Create payment event with $10 (above $5 minimum)
        payment_event = Event(
            event_id=generate_event_id(),
            event_type=EventType.PAYMENT_CAPTURED,
            aggregate_id="payment_1",
            aggregate_type="payment",
            payload={
                "payment_id": "payment_1",
                "sale_id": "sale_1",
                "barber_id": self.barber_id,
                "amount": {"amount_minor": 1000, "currency": "USD"},
            },
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        assert self.engine._is_qualified_transaction(payment_event, [payment_event])

    def test_transaction_below_minimum_not_qualified(self):
        """Transaction below $5 minimum not qualified"""
        payment_event = Event(
            event_id=generate_event_id(),
            event_type=EventType.PAYMENT_CAPTURED,
            aggregate_id="payment_1",
            aggregate_type="payment",
            payload={
                "payment_id": "payment_1",
                "sale_id": "sale_1",
                "barber_id": self.barber_id,
                "amount": {"amount_minor": 400, "currency": "USD"},  # $4.00
            },
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        assert not self.engine._is_qualified_transaction(payment_event, [payment_event])

    def test_refunded_transaction_not_qualified(self):
        """Transaction refunded within quarantine period not qualified"""
        payment_time = datetime.now(timezone.utc)
        refund_time = payment_time + timedelta(days=3)  # Within 7 day quarantine

        payment_event = Event(
            event_id=generate_event_id(),
            event_type=EventType.PAYMENT_CAPTURED,
            aggregate_id="payment_1",
            aggregate_type="payment",
            payload={
                "payment_id": "payment_1",
                "sale_id": "sale_1",
                "barber_id": self.barber_id,
                "amount": {"amount_minor": 1000, "currency": "USD"},
            },
            created_at=payment_time.isoformat(),
        )

        refund_event = Event(
            event_id=generate_event_id(),
            event_type=EventType.REFUND_CREATED,
            aggregate_id="refund_1",
            aggregate_type="refund",
            payload={
                "refund_id": "refund_1",
                "sale_id": "sale_1",
                "amount": {"amount_minor": 1000, "currency": "USD"},
            },
            created_at=refund_time.isoformat(),
        )

        events = [payment_event, refund_event]
        assert not self.engine._is_qualified_transaction(payment_event, events)

    def test_late_refund_transaction_still_qualified(self):
        """Transaction refunded after quarantine period is still qualified"""
        payment_time = datetime.now(timezone.utc)
        refund_time = payment_time + timedelta(days=10)  # After 7 day quarantine

        payment_event = Event(
            event_id=generate_event_id(),
            event_type=EventType.PAYMENT_CAPTURED,
            aggregate_id="payment_1",
            aggregate_type="payment",
            payload={
                "payment_id": "payment_1",
                "sale_id": "sale_1",
                "barber_id": self.barber_id,
                "amount": {"amount_minor": 1000, "currency": "USD"},
            },
            created_at=payment_time.isoformat(),
        )

        refund_event = Event(
            event_id=generate_event_id(),
            event_type=EventType.REFUND_CREATED,
            aggregate_id="refund_1",
            aggregate_type="refund",
            payload={
                "refund_id": "refund_1",
                "sale_id": "sale_1",
                "amount": {"amount_minor": 1000, "currency": "USD"},
            },
            created_at=refund_time.isoformat(),
        )

        events = [payment_event, refund_event]
        assert self.engine._is_qualified_transaction(payment_event, events)


class TestAntiGaming:
    """Test anti-gaming pattern detection"""

    def setup_method(self):
        self.cloud_store = CloudEventStore(":memory:")
        self.engine = EligibilityEngine(self.cloud_store)
        self.barber_id = "barber_123"

    def test_identical_amounts_detected(self):
        """Detect repeated identical transaction amounts"""
        events = []
        for i in range(15):
            event = Event(
                event_id=generate_event_id(),
                event_type=EventType.PAYMENT_CAPTURED,
                aggregate_id=f"payment_{i}",
                aggregate_type="payment",
                payload={
                    "barber_id": self.barber_id,
                    "amount": {"amount_minor": 5000, "currency": "USD"},  # All $50
                },
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            events.append(event)

        flags = self.engine._detect_gaming_patterns(events)
        assert "IDENTICAL_AMOUNTS_REPEATED" in flags

    def test_excessive_refund_rate_detected(self):
        """Detect excessive refund rate"""
        events = []

        # 10 payments
        for i in range(10):
            payment = Event(
                event_id=generate_event_id(),
                event_type=EventType.PAYMENT_CAPTURED,
                aggregate_id=f"payment_{i}",
                aggregate_type="payment",
                payload={
                    "barber_id": self.barber_id,
                    "amount": {"amount_minor": 1000, "currency": "USD"},
                },
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            events.append(payment)

        # 3 refunds (30% rate, above 20% threshold)
        for i in range(3):
            refund = Event(
                event_id=generate_event_id(),
                event_type=EventType.REFUND_CREATED,
                aggregate_id=f"refund_{i}",
                aggregate_type="refund",
                payload={
                    "sale_id": f"sale_{i}",
                    "amount": {"amount_minor": 1000, "currency": "USD"},
                },
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            events.append(refund)

        flags = self.engine._detect_gaming_patterns(events)
        assert "EXCESSIVE_REFUND_RATE" in flags

    def test_void_spike_detected(self):
        """Detect void spike"""
        events = []

        # 20 payments with varied amounts spread over days (avoid triggering other flags)
        base_time = datetime(2024, 6, 15, 14, 0, 0, tzinfo=timezone.utc)
        amounts = [1250, 3500, 2100, 4800, 1900, 3200, 2750, 4100, 1850, 3900,
                   1300, 2600, 4400, 3100, 2200, 3700, 1600, 2900, 4500, 3300]
        for i in range(20):
            payment = Event(
                event_id=generate_event_id(),
                event_type=EventType.PAYMENT_CAPTURED,
                aggregate_id=f"payment_{i}",
                aggregate_type="payment",
                payload={
                    "barber_id": self.barber_id,
                    "amount": {"amount_minor": amounts[i], "currency": "USD"},
                },
                created_at=(base_time + timedelta(hours=i * 4)).isoformat(),
            )
            events.append(payment)

        # 5 voids (25% rate, above 15% threshold, meets min_voids=5)
        for i in range(5):
            void = Event(
                event_id=generate_event_id(),
                event_type=EventType.VOID_APPLIED,
                aggregate_id=f"sale_{i}",
                aggregate_type="sale",
                payload={
                    "sale_id": f"sale_{i}",
                    "reason": "test",
                },
                created_at=(base_time + timedelta(hours=i * 8)).isoformat(),
            )
            events.append(void)

        flags = self.engine._detect_gaming_patterns(events)
        assert "VOID_SPIKE" in flags

    def test_round_number_bias_detected(self):
        """Detect excessive round number amounts"""
        events = []

        # 10 payments, all exactly $10, $20, or $50, spread over days
        base_time = datetime(2024, 6, 15, 14, 0, 0, tzinfo=timezone.utc)
        round_amounts = [1000, 2000, 5000]
        for i in range(10):
            payment = Event(
                event_id=generate_event_id(),
                event_type=EventType.PAYMENT_CAPTURED,
                aggregate_id=f"payment_{i}",
                aggregate_type="payment",
                payload={
                    "barber_id": self.barber_id,
                    "amount": {"amount_minor": round_amounts[i % 3], "currency": "USD"},
                },
                created_at=(base_time + timedelta(hours=i * 4)).isoformat(),
            )
            events.append(payment)

        flags = self.engine._detect_gaming_patterns(events)
        assert "ROUND_NUMBER_BIAS" in flags

    def test_no_flags_for_legitimate_activity(self):
        """No flags for diverse, legitimate transaction patterns"""
        events = []

        # Varied amounts spread over multiple days during business hours
        base_time = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        amounts = [1250, 3500, 2100, 4800, 1900, 3200, 2750, 4100, 1850, 3900]
        for i, amount in enumerate(amounts):
            payment = Event(
                event_id=generate_event_id(),
                event_type=EventType.PAYMENT_CAPTURED,
                aggregate_id=f"payment_{i}",
                aggregate_type="payment",
                payload={
                    "barber_id": self.barber_id,
                    "amount": {"amount_minor": amount, "currency": "USD"},
                },
                created_at=(base_time + timedelta(days=i, hours=i % 6)).isoformat(),
            )
            events.append(payment)

        # One refund (10% rate, acceptable)
        refund = Event(
            event_id=generate_event_id(),
            event_type=EventType.REFUND_CREATED,
            aggregate_id="refund_1",
            aggregate_type="refund",
            payload={
                "sale_id": "sale_1",
                "amount": {"amount_minor": 1250, "currency": "USD"},
            },
            created_at=(base_time + timedelta(days=15)).isoformat(),
        )
        events.append(refund)

        flags = self.engine._detect_gaming_patterns(events)
        assert len(flags) == 0


class TestHardGates:
    """Test hard gate (P0 risk tripwire) logic"""

    def setup_method(self):
        self.cloud_store = CloudEventStore(":memory:")
        self.engine = EligibilityEngine(self.cloud_store)

    def test_excessive_refund_rate_blocks(self):
        """Excessive refund rate triggers hard gate"""
        from eligibility_engine import BarberMetrics

        metrics = BarberMetrics(
            barber_id="barber_123",
            qualified_transactions=10,
            refund_count=3,
            refund_rate=0.30,  # 30%, above 25% threshold
        )

        blocks = self.engine._apply_hard_gates(metrics, [])
        assert len(blocks) > 0
        assert any("25%" in block for block in blocks)

    def test_insufficient_history_blocks(self):
        """Insufficient transaction history triggers hard gate"""
        from eligibility_engine import BarberMetrics

        metrics = BarberMetrics(
            barber_id="barber_123",
            qualified_transactions=5,  # Below 10 minimum
            active_days=3,  # Below 7 minimum
        )

        blocks = self.engine._apply_hard_gates(metrics, [])
        assert len(blocks) > 0
        assert any("Insufficient" in block for block in blocks)

    def test_good_metrics_no_blocks(self):
        """Good metrics pass all hard gates"""
        from eligibility_engine import BarberMetrics

        metrics = BarberMetrics(
            barber_id="barber_123",
            qualified_transactions=50,
            active_days=30,
            refund_rate=0.05,  # 5%
            void_rate=0.02,  # 2%
            chargeback_rate=0.0,
        )

        blocks = self.engine._apply_hard_gates(metrics, [])
        assert len(blocks) == 0


class TestScoreCalculation:
    """Test BarberScore calculation"""

    def setup_method(self):
        self.cloud_store = CloudEventStore(":memory:")
        self.engine = EligibilityEngine(self.cloud_store)

    def test_score_increases_with_qualified_transactions(self):
        """Score increases with more qualified transactions"""
        from eligibility_engine import BarberMetrics

        metrics_low = BarberMetrics(
            barber_id="barber_123",
            qualified_transactions=10,
            total_revenue_cents=10000,
            active_days=10,
        )

        metrics_high = BarberMetrics(
            barber_id="barber_123",
            qualified_transactions=100,
            total_revenue_cents=100000,
            active_days=30,
        )

        score_low = self.engine._calculate_score(metrics_low, [], [])
        score_high = self.engine._calculate_score(metrics_high, [], [])

        assert score_high > score_low

    def test_flags_decrease_score(self):
        """Gaming flags decrease score"""
        from eligibility_engine import BarberMetrics

        metrics = BarberMetrics(
            barber_id="barber_123",
            qualified_transactions=50,
            total_revenue_cents=50000,
            active_days=30,
        )

        score_no_flags = self.engine._calculate_score(metrics, [], [])
        score_with_flags = self.engine._calculate_score(
            metrics,
            ["IDENTICAL_AMOUNTS_REPEATED", "ROUND_NUMBER_BIAS"],
            []
        )

        assert score_with_flags < score_no_flags

    def test_hard_gate_blocks_set_minimum_score(self):
        """Hard gate blocks set score to minimum"""
        from eligibility_engine import BarberMetrics

        metrics = BarberMetrics(
            barber_id="barber_123",
            qualified_transactions=100,
            total_revenue_cents=100000,
            active_days=60,
        )

        score = self.engine._calculate_score(
            metrics,
            [],
            ["Excessive refund rate"]
        )

        assert score == 0  # Minimum score

    def test_tier_determination(self):
        """Correct tier determined from score"""
        assert self.engine._determine_tier(0) == "Level 0"
        assert self.engine._determine_tier(50) == "Level 1"
        assert self.engine._determine_tier(70) == "Level 2"
        assert self.engine._determine_tier(85) == "Level 3"
        assert self.engine._determine_tier(95) == "Level 4"
