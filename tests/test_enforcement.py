"""
Tests for Enforcement Middleware
"""

import pytest

from event_store import CloudEventStore, Money
from entitlement_ledger import EntitlementLedger, CurrentEntitlement
from procurement_service import ProcurementService
from enforcement_middleware import EnforcementMiddleware


class TestOrderEnforcement:
    """Test procurement order enforcement"""

    def setup_method(self):
        self.cloud_store = CloudEventStore(":memory:")
        self.entitlement_ledger = EntitlementLedger(":memory:")
        self.procurement_service = ProcurementService(self.cloud_store)
        self.enforcement = EnforcementMiddleware(
            self.entitlement_ledger,
            self.procurement_service,
        )

        self.barber_id = "barber_123"

    def test_no_entitlement_blocks_order(self):
        """Barber with no entitlement cannot place order"""
        result = self.enforcement.can_place_order(
            self.barber_id,
            Money(amount_minor=10000),  # $100
        )

        assert not result.allowed
        assert "No entitlement found" in result.reason
        assert result.blocked_by == "access"

    def test_level_0_blocks_store_access(self):
        """Level 0 barber cannot access store"""
        # Manually insert Level 0 entitlement
        import json
        import sqlite3
        from event_store import utc_now

        with sqlite3.connect(self.entitlement_ledger.db_path) as conn:
            conn.execute("""
                INSERT INTO entitlements
                (barber_id, tier, score, entitlement_type, access_list, caps,
                 granted_at, last_updated, is_active, blocked_reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.barber_id,
                "Level 0",
                45,
                "POS_ONLY",
                json.dumps(["POS_ONLY"]),
                json.dumps({}),
                utc_now(),
                utc_now(),
                1,
                json.dumps([]),
            ))
            conn.commit()

        result = self.enforcement.can_place_order(
            self.barber_id,
            Money(amount_minor=10000),
        )

        assert not result.allowed
        assert "Store access not available" in result.reason
        assert result.blocked_by == "access"

    def test_level_1_allows_order_under_cap(self):
        """Level 1 barber can place order under $500 cap"""
        # Insert Level 1 entitlement
        import json
        import sqlite3
        from event_store import utc_now

        with sqlite3.connect(self.entitlement_ledger.db_path) as conn:
            conn.execute("""
                INSERT INTO entitlements
                (barber_id, tier, score, entitlement_type, access_list, caps,
                 granted_at, last_updated, is_active, blocked_reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.barber_id,
                "Level 1",
                55,
                "STORE_ACCESS",
                json.dumps(["POS", "STORE_PREPAID"]),
                json.dumps({"max_order_value": 50000}),  # $500
                utc_now(),
                utc_now(),
                1,
                json.dumps([]),
            ))
            conn.commit()

        result = self.enforcement.can_place_order(
            self.barber_id,
            Money(amount_minor=40000),  # $400
        )

        assert result.allowed
        assert result.blocked_by is None

    def test_level_1_blocks_order_over_cap(self):
        """Level 1 barber cannot place order over $500 cap"""
        # Insert Level 1 entitlement
        import json
        import sqlite3
        from event_store import utc_now

        with sqlite3.connect(self.entitlement_ledger.db_path) as conn:
            conn.execute("""
                INSERT INTO entitlements
                (barber_id, tier, score, entitlement_type, access_list, caps,
                 granted_at, last_updated, is_active, blocked_reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.barber_id,
                "Level 1",
                55,
                "STORE_ACCESS",
                json.dumps(["POS", "STORE_PREPAID"]),
                json.dumps({"max_order_value": 50000}),  # $500
                utc_now(),
                utc_now(),
                1,
                json.dumps([]),
            ))
            conn.commit()

        result = self.enforcement.can_place_order(
            self.barber_id,
            Money(amount_minor=60000),  # $600, over cap
        )

        assert not result.allowed
        assert "exceeds your cap" in result.reason
        assert result.blocked_by == "cap"

    def test_inactive_entitlement_blocks(self):
        """Inactive entitlement blocks access"""
        import json
        import sqlite3
        from event_store import utc_now

        with sqlite3.connect(self.entitlement_ledger.db_path) as conn:
            conn.execute("""
                INSERT INTO entitlements
                (barber_id, tier, score, entitlement_type, access_list, caps,
                 granted_at, last_updated, is_active, blocked_reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.barber_id,
                "Level 1",
                55,
                "STORE_ACCESS",
                json.dumps(["POS", "STORE_PREPAID"]),
                json.dumps({"max_order_value": 50000}),
                utc_now(),
                utc_now(),
                0,  # Inactive
                json.dumps(["Excessive refund rate"]),
            ))
            conn.commit()

        result = self.enforcement.can_place_order(
            self.barber_id,
            Money(amount_minor=10000),
        )

        assert not result.allowed
        assert "Store access locked" in result.reason
        assert result.blocked_by == "blocked"


class TestTermsEnforcement:
    """Test net terms (credit) enforcement"""

    def setup_method(self):
        self.cloud_store = CloudEventStore(":memory:")
        self.entitlement_ledger = EntitlementLedger(":memory:")
        self.procurement_service = ProcurementService(self.cloud_store)
        self.enforcement = EnforcementMiddleware(
            self.entitlement_ledger,
            self.procurement_service,
        )

        self.barber_id = "barber_123"

    def test_level_2_cannot_use_terms(self):
        """Level 2 barber cannot use net terms"""
        import json
        import sqlite3
        from event_store import utc_now

        with sqlite3.connect(self.entitlement_ledger.db_path) as conn:
            conn.execute("""
                INSERT INTO entitlements
                (barber_id, tier, score, entitlement_type, access_list, caps,
                 granted_at, last_updated, is_active, blocked_reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.barber_id,
                "Level 2",
                75,
                "STORE_ACCESS",
                json.dumps(["POS", "STORE_PREPAID", "BETTER_PRICING"]),
                json.dumps({"max_order_value": 150000}),
                utc_now(),
                utc_now(),
                1,
                json.dumps([]),
            ))
            conn.commit()

        result = self.enforcement.can_use_terms(
            self.barber_id,
            Money(amount_minor=50000),  # $500 invoice
            Money(amount_minor=0),  # No outstanding balance
        )

        assert not result.allowed
        assert "Net terms not available" in result.reason
        assert "Level 3" in result.reason

    def test_level_3_can_use_terms_under_cap(self):
        """Level 3 barber can use terms under cap"""
        import json
        import sqlite3
        from event_store import utc_now

        with sqlite3.connect(self.entitlement_ledger.db_path) as conn:
            conn.execute("""
                INSERT INTO entitlements
                (barber_id, tier, score, entitlement_type, access_list, caps,
                 granted_at, last_updated, is_active, blocked_reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.barber_id,
                "Level 3",
                88,
                "STORE_ACCESS",
                json.dumps(["POS", "STORE_PREPAID", "BETTER_PRICING", "TERMS_ELIGIBLE"]),
                json.dumps({
                    "max_order_value": 300000,
                    "max_terms_outstanding": 100000,  # $1,000
                }),
                utc_now(),
                utc_now(),
                1,
                json.dumps([]),
            ))
            conn.commit()

        result = self.enforcement.can_use_terms(
            self.barber_id,
            Money(amount_minor=50000),  # $500 invoice
            Money(amount_minor=0),  # No outstanding balance
        )

        assert result.allowed

    def test_level_3_blocks_terms_over_cap(self):
        """Level 3 barber blocked if terms would exceed cap"""
        import json
        import sqlite3
        from event_store import utc_now

        with sqlite3.connect(self.entitlement_ledger.db_path) as conn:
            conn.execute("""
                INSERT INTO entitlements
                (barber_id, tier, score, entitlement_type, access_list, caps,
                 granted_at, last_updated, is_active, blocked_reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.barber_id,
                "Level 3",
                88,
                "STORE_ACCESS",
                json.dumps(["POS", "STORE_PREPAID", "BETTER_PRICING", "TERMS_ELIGIBLE"]),
                json.dumps({
                    "max_order_value": 300000,
                    "max_terms_outstanding": 100000,  # $1,000
                }),
                utc_now(),
                utc_now(),
                1,
                json.dumps([]),
            ))
            conn.commit()

        result = self.enforcement.can_use_terms(
            self.barber_id,
            Money(amount_minor=60000),  # $600 invoice
            Money(amount_minor=50000),  # $500 already outstanding = $1,100 total
        )

        assert not result.allowed
        assert "balance limit exceeded" in result.reason


class TestPricingAndSLA:
    """Test pricing tier and SLA determination"""

    def setup_method(self):
        self.cloud_store = CloudEventStore(":memory:")
        self.entitlement_ledger = EntitlementLedger(":memory:")
        self.procurement_service = ProcurementService(self.cloud_store)
        self.enforcement = EnforcementMiddleware(
            self.entitlement_ledger,
            self.procurement_service,
        )

        self.barber_id = "barber_123"

    def test_level_1_standard_pricing(self):
        """Level 1 gets standard pricing"""
        import json
        import sqlite3
        from event_store import utc_now

        with sqlite3.connect(self.entitlement_ledger.db_path) as conn:
            conn.execute("""
                INSERT INTO entitlements
                (barber_id, tier, score, entitlement_type, access_list, caps,
                 granted_at, last_updated, is_active, blocked_reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.barber_id,
                "Level 1",
                55,
                "STORE_ACCESS",
                json.dumps(["POS", "STORE_PREPAID"]),
                json.dumps({"max_order_value": 50000}),
                utc_now(),
                utc_now(),
                1,
                json.dumps([]),
            ))
            conn.commit()

        pricing = self.enforcement.get_pricing_tier(self.barber_id)
        assert pricing == "STANDARD"

    def test_level_2_better_pricing(self):
        """Level 2 gets better pricing"""
        import json
        import sqlite3
        from event_store import utc_now

        with sqlite3.connect(self.entitlement_ledger.db_path) as conn:
            conn.execute("""
                INSERT INTO entitlements
                (barber_id, tier, score, entitlement_type, access_list, caps,
                 granted_at, last_updated, is_active, blocked_reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.barber_id,
                "Level 2",
                75,
                "STORE_ACCESS",
                json.dumps(["POS", "STORE_PREPAID", "BETTER_PRICING"]),
                json.dumps({"max_order_value": 150000}),
                utc_now(),
                utc_now(),
                1,
                json.dumps([]),
            ))
            conn.commit()

        pricing = self.enforcement.get_pricing_tier(self.barber_id)
        assert pricing == "BETTER"

    def test_level_4_priority_fulfillment(self):
        """Level 4 gets priority fulfillment"""
        import json
        import sqlite3
        from event_store import utc_now

        with sqlite3.connect(self.entitlement_ledger.db_path) as conn:
            conn.execute("""
                INSERT INTO entitlements
                (barber_id, tier, score, entitlement_type, access_list, caps,
                 granted_at, last_updated, is_active, blocked_reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.barber_id,
                "Level 4",
                98,
                "STORE_ACCESS",
                json.dumps(["POS", "STORE_PREPAID", "BEST_PRICING", "TERMS_MATURE", "PRIORITY_FULFILLMENT"]),
                json.dumps({
                    "max_order_value": 999999,
                    "max_terms_outstanding": 500000,
                }),
                utc_now(),
                utc_now(),
                1,
                json.dumps([]),
            ))
            conn.commit()

        sla = self.enforcement.get_fulfillment_sla(self.barber_id)
        assert sla == "PRIORITY"


class TestEntitlementSummary:
    """Test entitlement summary for UI"""

    def setup_method(self):
        self.cloud_store = CloudEventStore(":memory:")
        self.entitlement_ledger = EntitlementLedger(":memory:")
        self.procurement_service = ProcurementService(self.cloud_store)
        self.enforcement = EnforcementMiddleware(
            self.entitlement_ledger,
            self.procurement_service,
        )

        self.barber_id = "barber_123"

    def test_summary_for_level_2_barber(self):
        """Summary shows correct info for Level 2 barber"""
        import json
        import sqlite3
        from event_store import utc_now

        with sqlite3.connect(self.entitlement_ledger.db_path) as conn:
            conn.execute("""
                INSERT INTO entitlements
                (barber_id, tier, score, entitlement_type, access_list, caps,
                 granted_at, last_updated, is_active, blocked_reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.barber_id,
                "Level 2",
                72,
                "STORE_ACCESS",
                json.dumps(["POS", "STORE_PREPAID", "BETTER_PRICING"]),
                json.dumps({"max_order_value": 150000}),
                utc_now(),
                utc_now(),
                1,
                json.dumps([]),
            ))
            conn.commit()

        summary = self.enforcement.get_entitlement_summary(self.barber_id)

        assert summary["tier"] == "Level 2"
        assert summary["score"] == 72
        assert summary["store_access"] is True
        assert summary["terms_access"] is False
        assert summary["next_tier"] == "Level 3"
        assert summary["points_to_next"] == 13  # 85 - 72

    def test_unlock_requirements(self):
        """Get unlock requirements for next tier"""
        import json
        import sqlite3
        from event_store import utc_now

        with sqlite3.connect(self.entitlement_ledger.db_path) as conn:
            conn.execute("""
                INSERT INTO entitlements
                (barber_id, tier, score, entitlement_type, access_list, caps,
                 granted_at, last_updated, is_active, blocked_reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.barber_id,
                "Level 1",
                55,
                "STORE_ACCESS",
                json.dumps(["POS", "STORE_PREPAID"]),
                json.dumps({"max_order_value": 50000}),
                utc_now(),
                utc_now(),
                1,
                json.dumps([]),
            ))
            conn.commit()

        requirements = self.enforcement.get_unlock_requirements(self.barber_id, "Level 3")

        assert requirements["desired_tier"] == "Level 3"
        assert requirements["required_score"] == 85
        assert requirements["current_score"] == 55
        assert requirements["points_needed"] == 30
        assert not requirements["is_unlocked"]
        assert "Net-30 terms" in str(requirements["benefits"])
