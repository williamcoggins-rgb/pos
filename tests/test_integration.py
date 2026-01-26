"""
End-to-End Integration Tests
Tests the full flow: POS → BarberScore → Entitlements → Procurement
"""

import pytest
from datetime import datetime, timezone

from event_store import CloudEventStore, LocalEventQueue, Money
from square_like_pos import POSRuntime, PaymentMethod, HardwareMode
from eligibility_engine import EligibilityEngine
from entitlement_ledger import EntitlementLedger
from procurement_service import ProcurementService, FulfillmentSLA
from enforcement_middleware import EnforcementMiddleware


class TestEndToEndFlow:
    """Test complete POS → Procurement integration"""

    def setup_method(self):
        # Initialize all components
        self.cloud_store = CloudEventStore(":memory:")
        self.local_queue = LocalEventQueue(":memory:")
        self.entitlement_ledger = EntitlementLedger(":memory:")
        self.eligibility_engine = EligibilityEngine(self.cloud_store)
        self.procurement_service = ProcurementService(self.cloud_store)
        self.enforcement = EnforcementMiddleware(
            self.entitlement_ledger,
            self.procurement_service,
        )

        # Subscribe ledger to events
        self.entitlement_ledger.subscribe_to_events(self.cloud_store)

        self.barber_id = "barber_alice"

    def test_new_barber_cannot_access_store(self):
        """New barber with no transactions cannot access procurement store"""
        # Check store access
        result = self.enforcement.can_place_order(
            self.barber_id,
            Money(amount_minor=10000),
        )

        assert not result.allowed
        assert "No entitlement found" in result.reason

    def test_barber_unlocks_store_with_transactions(self):
        """Barber unlocks store access after qualifying transactions"""
        # Initialize POS for barber
        pos = POSRuntime(
            barber_id=self.barber_id,
            cloud_store=self.cloud_store,
            local_queue=self.local_queue,
            hardware_mode=HardwareMode.FULL,
            is_online=True,
        )

        # Simulate 15 qualifying transactions over $5
        for i in range(15):
            sale_id = pos.create_sale()
            pos.add_line_item(
                sale_id,
                name=f"Haircut {i}",
                quantity=1,
                unit_price=Money.from_dollars(35.00),
            )
            pos.calculate_tax(sale_id)
            pos.take_payment(
                sale_id,
                amount=Money.from_dollars(37.80),  # With tax
                method=PaymentMethod.CARD_PRESENT,
            )

        # Calculate BarberScore
        barberscore = self.eligibility_engine.calculate_barberscore(self.barber_id)

        # Should be at least Level 1 (50+)
        assert barberscore.score >= 50
        assert barberscore.tier == "Level 1"

        # Emit entitlements
        self.eligibility_engine.update_and_emit_entitlements(self.barber_id)

        # Check store access now granted
        result = self.enforcement.can_place_order(
            self.barber_id,
            Money(amount_minor=40000),  # $400
        )

        assert result.allowed
        assert result.current_entitlement.tier == "Level 1"

    def test_level_1_barber_blocked_by_cap(self):
        """Level 1 barber blocked from large orders"""
        # Set up Level 1 barber (from previous test)
        pos = POSRuntime(
            barber_id=self.barber_id,
            cloud_store=self.cloud_store,
            local_queue=self.local_queue,
        )

        # Create 15 transactions
        for i in range(15):
            sale_id = pos.create_sale()
            pos.add_line_item(
                sale_id,
                name=f"Service {i}",
                quantity=1,
                unit_price=Money.from_dollars(30.00),
            )
            pos.calculate_tax(sale_id)
            pos.take_payment(
                sale_id,
                amount=Money.from_dollars(32.40),
                method=PaymentMethod.CARD_PRESENT,
            )

        self.eligibility_engine.update_and_emit_entitlements(self.barber_id)

        # Try to place $600 order (over Level 1 cap of $500)
        result = self.enforcement.can_place_order(
            self.barber_id,
            Money(amount_minor=60000),
        )

        assert not result.allowed
        assert "exceeds your cap" in result.reason
        assert "$500" in result.reason

    def test_barber_progresses_to_level_2(self):
        """Barber with strong metrics progresses to Level 2"""
        pos = POSRuntime(
            barber_id=self.barber_id,
            cloud_store=self.cloud_store,
            local_queue=self.local_queue,
        )

        # Create 50 diverse, high-quality transactions
        amounts = [25, 35, 45, 30, 40, 50, 28, 38, 42, 32]
        for i in range(50):
            sale_id = pos.create_sale()
            amount = amounts[i % len(amounts)]
            pos.add_line_item(
                sale_id,
                name=f"Service {i}",
                quantity=1,
                unit_price=Money.from_dollars(amount),
            )
            pos.calculate_tax(sale_id)
            pos.take_payment(
                sale_id,
                amount=Money.from_dollars(amount * 1.08),
                method=PaymentMethod.CARD_PRESENT if i % 3 != 0 else PaymentMethod.CASH,
            )

        # Calculate score
        barberscore = self.eligibility_engine.calculate_barberscore(self.barber_id)

        # Should reach Level 2 (70+)
        assert barberscore.score >= 70
        assert barberscore.tier == "Level 2"

        # Update entitlements
        self.eligibility_engine.update_and_emit_entitlements(self.barber_id)

        # Can now place larger orders
        result = self.enforcement.can_place_order(
            self.barber_id,
            Money(amount_minor=120000),  # $1,200
        )

        assert result.allowed
        assert result.current_entitlement.tier == "Level 2"

        # Gets better pricing
        pricing = self.enforcement.get_pricing_tier(self.barber_id)
        assert pricing == "BETTER"

    def test_excessive_refunds_trigger_hard_gate(self):
        """Excessive refunds block entitlements"""
        pos = POSRuntime(
            barber_id=self.barber_id,
            cloud_store=self.cloud_store,
            local_queue=self.local_queue,
        )

        # Create 10 transactions
        sale_ids = []
        for i in range(10):
            sale_id = pos.create_sale()
            pos.add_line_item(
                sale_id,
                name=f"Service {i}",
                quantity=1,
                unit_price=Money.from_dollars(30.00),
            )
            pos.calculate_tax(sale_id)
            pos.take_payment(
                sale_id,
                amount=Money.from_dollars(32.40),
                method=PaymentMethod.CARD_PRESENT,
            )
            sale_ids.append(sale_id)

        # Refund 4 of them (40% refund rate, exceeds 25% threshold)
        for i in range(4):
            pos.create_refund(
                sale_ids[i],
                amount=Money.from_dollars(32.40),
                reason="Customer request",
            )

        # Calculate score
        barberscore = self.eligibility_engine.calculate_barberscore(self.barber_id)

        # Hard gate should be triggered
        assert len(barberscore.hard_gate_blocks) > 0
        assert any("refund" in block.lower() for block in barberscore.hard_gate_blocks)

        # Update entitlements (should revoke)
        self.eligibility_engine.update_and_emit_entitlements(self.barber_id)

        # Store access should be blocked
        result = self.enforcement.can_place_order(
            self.barber_id,
            Money(amount_minor=10000),
        )

        assert not result.allowed
        assert result.blocked_by == "blocked"

    def test_complete_procurement_flow(self):
        """Complete flow: qualify → order → fulfill"""
        # Step 1: Build BarberScore
        pos = POSRuntime(
            barber_id=self.barber_id,
            cloud_store=self.cloud_store,
            local_queue=self.local_queue,
        )

        for i in range(30):
            sale_id = pos.create_sale()
            pos.add_line_item(
                sale_id,
                name="Haircut",
                quantity=1,
                unit_price=Money.from_dollars(35.00),
            )
            pos.calculate_tax(sale_id)
            payment_id, state = pos.take_payment(
                sale_id,
                amount=Money.from_dollars(37.80),
                method=PaymentMethod.CARD_PRESENT,
            )

        # Step 2: Grant entitlements
        self.eligibility_engine.update_and_emit_entitlements(self.barber_id)

        # Step 3: Check enforcement
        line_items = [
            {
                "sku": "SHAMPOO_001",
                "name": "Professional Shampoo",
                "quantity": 3,
                "unit_price": {"amount_minor": 2500, "currency": "USD"},
            },
            {
                "sku": "COMB_001",
                "name": "Professional Comb Set",
                "quantity": 2,
                "unit_price": {"amount_minor": 1500, "currency": "USD"},
            },
        ]

        validation = self.enforcement.validate_order_creation(
            self.barber_id,
            line_items,
        )

        assert validation.allowed

        # Step 4: Create order
        order_id = self.procurement_service.create_order(
            self.barber_id,
            line_items,
            sla=FulfillmentSLA.STANDARD,
        )

        # Step 5: Pay order
        self.procurement_service.pay_order(
            order_id,
            payment_method="CARD",
            payment_id="pay_123",
        )

        # Step 6: Fulfill
        self.procurement_service.mark_order_picked(order_id)
        self.procurement_service.mark_order_packed(order_id)
        self.procurement_service.dispatch_shipment(
            order_id,
            tracking_number="USPS123456",
        )
        self.procurement_service.confirm_delivery(order_id)

        # Verify order state
        order = self.procurement_service.get_order(order_id)
        assert order.state.value == "DELIVERED"
        assert order.tracking_number == "USPS123456"

    def test_gaming_patterns_prevent_progression(self):
        """Gaming patterns flag barber and limit score"""
        pos = POSRuntime(
            barber_id=self.barber_id,
            cloud_store=self.cloud_store,
            local_queue=self.local_queue,
        )

        # Create 20 transactions with identical amounts (gaming pattern)
        for i in range(20):
            sale_id = pos.create_sale()
            pos.add_line_item(
                sale_id,
                name="Service",
                quantity=1,
                unit_price=Money.from_dollars(50.00),  # Always $50
            )
            pos.calculate_tax(sale_id)
            pos.take_payment(
                sale_id,
                amount=Money.from_dollars(54.00),
                method=PaymentMethod.CARD_MANUAL,  # Always manual (another pattern)
            )

        # Calculate score
        barberscore = self.eligibility_engine.calculate_barberscore(self.barber_id)

        # Flags should be present
        assert len(barberscore.flags) > 0
        assert "IDENTICAL_AMOUNTS_REPEATED" in barberscore.flags

        # Score should be penalized
        # Even with 20 transactions, score should be lower due to flags
        assert barberscore.score < 65  # Would be higher without flags

    def test_offline_sync_preserves_score_calculation(self):
        """Events created offline sync and calculate score correctly"""
        # Start offline
        pos = POSRuntime(
            barber_id=self.barber_id,
            cloud_store=self.cloud_store,
            local_queue=self.local_queue,
            is_online=False,  # Offline mode
        )

        # Create transactions offline (go to local queue)
        for i in range(10):
            sale_id = pos.create_sale()
            pos.add_line_item(
                sale_id,
                name="Service",
                quantity=1,
                unit_price=Money.from_dollars(30.00),
            )
            pos.calculate_tax(sale_id)
            pos.take_payment(
                sale_id,
                amount=Money.from_dollars(32.40),
                method=PaymentMethod.CASH,
            )

        # Verify events are queued locally
        pending_count = self.local_queue.get_pending_count()
        assert pending_count > 0

        # Come back online and sync
        pos.is_online = True
        synced_count = pos.sync_offline_events()
        assert synced_count > 0

        # Calculate score from synced events
        barberscore = self.eligibility_engine.calculate_barberscore(self.barber_id)

        # Should have qualified transactions
        assert barberscore.metrics.qualified_transactions > 0
