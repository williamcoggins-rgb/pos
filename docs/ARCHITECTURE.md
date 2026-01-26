# Architecture Documentation

## System Overview

The POS → BarberScore → Procurement integration is an event-sourced system where all state changes flow through immutable event ledgers. This architecture ensures auditability, enables replay/reconstruction, and provides natural integration points between components.

## Architectural Principles

### 1. Event Sourcing

**All state is derived from events, never directly mutated.**

```
Events (immutable) → Aggregates (reconstructed) → Projections (materialized views)
```

Benefits:
- Complete audit trail
- Time travel / debugging
- Easy to add new projections
- Natural distributed system boundaries

### 2. Offline-First

**POS must work without internet connectivity.**

```
Local SQLite Queue → Sync when online → Cloud PostgreSQL Store
```

Implementation:
- `LocalEventQueue` buffers events when offline
- Idempotency keys prevent duplicates on sync
- Score calculation happens after sync

### 3. Anti-Gaming by Design

**Eligibility cannot be manipulated through raw transaction count.**

Protections:
- Qualified transaction filters (minimum amount, refund quarantine)
- Pattern detection (8 distinct gaming patterns)
- Hard gates (P0 tripwires)
- Time decay (recent activity weighted more)

### 4. Entitlement-Based Access

**All procurement actions gated by derived entitlements, never user-editable.**

```
POS Events → BarberScore → Entitlements → Enforcement Gates
```

No backdoor access - even internal tools must respect entitlements.

## Layer Architecture

```
┌──────────────────────────────────────────────────────┐
│  Layer 14: Financing Adapter (Future)                │
│  - Terms/lending integration                         │
└──────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────┐
│  Layer 10a: ELIGIBILITY_BARBERSCORE                  │
│  - eligibility_engine.py                             │
│  - entitlement_ledger.py                             │
│  - Anti-gaming logic                                 │
└──────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────┐
│  Layer 10: Event Store                               │
│  - event_store.py (CloudEventStore, LocalEventQueue) │
│  - Immutable append-only ledger                      │
└──────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────┐
│  Layer 9: POS Runtime                                │
│  - square_like_pos.py                                │
│  - Payment state machine                             │
└──────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────┐
│  Layer 8: Procurement & Warehouse                    │
│  - procurement_service.py                            │
│  - enforcement_middleware.py                         │
└──────────────────────────────────────────────────────┘
```

### Layer Dependencies

**Rule:** Higher layers can depend on lower layers, never reverse.

- Layer 14 (Financing) can read Layer 10a (Eligibility) ✅
- Layer 8 (Procurement) can read Layer 10a (Eligibility) ✅
- Layer 10a (Eligibility) CANNOT write to Layer 9 (POS) ❌

## Data Flow

### 1. POS Transaction Flow

```
Barber → POS UI → POSRuntime → CloudEventStore
                                     ↓
                              [PAYMENT_CAPTURED]
                                     ↓
                         EligibilityEngine (listens)
```

Events emitted:
1. `SALE_CREATED` (sale_id, barber_id)
2. `LINE_ITEM_ADDED` (item_id, name, quantity, unit_price)
3. `TAX_CALCULATED` (tax amount)
4. `PAYMENT_INITIATED` (payment_id, amount, method)
5. `PAYMENT_AUTHORIZED` (payment_id, authorized_at)
6. `PAYMENT_CAPTURED` (payment_id, captured_at)

### 2. BarberScore Calculation Flow

```
CloudEventStore → EligibilityEngine.calculate_barberscore()
                         ↓
                  [Fetch all barber events]
                         ↓
                  [Calculate metrics]
                         ↓
                  [Detect gaming patterns]
                         ↓
                  [Apply hard gates]
                         ↓
                  [Calculate weighted score]
                         ↓
                  [Determine tier]
                         ↓
                  Emit BARBERSCORE_UPDATED
                         ↓
                  Emit ENTITLEMENT_GRANTED/REVOKED
```

### 3. Procurement Order Flow

```
Barber → Store UI → EnforcementMiddleware.can_place_order()
                            ↓
                     [Check entitlement]
                     [Check caps]
                            ↓
                         {allowed?}
                            ↓
                  ProcurementService.create_order()
                            ↓
                  [PROCUREMENT_ORDER_CREATED]
                            ↓
                  [PROCUREMENT_ORDER_PAID]
                            ↓
                  [PICKLIST_CREATED]
                            ↓
                  [ORDER_PICKED]
                            ↓
                  [ORDER_PACKED]
                            ↓
                  [SHIPMENT_DISPATCHED]
                            ↓
                  [DELIVERY_CONFIRMED]
```

## State Machines

### Payment State Machine

```
        INITIATED
           ↓
    [authorize card]
           ↓
       AUTHORIZED
           ↓
     [settle/capture]
           ↓
       CAPTURED
```

**Transitions:**
- `INITIATED` → `AUTHORIZED` (card auth succeeds)
- `INITIATED` → `DECLINED` (card auth fails)
- `AUTHORIZED` → `CAPTURED` (settlement succeeds)
- `AUTHORIZED` → `FAILED` (settlement fails)
- `INITIATED` → `CAPTURED` (cash, or software-only mode)

**Immutability Constraint:** Once `CAPTURED`, payment cannot be modified (only refunded via new event).

### Sale State Machine

```
   DRAFT → COMPLETED → REFUNDED
     ↓
   VOIDED
```

**Transitions:**
- `DRAFT` → `COMPLETED` (payment captured)
- `DRAFT` → `VOIDED` (sale cancelled before payment)
- `COMPLETED` → `REFUNDED` (refund issued)

**Immutability Constraint:** Cannot modify `COMPLETED` or `REFUNDED` sales.

### Procurement Order State Machine

```
CREATED → PAID → PICKING → PICKED → PACKED → SHIPPED → DELIVERED
   ↓
CANCELED
```

## Qualified Transaction Logic

A transaction is "qualified" for BarberScore if:

```python
def is_qualified(payment_event, all_events):
    # 1. Must be settled
    if payment_event.type != PAYMENT_CAPTURED:
        return False

    # 2. Minimum amount ($5)
    if payment_event.amount < 500:  # cents
        return False

    # 3. Not refunded within 7 days
    refund_events = find_refunds_for_sale(payment_event.sale_id)
    for refund in refund_events:
        if (refund.created_at - payment_event.created_at) < 7 days:
            return False

    return True
```

**Why these rules?**
- Minimum amount prevents micro-swipe gaming
- Refund quarantine prevents buy-refund loops
- Settlement required prevents auth-only gaming

## Anti-Gaming Pattern Detection

### Pattern: Identical Amounts

**Detection:**
```python
amounts = [event.amount for event in payment_events]
if len(set(amounts)) == 1 and len(amounts) > 10:
    flag = "IDENTICAL_AMOUNTS_REPEATED"
```

**Why it matters:** Legitimate businesses have varied transaction amounts. Identical amounts suggest artificial activity.

### Pattern: Excessive Refunds

**Detection:**
```python
refund_rate = refund_count / payment_count
if refund_rate > 0.20:  # 20%
    flag = "EXCESSIVE_REFUND_RATE"
```

**Why it matters:** High refund rates indicate either gaming or problematic business practices.

### Pattern: Refund Clusters

**Detection:**
```python
for refund in refunds:
    nearby_refunds = count_within_24_hours(refund)
    if nearby_refunds >= 5:
        flag = "REFUND_CLUSTER_DETECTED"
```

**Why it matters:** Multiple refunds in short timespan suggests coordinated gaming.

## Score Calculation Formula

```python
score = BASE_SCORE  # 50

# Positive contributions
score += (qualified_transactions / 100) * 100 * WEIGHT_TX        # 0.25
score += (revenue / 10000) * 100 * WEIGHT_REVENUE                # 0.20
score += (active_days / 90) * 100 * WEIGHT_ACTIVE                # 0.15
score += (avg_ticket / 100) * 100 * WEIGHT_AVG_TICKET            # 0.10
score += (payment_methods / 4) * 100 * WEIGHT_DIVERSITY          # 0.05

# Negative contributions
score += refund_rate * 100 * WEIGHT_REFUND                       # -0.15
score += void_rate * 100 * WEIGHT_VOID                           # -0.10
score += chargeback_rate * 100 * WEIGHT_CHARGEBACK               # -0.20

# Flag penalties
score -= len(flags) * 5

# Clamp to [0, 100]
score = max(0, min(100, score))
```

**Time Decay:**
```python
recent_score = calculate_score(events_last_60_days)
historical_score = calculate_score(all_events)

final_score = (recent_score * 0.70) + (historical_score * 0.30)
```

## Entitlement Enforcement

### Order Placement

```python
def can_place_order(barber_id, order_value):
    entitlement = ledger.get_entitlement(barber_id)

    # Gate 1: Entitlement exists and active
    if not entitlement or not entitlement.is_active:
        return BLOCKED("No active entitlement")

    # Gate 2: Store access granted
    if "STORE_PREPAID" not in entitlement.access:
        return BLOCKED("Store access locked")

    # Gate 3: Under order cap
    cap = entitlement.caps.get("max_order_value")
    if order_value > cap:
        return BLOCKED(f"Exceeds cap of ${cap/100}")

    return ALLOWED
```

### Net Terms

```python
def can_use_terms(barber_id, invoice_amount, outstanding_balance):
    entitlement = ledger.get_entitlement(barber_id)

    # Gate 1: Terms access granted
    if "TERMS_ELIGIBLE" not in entitlement.access:
        return BLOCKED("Terms not available for tier")

    # Gate 2: Under credit limit
    cap = entitlement.caps.get("max_terms_outstanding")
    new_balance = outstanding_balance + invoice_amount
    if new_balance > cap:
        return BLOCKED(f"Would exceed credit limit")

    return ALLOWED
```

## Idempotency

All money-touching operations use idempotency keys:

```python
# Creating a sale
idempotency_key = f"sale_created_{sale_id}"
event = Event(..., idempotency_key=idempotency_key)

# CloudEventStore checks
if exists(idempotency_key):
    return False  # Duplicate, skip

# Otherwise append
append(event)
```

**Why?**
- Network retries don't duplicate charges
- Offline sync doesn't create duplicates
- Replaying events is safe

## Database Schema

### events table (CloudEventStore)

```sql
CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    payload TEXT NOT NULL,  -- JSON
    created_at TEXT NOT NULL,  -- ISO 8601
    idempotency_key TEXT UNIQUE,
    metadata TEXT,  -- JSON
    sequence INTEGER NOT NULL  -- Auto-increment
);

CREATE INDEX idx_aggregate ON events(aggregate_type, aggregate_id);
CREATE INDEX idx_event_type ON events(event_type);
CREATE INDEX idx_created_at ON events(created_at);
CREATE UNIQUE INDEX idx_idempotency ON events(idempotency_key)
    WHERE idempotency_key IS NOT NULL;
```

### entitlements table (EntitlementLedger)

```sql
CREATE TABLE entitlements (
    barber_id TEXT PRIMARY KEY,
    tier TEXT NOT NULL,
    score INTEGER NOT NULL,
    entitlement_type TEXT NOT NULL,
    access_list TEXT NOT NULL,  -- JSON array
    caps TEXT NOT NULL,  -- JSON object
    granted_at TEXT NOT NULL,
    last_updated TEXT NOT NULL,
    is_active INTEGER NOT NULL,  -- 0 or 1
    blocked_reasons TEXT  -- JSON array
);

CREATE INDEX idx_tier ON entitlements(tier);
CREATE INDEX idx_active ON entitlements(is_active);
```

## Security Considerations

### Threat Model

**Attack:** Gaming the score through artificial transactions
**Defense:** Anti-gaming pattern detection + hard gates

**Attack:** Bypassing caps through multiple accounts
**Defense:** Fraud detection (future), KYC verification

**Attack:** Refund abuse (buy → unlock → refund)
**Defense:** 7-day refund quarantine, refund rate hard gate

**Attack:** Direct database manipulation
**Defense:** Event sourcing (audit trail), entitlements derived not editable

### Access Control

```
Layer 10a (Eligibility) → Read-only access to Layer 10 (Events)
Layer 8 (Procurement) → Read-only access to Layer 10a (Entitlements)
Layer 9 (POS) → Write-only access to Layer 10 (Events)
```

**No component can:**
- Directly edit scores
- Directly grant entitlements
- Bypass enforcement checks

## Performance Optimization

### Event Store
- **Partitioning:** Partition events by `barber_id` for parallelism
- **Indexing:** Compound index on `(aggregate_type, aggregate_id, created_at)`
- **Archiving:** Move events >1 year to cold storage, keep aggregates

### Entitlement Ledger
- **Caching:** Cache active entitlements in Redis (TTL: 5 minutes)
- **Denormalization:** Pre-calculate tier thresholds
- **Read replicas:** Use read replicas for enforcement checks

### Score Calculation
- **Async:** Run as background job (Celery/RQ)
- **Incremental:** Only recalculate on new events (event listener)
- **Batching:** Batch calculate for multiple barbers

## Disaster Recovery

### Event Replay

If `EntitlementLedger` corrupted:

```python
ledger = EntitlementLedger(":memory:")
ledger.rebuild_from_events(cloud_store)
```

Replays all `BARBERSCORE_UPDATED` and `ENTITLEMENT_*` events to reconstruct state.

### Point-in-Time Recovery

```python
# Get barber state as of specific date
events = cloud_store.get_events(
    barber_id="alice",
    until="2024-01-15T00:00:00Z"
)

barberscore = calculate_from_events(events)
```

## Future Enhancements

### 1. Real-time Score Updates

**Current:** Batch calculation
**Future:** Stream processing (Kafka, Flink)

```
Events → Kafka → Flink Job → Score Updates → Push to UI
```

### 2. Predictive Scoring

**Current:** Reactive (based on past)
**Future:** Predictive (ML model)

```
Historical Events → ML Model → Predicted Future Score
```

### 3. Lending Integration

**Current:** Net terms only
**Future:** Equipment loans, shop financing

```
Entitlement Level → Lending Partner API → Loan Offers
```

### 4. Multi-tenant

**Current:** Single deployment
**Future:** SaaS with tenant isolation

```
Tenant ID → Separate Event Store → Separate Entitlement Ledger
```

## Development Guidelines

### Adding New Event Types

1. Add to `EventType` enum in `event_store.py`
2. Emit event in appropriate service
3. Update aggregate reconstruction logic
4. Add tests
5. Update documentation

### Modifying Score Calculation

1. Update weights in `config/score_rules.json`
2. Test impact on existing barbers (shadow mode first)
3. Communicate changes to barbers
4. Deploy with feature flag

### Adding New Tier

1. Update `config/entitlement_levels.json`
2. Update enforcement logic in `enforcement_middleware.py`
3. Update UI to display new tier
4. Test tier progression logic

## Monitoring & Observability

### Key Metrics

- **Event throughput:** Events/second
- **Score calculation latency:** Time to calculate score
- **Gaming pattern frequency:** Flags raised/day
- **Entitlement changes:** Grants/revocations per day
- **Enforcement blocks:** Orders blocked/reason

### Alerts

- 🚨 **Hard gate triggered** (excessive refunds, chargebacks)
- ⚠️ **Gaming pattern spike** (>10 flags/hour for single barber)
- 📉 **Score calculation lag** (>5 minutes behind events)
- 🔒 **Enforcement blocking >50%** of orders for a tier

## Conclusion

This architecture provides:
- ✅ Tamper-proof audit trail (event sourcing)
- ✅ Offline resilience (local queue)
- ✅ Gaming resistance (anti-gaming + hard gates)
- ✅ Scalable enforcement (materialized views)
- ✅ Extensible design (new event types, tiers, rules)

The system grows with the business while maintaining integrity and fairness.
