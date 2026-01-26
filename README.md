# POS → BarberScore → Procurement Integration

Complete event-sourced system integrating Square-like POS with BarberScore eligibility engine and tier-based procurement access.

---

## 👀 Want to View It Right Now?

**Two options:**
- **[View Locally](VIEW.md)** - Run on your computer in 5 minutes
- **[Deploy Online](DEPLOYMENT.md)** - Access from anywhere in 30 minutes

**Quick guides:**
- **[Local Setup](LOCAL_SETUP.md)** - Detailed local development guide
- **[Quick Start](QUICK_START.md)** - API-only setup
- **[Deployment](DEPLOYMENT.md)** - Production deployment to Render + Vercel

---

## 🎯 Overview

This system creates a flywheel where:
1. **Barbers use POS** → generates transaction events
2. **BarberScore calculates eligibility** → determines tier based on quality metrics + anti-gaming
3. **Entitlements gate procurement** → tier-based store access, pricing, and terms
4. **Warehouse fulfills orders** → SLA based on tier
5. **Better service drives POS usage** → flywheel continues

## 🏗️ Architecture

### Event-Sourced Foundation

All state changes are captured as immutable events in append-only ledgers:

```
POS Transactions → CloudEventStore (immutable)
                       ↓
                 EligibilityEngine (consumes events)
                       ↓
                 EntitlementLedger (materialized view)
                       ↓
                 EnforcementMiddleware (gates access)
```

### Key Components

| Component | Purpose | Layer |
|-----------|---------|-------|
| `event_store.py` | Immutable event ledger + offline queue | 10 |
| `square_like_pos.py` | POS runtime with payment state machine | 9 |
| `eligibility_engine.py` | BarberScore calculation + anti-gaming | 10a |
| `entitlement_ledger.py` | Fast queryable entitlement state | 10a |
| `enforcement_middleware.py` | Procurement gating logic | 8 |
| `procurement_service.py` | Warehouse orders + fulfillment | 8 |

## 🚀 Quick Start

### Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt
```

### Basic Usage

```python
from event_store import CloudEventStore, LocalEventQueue, Money
from square_like_pos import POSRuntime, PaymentMethod
from eligibility_engine import EligibilityEngine
from entitlement_ledger import EntitlementLedger
from enforcement_middleware import EnforcementMiddleware
from procurement_service import ProcurementService

# Initialize system
cloud_store = CloudEventStore("pos_events.db")
local_queue = LocalEventQueue("local_queue.db")
entitlement_ledger = EntitlementLedger("entitlements.db")
entitlement_ledger.subscribe_to_events(cloud_store)

# Use POS
pos = POSRuntime(
    barber_id="barber_alice",
    cloud_store=cloud_store,
    local_queue=local_queue,
)

# Create sale
sale_id = pos.create_sale()
pos.add_line_item(sale_id, "Haircut", 1, Money.from_dollars(35.00))
pos.calculate_tax(sale_id)
pos.take_payment(sale_id, Money.from_dollars(37.80), PaymentMethod.CARD_PRESENT)

# Calculate BarberScore
eligibility_engine = EligibilityEngine(cloud_store)
eligibility_engine.update_and_emit_entitlements("barber_alice")

# Check procurement access
procurement = ProcurementService(cloud_store)
enforcement = EnforcementMiddleware(entitlement_ledger, procurement)

result = enforcement.can_place_order("barber_alice", Money.from_dollars(400))
if result.allowed:
    order_id = procurement.create_order("barber_alice", line_items)
```

## 📊 BarberScore Tiers

| Tier | Score | Access | Caps |
|------|-------|--------|------|
| **Level 0** | 0-49 | POS only | None |
| **Level 1** | 50-69 | Store (prepaid) | $500/order |
| **Level 2** | 70-84 | Better pricing (5-10%) | $1,500/order |
| **Level 3** | 85-94 | Net-30 terms | $3,000/order, $1,000 credit |
| **Level 4** | 95-100 | Best pricing (15%), priority SLA | $10,000/order, $5,000 credit |

### How Score is Calculated

**Positive Factors:**
- ✅ Qualified transactions (above $5, not refunded within 7 days)
- ✅ Revenue consistency
- ✅ Active days
- ✅ Average ticket size
- ✅ Payment method diversity

**Negative Factors:**
- ❌ Refund rate
- ❌ Void rate
- ❌ Chargeback rate
- ❌ Gaming pattern flags

**Time Decay:**
- Recent 60 days weighted 70%
- Historical weighted 30%

## 🛡️ Anti-Gaming Protections

### Pattern Detection

The system detects and penalizes gaming behaviors:

| Pattern | Detection | Impact |
|---------|-----------|--------|
| **Identical amounts** | 10+ transactions, all same amount | -5 points, flag |
| **Excessive refunds** | >20% refund rate | -5 points, flag |
| **Refund clusters** | 5+ refunds in 24hr window | -5 points, flag |
| **Void spike** | >15% void rate | -5 points, flag |
| **Round number bias** | >80% round amounts ($10, $20, etc) | -5 points, flag |
| **Rapid sequence** | 10+ transactions in 5 minutes | -5 points, flag |
| **Late night spike** | >30% transactions 1-5 AM | -5 points, flag |
| **Manual entry bias** | >70% manual card entry | -5 points, flag |

### Hard Gates (P0 Tripwires)

These immediately block all entitlements:

- ❗ **Excessive refund rate** (>25%) → Score = 0, entitlements revoked
- ❗ **Chargeback spike** (>5%) → Score = 0, account frozen
- ❗ **Insufficient history** (<10 qualified transactions OR <7 active days) → Level 0 locked

## 🔒 Enforcement Logic

### Procurement Order Gating

```python
# Check before order creation
result = enforcement.can_place_order(barber_id, order_value)

if not result.allowed:
    print(f"Blocked: {result.reason}")
    print(f"Blocked by: {result.blocked_by}")  # "access", "cap", or "blocked"
```

**Enforcement Checks:**
1. ✅ Entitlement exists and is active
2. ✅ Has "STORE_PREPAID" access
3. ✅ Order value under tier cap

### Net Terms (Credit) Gating

```python
result = enforcement.can_use_terms(
    barber_id,
    invoice_amount,
    outstanding_balance,
)
```

**Enforcement Checks:**
1. ✅ Has "TERMS_ELIGIBLE" or "TERMS_MATURE" access
2. ✅ New balance would not exceed credit limit

## 📦 Event Types

### POS Events
- `SALE_CREATED` - New sale started
- `LINE_ITEM_ADDED` - Item added to sale
- `DISCOUNT_APPLIED` - Discount applied
- `TAX_CALCULATED` - Tax calculated
- `PAYMENT_INITIATED` - Payment started
- `PAYMENT_AUTHORIZED` - Card authorized
- `PAYMENT_CAPTURED` - Payment settled
- `PAYMENT_DECLINED` - Payment declined
- `REFUND_CREATED` - Refund issued
- `VOID_APPLIED` - Sale voided
- `SHIFT_OPENED` / `SHIFT_CLOSED` - Shift management

### Procurement Events
- `PROCUREMENT_ORDER_CREATED` - Order placed
- `PROCUREMENT_ORDER_PAID` - Order paid
- `PROCUREMENT_ORDER_CANCELED` - Order canceled
- `PICKLIST_CREATED` - Warehouse picklist created
- `ORDER_PICKED` - Items picked
- `ORDER_PACKED` - Order packed
- `SHIPMENT_DISPATCHED` - Order shipped
- `DELIVERY_CONFIRMED` - Delivery confirmed
- `RETURN_RECEIVED` - Return processed

### Entitlement Events
- `BARBERSCORE_UPDATED` - Score recalculated
- `ENTITLEMENT_GRANTED` - Access granted
- `ENTITLEMENT_REVOKED` - Access revoked
- `RISK_FLAG_RAISED` - Gaming pattern detected

## 🧪 Testing

Run the comprehensive test suite:

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_eligibility.py -v

# Run with coverage
pytest --cov=. --cov-report=html tests/

# Run integration tests only
pytest tests/test_integration.py -v
```

### Test Coverage

- ✅ **Qualified transaction logic** - minimum amounts, refund quarantine
- ✅ **Anti-gaming detection** - all 8 pattern types
- ✅ **Hard gates** - P0 tripwires
- ✅ **Score calculation** - tier progression
- ✅ **Enforcement** - order caps, terms limits
- ✅ **End-to-end flow** - POS → score → procurement
- ✅ **Offline mode** - local queue sync
- ✅ **Payment state machine** - auth → capture flow

## 🎨 BarberScore UI

Open `BarberScore_2.html` in a browser to view the dashboard:

**Features:**
- 📊 Real-time score display with tier badge
- 📈 Progress bar to next tier
- 📉 Key metrics (qualified transactions, revenue, refund rate)
- 🔓 Access & benefits overview
- 🛒 Procurement store (locked/unlocked based on tier)
- ⚠️ Gaming flags display
- 🚀 Unlock requirements guide

**Integration:**
Replace the `mockAPI` in the HTML with real API endpoints:

```javascript
const api = {
    async getEntitlementSummary(barberId) {
        const response = await fetch(`/api/entitlements/${barberId}`);
        return response.json();
    },
    // ... more endpoints
};
```

## 📝 Configuration

All scoring rules, tier thresholds, and anti-gaming patterns are configurable via JSON:

### `config/score_rules.json`
- Qualified transaction rules
- Metric weights
- Time decay settings
- Hard gate thresholds

### `config/entitlement_levels.json`
- Tier definitions (Level 0-4)
- Access lists per tier
- Caps per tier
- Benefits descriptions

### `config/anti_gaming_rules.json`
- Pattern detection rules
- Severity levels
- Response actions

## 🔄 Offline-First Architecture

The system works seamlessly offline:

1. **Offline mode** - Events queued in `LocalEventQueue` (SQLite)
2. **Network restoration** - Events sync to `CloudEventStore`
3. **Idempotency** - Duplicate events automatically deduplicated
4. **Score calculation** - Works on synced events after reconnection

```python
# Start offline
pos = POSRuntime(barber_id="alice", is_online=False, ...)

# Create transactions (queued locally)
sale_id = pos.create_sale()
# ... add items, take payment

# Come back online
pos.is_online = True
synced_count = pos.sync_offline_events()
print(f"Synced {synced_count} events")

# Calculate score from synced events
eligibility_engine.update_and_emit_entitlements("alice")
```

## 🏭 Production Deployment

### Database Setup

**Development:**
```python
cloud_store = CloudEventStore(":memory:")  # In-memory
```

**Production:**
```python
cloud_store = CloudEventStore("postgres://user:pass@host/db")  # PostgreSQL
```

### Environment Variables

```bash
# .env file
DATABASE_URL=postgresql://user:pass@host/db
REDIS_URL=redis://localhost:6379
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-key
```

### Scaling Considerations

- **Event Store** - Partition by barber_id for horizontal scaling
- **Entitlement Ledger** - Cache frequently accessed entitlements (Redis)
- **Score Calculation** - Run as async background jobs (Celery/RQ)
- **API Layer** - FastAPI for REST endpoints, rate limiting per tier

## 📚 API Reference

### Core Classes

#### `POSRuntime`
```python
pos = POSRuntime(barber_id, cloud_store, local_queue, hardware_mode, is_online)
pos.create_sale(metadata) -> sale_id
pos.add_line_item(sale_id, name, quantity, unit_price) -> item_id
pos.take_payment(sale_id, amount, method) -> (payment_id, state)
pos.create_refund(sale_id, amount, reason) -> refund_id
pos.void_sale(sale_id, reason) -> bool
```

#### `EligibilityEngine`
```python
engine = EligibilityEngine(cloud_store, config_dir)
barberscore = engine.calculate_barberscore(barber_id)
engine.update_and_emit_entitlements(barber_id)
```

#### `EnforcementMiddleware`
```python
enforcement = EnforcementMiddleware(entitlement_ledger, procurement_service)
result = enforcement.can_place_order(barber_id, order_value)
result = enforcement.can_use_terms(barber_id, invoice_amount, outstanding_balance)
summary = enforcement.get_entitlement_summary(barber_id)
```

#### `ProcurementService`
```python
procurement = ProcurementService(cloud_store)
order_id = procurement.create_order(barber_id, line_items, sla)
procurement.pay_order(order_id, payment_method, payment_id)
procurement.dispatch_shipment(order_id, tracking_number, carrier)
```

## 🤝 Contributing

See `docs/ARCHITECTURE.md` for detailed architecture documentation.

## 📄 License

Proprietary - All rights reserved
