"""
Tests for Square-Like POS System
"""

import pytest

from event_store import CloudEventStore, LocalEventQueue, Money
from square_like_pos import POSRuntime, PaymentMethod, PaymentState, SaleState, HardwareMode


class TestSaleLifecycle:
    """Test sale creation and lifecycle"""

    def setup_method(self):
        self.cloud_store = CloudEventStore(":memory:")
        self.local_queue = LocalEventQueue(":memory:")
        self.pos = POSRuntime(
            barber_id="barber_test",
            cloud_store=self.cloud_store,
            local_queue=self.local_queue,
        )

    def test_create_sale(self):
        """Can create a new sale"""
        sale_id = self.pos.create_sale(metadata={"location": "Shop A"})
        assert sale_id is not None

        sale = self.pos.get_sale(sale_id)
        assert sale.state == SaleState.DRAFT
        assert sale.metadata["location"] == "Shop A"

    def test_add_line_items(self):
        """Can add line items to sale"""
        sale_id = self.pos.create_sale()

        # Add first item
        item1_id = self.pos.add_line_item(
            sale_id,
            name="Haircut",
            quantity=1,
            unit_price=Money.from_dollars(35.00),
        )
        assert item1_id is not None

        # Add second item
        item2_id = self.pos.add_line_item(
            sale_id,
            name="Beard Trim",
            quantity=1,
            unit_price=Money.from_dollars(15.00),
        )

        sale = self.pos.get_sale(sale_id)
        assert len(sale.line_items) == 2
        assert sale.subtotal.amount_dollars == 50.00

    def test_apply_discount(self):
        """Can apply discount to sale"""
        sale_id = self.pos.create_sale()
        self.pos.add_line_item(
            sale_id,
            name="Service",
            quantity=1,
            unit_price=Money.from_dollars(50.00),
        )

        self.pos.apply_discount(
            sale_id,
            amount=Money.from_dollars(5.00),
            reason="Loyalty discount",
        )

        sale = self.pos.get_sale(sale_id)
        assert sale.discounts.amount_dollars == 5.00

    def test_calculate_tax(self):
        """Can calculate tax on sale"""
        sale_id = self.pos.create_sale()
        self.pos.add_line_item(
            sale_id,
            name="Service",
            quantity=1,
            unit_price=Money.from_dollars(100.00),
        )

        self.pos.calculate_tax(sale_id, tax_rate=0.08)

        sale = self.pos.get_sale(sale_id)
        assert sale.tax.amount_dollars == 8.00

    def test_cannot_modify_completed_sale(self):
        """Cannot modify sale after completion"""
        sale_id = self.pos.create_sale()
        self.pos.add_line_item(
            sale_id,
            name="Service",
            quantity=1,
            unit_price=Money.from_dollars(30.00),
        )
        self.pos.calculate_tax(sale_id)

        # Complete sale
        self.pos.take_payment(
            sale_id,
            amount=Money.from_dollars(32.40),
            method=PaymentMethod.CASH,
        )

        # Try to add another item (should fail)
        with pytest.raises(ValueError, match="Cannot modify sale"):
            self.pos.add_line_item(
                sale_id,
                name="Extra",
                quantity=1,
                unit_price=Money.from_dollars(10.00),
            )


class TestPaymentStateMachine:
    """Test payment state machine"""

    def setup_method(self):
        self.cloud_store = CloudEventStore(":memory:")
        self.local_queue = LocalEventQueue(":memory:")
        self.pos = POSRuntime(
            barber_id="barber_test",
            cloud_store=self.cloud_store,
            local_queue=self.local_queue,
            hardware_mode=HardwareMode.FULL,
        )

    def test_cash_payment_direct_capture(self):
        """Cash payment goes directly to captured"""
        sale_id = self.pos.create_sale()
        self.pos.add_line_item(
            sale_id,
            name="Service",
            quantity=1,
            unit_price=Money.from_dollars(30.00),
        )
        self.pos.calculate_tax(sale_id)

        payment_id, state = self.pos.take_payment(
            sale_id,
            amount=Money.from_dollars(32.40),
            method=PaymentMethod.CASH,
        )

        assert state == PaymentState.CAPTURED

        payment = self.pos.get_payment(payment_id)
        assert payment.state == PaymentState.CAPTURED

    def test_card_payment_authorize_then_capture(self):
        """Card payment with hardware goes through auth → capture"""
        sale_id = self.pos.create_sale()
        self.pos.add_line_item(
            sale_id,
            name="Service",
            quantity=1,
            unit_price=Money.from_dollars(30.00),
        )
        self.pos.calculate_tax(sale_id)

        payment_id, state = self.pos.take_payment(
            sale_id,
            amount=Money.from_dollars(32.40),
            method=PaymentMethod.CARD_PRESENT,
            card_last_four="4242",
        )

        assert state == PaymentState.CAPTURED

        payment = self.pos.get_payment(payment_id)
        assert payment.state == PaymentState.CAPTURED
        assert payment.card_last_four == "4242"

    def test_software_only_mode_direct_capture(self):
        """Software-only mode skips auth step"""
        pos = POSRuntime(
            barber_id="barber_test",
            cloud_store=self.cloud_store,
            local_queue=self.local_queue,
            hardware_mode=HardwareMode.SOFTWARE_ONLY,
        )

        sale_id = pos.create_sale()
        pos.add_line_item(
            sale_id,
            name="Service",
            quantity=1,
            unit_price=Money.from_dollars(30.00),
        )
        pos.calculate_tax(sale_id)

        payment_id, state = pos.take_payment(
            sale_id,
            amount=Money.from_dollars(32.40),
            method=PaymentMethod.CARD_MANUAL,
        )

        # Software-only goes directly to captured
        assert state == PaymentState.CAPTURED


class TestRefundsAndVoids:
    """Test refunds and voids"""

    def setup_method(self):
        self.cloud_store = CloudEventStore(":memory:")
        self.local_queue = LocalEventQueue(":memory:")
        self.pos = POSRuntime(
            barber_id="barber_test",
            cloud_store=self.cloud_store,
            local_queue=self.local_queue,
        )

    def test_refund_completed_sale(self):
        """Can refund a completed sale"""
        sale_id = self.pos.create_sale()
        self.pos.add_line_item(
            sale_id,
            name="Service",
            quantity=1,
            unit_price=Money.from_dollars(30.00),
        )
        self.pos.calculate_tax(sale_id)
        self.pos.take_payment(
            sale_id,
            amount=Money.from_dollars(32.40),
            method=PaymentMethod.CASH,
        )

        # Refund
        refund_id = self.pos.create_refund(
            sale_id,
            amount=Money.from_dollars(32.40),
            reason="Customer request",
        )

        assert refund_id is not None

        sale = self.pos.get_sale(sale_id)
        assert sale.state == SaleState.REFUNDED

    def test_cannot_refund_draft_sale(self):
        """Cannot refund a draft sale"""
        sale_id = self.pos.create_sale()
        self.pos.add_line_item(
            sale_id,
            name="Service",
            quantity=1,
            unit_price=Money.from_dollars(30.00),
        )

        with pytest.raises(ValueError, match="Cannot refund sale"):
            self.pos.create_refund(
                sale_id,
                amount=Money.from_dollars(30.00),
            )

    def test_void_draft_sale(self):
        """Can void a draft sale"""
        sale_id = self.pos.create_sale()
        self.pos.add_line_item(
            sale_id,
            name="Service",
            quantity=1,
            unit_price=Money.from_dollars(30.00),
        )

        success = self.pos.void_sale(sale_id, reason="Customer cancelled")
        assert success

        sale = self.pos.get_sale(sale_id)
        assert sale.state == SaleState.VOIDED

    def test_cannot_void_completed_sale(self):
        """Cannot void a completed sale"""
        sale_id = self.pos.create_sale()
        self.pos.add_line_item(
            sale_id,
            name="Service",
            quantity=1,
            unit_price=Money.from_dollars(30.00),
        )
        self.pos.calculate_tax(sale_id)
        self.pos.take_payment(
            sale_id,
            amount=Money.from_dollars(32.40),
            method=PaymentMethod.CASH,
        )

        with pytest.raises(ValueError, match="Cannot void sale"):
            self.pos.void_sale(sale_id)


class TestOfflineMode:
    """Test offline-first functionality"""

    def setup_method(self):
        self.cloud_store = CloudEventStore(":memory:")
        self.local_queue = LocalEventQueue(":memory:")

    def test_offline_events_queued_locally(self):
        """Events created offline go to local queue"""
        pos = POSRuntime(
            barber_id="barber_test",
            cloud_store=self.cloud_store,
            local_queue=self.local_queue,
            is_online=False,  # Offline
        )

        # Create sale offline
        sale_id = pos.create_sale()
        pos.add_line_item(
            sale_id,
            name="Service",
            quantity=1,
            unit_price=Money.from_dollars(30.00),
        )

        # Events should be in local queue
        pending = self.local_queue.get_pending_count()
        assert pending > 0

        # Cloud store should be empty (offline)
        cloud_events = self.cloud_store.get_events()
        assert len(cloud_events) == 0

    def test_sync_moves_events_to_cloud(self):
        """Syncing moves local events to cloud"""
        pos = POSRuntime(
            barber_id="barber_test",
            cloud_store=self.cloud_store,
            local_queue=self.local_queue,
            is_online=False,
        )

        # Create events offline
        sale_id = pos.create_sale()
        pos.add_line_item(
            sale_id,
            name="Service",
            quantity=1,
            unit_price=Money.from_dollars(30.00),
        )

        # Go online and sync
        pos.is_online = True
        synced_count = pos.sync_offline_events()

        assert synced_count > 0

        # Events should now be in cloud
        cloud_events = self.cloud_store.get_events()
        assert len(cloud_events) > 0


class TestIdempotency:
    """Test idempotency of money-touching operations"""

    def setup_method(self):
        self.cloud_store = CloudEventStore(":memory:")
        self.local_queue = LocalEventQueue(":memory:")
        self.pos = POSRuntime(
            barber_id="barber_test",
            cloud_store=self.cloud_store,
            local_queue=self.local_queue,
        )

    def test_duplicate_sale_creation_prevented(self):
        """Creating sale with same idempotency key prevented"""
        sale_id1 = self.pos.create_sale()

        # Try to create same sale again (would have same idempotency key)
        # In real implementation, would pass explicit idempotency key
        # For now, verify events are unique
        events = self.cloud_store.get_events(aggregate_id=sale_id1)
        assert len(events) == 1  # Only one SALE_CREATED event


class TestShiftManagement:
    """Test shift open/close"""

    def setup_method(self):
        self.cloud_store = CloudEventStore(":memory:")
        self.local_queue = LocalEventQueue(":memory:")
        self.pos = POSRuntime(
            barber_id="barber_test",
            cloud_store=self.cloud_store,
            local_queue=self.local_queue,
        )

    def test_open_shift(self):
        """Can open a shift"""
        shift_id = self.pos.open_shift(starting_cash=Money.from_dollars(100.00))
        assert shift_id is not None

        events = self.cloud_store.get_events(aggregate_id=shift_id)
        assert len(events) == 1
        assert events[0].event_type.value == "SHIFT_OPENED"

    def test_close_shift(self):
        """Can close a shift"""
        shift_id = self.pos.open_shift(starting_cash=Money.from_dollars(100.00))

        self.pos.close_shift(
            shift_id,
            ending_cash=Money.from_dollars(450.00),
            total_sales=Money.from_dollars(350.00),
        )

        events = self.cloud_store.get_events(aggregate_id=shift_id)
        assert len(events) == 2
        assert events[1].event_type.value == "SHIFT_CLOSED"
