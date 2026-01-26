# Product Roadmap: POS to App Store

## Current State

✅ **What We Have:**
- Event-sourced backend architecture (Python)
- BarberScore eligibility engine
- Procurement/entitlement system
- BarberScore dashboard UI (HTML/React)
- Comprehensive test suite

❌ **What We're Missing:**
- Actual POS checkout interface
- Real payment processor integration
- Cloud infrastructure
- API layer for clients
- Mobile apps
- Authentication system

---

## 🎯 Phase 1: Working POS MVP (Weeks 1-3)

**Goal:** Barber can accept a credit card payment on a tablet/computer

### Week 1: Infrastructure & API

#### 1.1 Cloud Infrastructure Setup
**Tool Stack:**
- **Database:** Supabase (PostgreSQL) or Railway
- **Hosting:** Render.com or Fly.io
- **File Storage:** S3 or Supabase Storage

**Tasks:**
```bash
# Deploy PostgreSQL
- Set up Supabase project (free tier)
- Migrate event_store.py to use PostgreSQL
- Set up connection pooling
- Configure backups

# Deploy API
- Set up Render.com web service
- Configure environment variables
- Set up CI/CD (GitHub Actions)
```

**Deliverable:** PostgreSQL database live, API deployment pipeline ready

---

#### 1.2 REST API Layer
**Framework:** FastAPI (Python)

**File Structure:**
```
/api
├── main.py                 # FastAPI app
├── routers/
│   ├── pos.py             # POS endpoints
│   ├── eligibility.py     # BarberScore endpoints
│   ├── procurement.py     # Store endpoints
│   └── auth.py            # Authentication
├── dependencies.py         # Shared dependencies
└── models.py              # Pydantic models
```

**Core Endpoints:**
```python
# POS Endpoints
POST   /api/pos/sales                    # Create sale
POST   /api/pos/sales/{id}/items         # Add line item
POST   /api/pos/sales/{id}/payment       # Take payment
POST   /api/pos/sales/{id}/refund        # Process refund
GET    /api/pos/sales/{id}               # Get sale details

# Eligibility Endpoints
GET    /api/eligibility/{barber_id}      # Get BarberScore
GET    /api/entitlements/{barber_id}     # Get entitlements

# Procurement Endpoints
POST   /api/procurement/orders            # Create order
GET    /api/procurement/orders            # List orders
GET    /api/procurement/catalog           # Browse products

# Auth Endpoints
POST   /api/auth/register                 # Register barber
POST   /api/auth/login                    # Login
POST   /api/auth/refresh                  # Refresh token
```

**Deliverable:** REST API deployed and documented (OpenAPI/Swagger)

---

### Week 2: Payment Integration

#### 2.1 Choose Payment Processor

**Option A: Stripe Terminal (RECOMMENDED)**
- ✅ Best developer experience
- ✅ Strong API, great documentation
- ✅ Reader hardware available ($59-299)
- ✅ PCI compliance handled
- ✅ Built-in offline mode
- ⚠️ 2.7% + 5¢ per transaction

**Option B: Square Terminal API**
- ✅ Square branding (familiar to barbers)
- ✅ Lower rates for established businesses
- ⚠️ Harder API integration
- ⚠️ Requires Square account

**Option C: PayPal Zettle**
- ✅ Lower upfront cost
- ⚠️ Limited offline support
- ⚠️ Less flexible API

**Decision:** Start with **Stripe Terminal** for speed and reliability.

---

#### 2.2 Stripe Terminal Integration

**Hardware Options:**
- **Stripe Reader M2** ($59) - Bluetooth, countertop
- **BBPOS WisePOS E** ($299) - All-in-one Android terminal
- **Verifone P400** ($249) - Countertop with screen

**Integration Steps:**

```python
# File: payment_processor.py

import stripe

class StripeTerminalProcessor:
    def __init__(self, secret_key: str):
        stripe.api_key = secret_key

    def create_payment_intent(self, amount: Money) -> str:
        """Create payment intent for terminal"""
        intent = stripe.PaymentIntent.create(
            amount=amount.amount_minor,
            currency="usd",
            payment_method_types=["card_present"],
            capture_method="manual",  # Auth first, capture later
        )
        return intent.id

    def collect_payment(self, reader_id: str, payment_intent_id: str):
        """Collect payment on terminal"""
        return stripe.terminal.Reader.process_payment_intent(
            reader_id,
            payment_intent=payment_intent_id,
        )

    def capture_payment(self, payment_intent_id: str):
        """Capture authorized payment"""
        return stripe.PaymentIntent.capture(payment_intent_id)
```

**Deliverable:**
- Stripe Terminal SDK integrated
- Can process test payment on physical reader
- Payment events flow to event store

---

### Week 3: POS UI + Testing

#### 3.1 Build POS Checkout UI

**Tech Stack:**
- **Framework:** React (TypeScript)
- **UI Library:** shadcn/ui or Chakra UI
- **State:** Zustand or Redux Toolkit
- **API Client:** TanStack Query (React Query)

**Screen Flow:**
```
1. Login Screen
   ↓
2. Active Sale Screen
   - Numpad for manual entry
   - Service buttons (preset items)
   - Line item list
   - Subtotal/tax/total
   - "Charge" button
   ↓
3. Payment Screen
   - Amount to charge
   - Payment method selector
   - "Process Payment" button
   - Shows reader status
   ↓
4. Receipt Screen
   - Transaction details
   - "New Sale" / "Email Receipt" buttons
```

**Key Components:**

```typescript
// src/components/pos/ActiveSale.tsx
interface ActiveSaleProps {
  saleId: string;
  items: LineItem[];
  total: Money;
  onAddItem: (item: LineItem) => void;
  onCheckout: () => void;
}

// src/components/pos/PaymentScreen.tsx
interface PaymentScreenProps {
  saleId: string;
  amount: Money;
  readerStatus: 'connected' | 'disconnected' | 'busy';
  onProcessPayment: () => void;
}

// src/components/pos/Numpad.tsx
// src/components/pos/ServiceButtons.tsx
// src/components/pos/LineItemList.tsx
```

**Deliverable:**
- Web-based POS UI works on tablet/desktop
- Can create sale, add items, process payment
- Connected to REST API

---

#### 3.2 Authentication & Multi-Tenant

**Use Supabase Auth (easiest)**

```typescript
// src/lib/auth.ts
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_ANON_KEY
)

export const login = async (email: string, password: string) => {
  const { data, error } = await supabase.auth.signInWithPassword({
    email,
    password,
  })
  return { user: data.user, error }
}
```

**Database Schema:**
```sql
-- Add to Supabase
CREATE TABLE barbers (
  id UUID PRIMARY KEY REFERENCES auth.users(id),
  barber_id TEXT UNIQUE NOT NULL,
  shop_name TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Row Level Security
ALTER TABLE events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Barbers can only see their own events"
  ON events FOR SELECT
  USING (auth.uid() = (
    SELECT id FROM barbers WHERE barber_id = events.payload->>'barber_id'
  ));
```

**Deliverable:**
- Barbers can register and log in
- Each barber only sees their own data
- API enforces tenant isolation

---

#### 3.3 End-to-End Testing

**Test Checklist:**
- [ ] Barber registers account
- [ ] Barber logs in on iPad
- [ ] Creates sale with 3 line items
- [ ] Processes payment with Stripe Test Reader
- [ ] Receives confirmation
- [ ] BarberScore updates (after 10 transactions)
- [ ] Can view BarberScore dashboard
- [ ] Unlocks procurement store at Level 1

**Tools:**
- Stripe CLI for webhook testing
- Stripe test cards
- Cypress for E2E tests

**Deliverable:** Full flow works end-to-end with real hardware

---

## 🚀 Phase 2: Mobile Apps (Weeks 4-7)

**Goal:** Native iOS and Android apps in TestFlight/Beta

### Week 4-5: Mobile App Development

**Tech Stack Choice:**

| Option | Pros | Cons | Recommendation |
|--------|------|------|----------------|
| **React Native** | Share code with web, fast development | Performance issues on complex UI | ✅ **BEST CHOICE** |
| **Flutter** | Best performance, beautiful UI | Dart language, separate codebase | Good alternative |
| **Native (Swift/Kotlin)** | Best performance and UX | 2x development time | Only if huge budget |

**Decision:** **React Native + Expo** for speed and code sharing

---

#### Mobile App Structure

```
/mobile
├── App.tsx
├── app/
│   ├── (auth)/
│   │   ├── login.tsx
│   │   └── register.tsx
│   └── (tabs)/
│       ├── pos.tsx           # POS checkout
│       ├── sales.tsx         # Sales history
│       ├── score.tsx         # BarberScore
│       └── store.tsx         # Procurement
├── components/
│   ├── pos/
│   │   ├── Numpad.tsx
│   │   ├── ServiceButtons.tsx
│   │   └── PaymentReader.tsx
│   └── shared/
├── lib/
│   ├── api.ts              # API client
│   ├── stripe.ts           # Stripe Terminal SDK
│   └── auth.ts             # Supabase auth
└── hooks/
    ├── useSale.ts
    ├── usePayment.ts
    └── useBarberScore.ts
```

**Key Features:**
- Tab navigation (POS, History, Score, Store)
- Bluetooth connection to card reader
- Offline mode (queue transactions)
- Push notifications for score updates
- Biometric login (Face ID/Touch ID)

---

#### Stripe Terminal Mobile SDK

**iOS Integration:**
```swift
// Use @stripe/stripe-terminal-react-native

import { useStripeTerminal } from '@stripe/stripe-terminal-react-native'

const { discoverReaders, connectReader } = useStripeTerminal()

// Discover nearby readers
const readers = await discoverReaders({
  discoveryMethod: 'bluetoothScan',
  simulated: false,
})

// Connect to reader
await connectReader(readers[0].serialNumber)
```

**Android Integration:**
Same package, slightly different permissions setup

**Deliverable:**
- Mobile app connects to Stripe reader
- Can process payments from iPhone/Android phone
- Offline mode queues transactions

---

### Week 6-7: Polish & Compliance

#### App Store Requirements

**iOS App Store:**
- [ ] Privacy Policy URL
- [ ] Terms of Service URL
- [ ] App icon (1024x1024)
- [ ] Screenshots (multiple sizes)
- [ ] App Store Connect account ($99/year)
- [ ] Code signing certificate
- [ ] Financial services compliance docs

**Google Play Store:**
- [ ] Privacy Policy URL
- [ ] Developer account ($25 one-time)
- [ ] Feature graphic (1024x500)
- [ ] Screenshots
- [ ] Content rating questionnaire
- [ ] Payment processor verification

**Deliverable:**
- Apps submitted to TestFlight (iOS) and Google Play Beta
- 10 beta testers using the app
- Feedback incorporated

---

## 🏪 Phase 3: App Store Launch (Weeks 8-10)

### Week 8: Security & Performance

#### Security Hardening
```bash
# API Security
- [ ] Rate limiting (100 req/min per user)
- [ ] SQL injection prevention (parameterized queries)
- [ ] CORS configuration
- [ ] Helmet.js security headers
- [ ] API key rotation
- [ ] Secrets in environment variables (not code)

# Mobile Security
- [ ] Certificate pinning
- [ ] Jailbreak/root detection
- [ ] Code obfuscation
- [ ] Biometric authentication required
- [ ] Auto-logout after 15min
```

#### Performance Optimization
```bash
# Database
- [ ] Add indexes on frequently queried columns
- [ ] Implement database connection pooling
- [ ] Set up read replicas for scale

# API
- [ ] Implement Redis caching for entitlements
- [ ] Lazy load heavy operations
- [ ] Compress API responses (gzip)
- [ ] CDN for static assets

# Mobile
- [ ] Lazy load tab screens
- [ ] Optimize images (WebP format)
- [ ] Minimize bundle size
- [ ] Profile with React DevTools
```

**Deliverable:** App loads <2s, API responds <200ms p95

---

### Week 9: Compliance & Legal

#### PCI Compliance
**Because we handle payments, we need:**

- [ ] PCI-DSS SAQ A questionnaire (Stripe handles most)
- [ ] Security scan (Stripe can help)
- [ ] SSL certificate on all endpoints
- [ ] Never store raw card numbers
- [ ] Secure transmission (TLS 1.2+)

**Good news:** Using Stripe Terminal, they handle most PCI burden.

#### Legal Documents
Create these pages:

```
/legal
├── privacy-policy.html      # Required by app stores
├── terms-of-service.html    # Required by app stores
├── refund-policy.html       # Good practice
└── support.html             # Required by Apple
```

**Use generators:**
- Termly.io (free templates)
- GetTerms.io
- Or hire lawyer ($500-1000)

**Deliverable:** All legal docs live, linked in app

---

### Week 10: Launch Preparation

#### Pre-Launch Checklist

**Marketing Assets:**
- [ ] App icon designed
- [ ] Screenshots (5 per platform)
- [ ] App Store description (compelling copy)
- [ ] Demo video (30 seconds)
- [ ] Landing page (pos.yourcompany.com)
- [ ] Support email (support@yourcompany.com)

**Operations:**
- [ ] Customer support system (Intercom/Zendesk)
- [ ] Bug tracking (Linear/Jira)
- [ ] Monitoring (Sentry for errors)
- [ ] Analytics (Mixpanel/Amplitude)
- [ ] Status page (status.yourcompany.com)

**Billing (if not free):**
- [ ] Stripe Billing setup
- [ ] Pricing page
- [ ] Subscription management
- [ ] Trial period (7-14 days)

**Launch:**
- [ ] Soft launch to beta users (100 barbers)
- [ ] Fix critical bugs
- [ ] Submit to App Store & Google Play
- [ ] Wait for review (1-7 days)
- [ ] Launch! 🚀

---

## 📊 Tech Stack Summary

### Backend
- **Language:** Python 3.11+
- **API:** FastAPI
- **Database:** PostgreSQL (Supabase)
- **Cache:** Redis
- **Hosting:** Render.com or Fly.io
- **Storage:** S3 or Supabase Storage

### Frontend
- **Web:** React (TypeScript) + Vite
- **Mobile:** React Native + Expo
- **UI:** shadcn/ui (web), React Native Paper (mobile)
- **State:** Zustand or Jotai
- **API Client:** TanStack Query

### Payments
- **Processor:** Stripe Terminal
- **Readers:** Stripe Reader M2 ($59)
- **SDK:** @stripe/stripe-terminal-react-native

### Auth
- **Provider:** Supabase Auth
- **Method:** Email/password + biometrics

### Infrastructure
- **Database:** Supabase PostgreSQL
- **Hosting:** Render.com
- **CDN:** Cloudflare
- **Monitoring:** Sentry
- **Analytics:** Mixpanel

---

## 💰 Cost Breakdown

### Development Costs (If hiring)
| Role | Duration | Rate | Total |
|------|----------|------|-------|
| Backend Dev | 2 weeks | $150/hr | $12,000 |
| Frontend Dev | 3 weeks | $150/hr | $18,000 |
| Mobile Dev | 4 weeks | $150/hr | $24,000 |
| UI/UX Designer | 1 week | $125/hr | $5,000 |
| **TOTAL** | | | **$59,000** |

### Operational Costs (Monthly)
| Service | Cost |
|---------|------|
| Supabase (Pro) | $25 |
| Render.com (Web + Worker) | $25 |
| Stripe Terminal | $0 (pay per transaction) |
| Domain | $12/year |
| SSL | $0 (Let's Encrypt) |
| App Store (iOS) | $99/year |
| Google Play (Android) | $25 one-time |
| **TOTAL** | **~$50/month** |

### Transaction Costs
- Stripe: 2.7% + 5¢ per card present transaction
- Your margin: Add 0.5% = **3.2% + 5¢** to barber

---

## 🎯 Success Metrics

**Phase 1 Success:**
- ✅ 10 barbers processing real payments
- ✅ 0 payment failures
- ✅ BarberScore updating correctly
- ✅ <2s checkout time

**Phase 2 Success:**
- ✅ Mobile app on 50 devices (iOS + Android)
- ✅ 4.5+ star rating from beta testers
- ✅ <5% crash rate
- ✅ Card reader connects <10 seconds

**Phase 3 Success:**
- ✅ Apps approved by Apple and Google
- ✅ 100 active barbers in first month
- ✅ $50k+ processed through POS
- ✅ First barber unlocks Level 2

---

## 🚨 Critical Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **App Store rejection** | 2 week delay | Follow guidelines exactly, have backup plans |
| **Payment processor issues** | Can't process payments | Have Stripe support contact ready |
| **Offline mode bugs** | Lost transactions | Extensive offline testing, local queue |
| **Security breach** | Business killer | Penetration testing, bug bounty program |
| **Slow adoption** | No revenue | Beta program, incentives (free for 3 months) |

---

## 📅 Timeline Summary

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| **Phase 1: Working POS** | 3 weeks | Web POS processing real payments |
| **Phase 2: Mobile Apps** | 4 weeks | iOS/Android apps in beta |
| **Phase 3: Launch** | 3 weeks | Live in app stores |
| **TOTAL** | **10 weeks** | **Full launch** |

---

## 🎬 Immediate Next Steps (This Week)

1. **Make Infrastructure Decisions**
   - ✅ Use Supabase for database + auth
   - ✅ Use Stripe Terminal for payments
   - ✅ Use Render.com for API hosting
   - ✅ Use React Native for mobile

2. **Set Up Accounts**
   - [ ] Create Supabase project
   - [ ] Create Stripe account (request Terminal access)
   - [ ] Create Render.com account
   - [ ] Order Stripe Reader M2 ($59)

3. **Start Building**
   - [ ] Build FastAPI layer (Week 1)
   - [ ] Deploy to Render.com
   - [ ] Integrate Stripe Terminal SDK
   - [ ] Build simple checkout UI

**First Milestone:** Process a real $1 test payment by end of Week 1

---

Would you like me to start building Phase 1 (the API layer and payment integration) right now?
