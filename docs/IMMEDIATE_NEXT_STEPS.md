# Immediate Next Steps: What to Build NOW

## 🎯 Goal
**Build a working POS system that can accept real payments within 1-3 weeks**

---

## Architecture We Need to Build

```
┌─────────────────┐
│   iPad/Phone    │  ← Barber uses this
│   POS UI        │
│  (React/RN)     │
└────────┬────────┘
         │ HTTPS
         ↓
┌─────────────────┐
│   REST API      │  ← We need to build this
│   (FastAPI)     │
└────────┬────────┘
         │
    ┌────┴────┐
    ↓         ↓
┌────────┐  ┌──────────────┐
│Postgres│  │ Stripe API   │  ← Payment processing
│(Events)│  │ (Terminal)   │
└────────┘  └──────────────┘
                   ↓
            ┌──────────────┐
            │ Card Reader  │  ← Physical hardware
            │  (M2/BBPOS)  │
            └──────────────┘
```

---

## Week 1: API + Payment Integration

### Day 1-2: Set Up Infrastructure

**1. Create Supabase Project (10 minutes)**
```bash
1. Go to supabase.com
2. Click "New Project"
3. Choose free tier
4. Note down:
   - Project URL: https://xxxxx.supabase.co
   - Anon public key
   - Service role key (secret)
```

**2. Create Stripe Account (15 minutes)**
```bash
1. Go to stripe.com
2. Sign up
3. Go to Dashboard → Terminal
4. Request Terminal access (instant approval for test mode)
5. Note down:
   - Publishable key
   - Secret key
```

**3. Order Hardware ($59)**
```bash
1. stripe.com/terminal/readers
2. Order "Stripe Reader M2"
3. Ships in 1-2 days
```

---

### Day 3-4: Build API

**File: `api/main.py`**
```python
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
import stripe
from typing import Optional

app = FastAPI(title="POS API")

# Enable CORS for web/mobile clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

@app.post("/api/pos/sales")
async def create_sale(barber_id: str):
    """Create a new sale"""
    # Use existing square_like_pos.py logic
    pos = POSRuntime(barber_id, cloud_store, local_queue)
    sale_id = pos.create_sale()
    return {"sale_id": sale_id}

@app.post("/api/pos/sales/{sale_id}/items")
async def add_item(sale_id: str, name: str, price: float, quantity: int):
    """Add item to sale"""
    # Use existing logic
    pos = get_pos_runtime()
    item_id = pos.add_line_item(
        sale_id,
        name,
        quantity,
        Money.from_dollars(price)
    )
    return {"item_id": item_id}

@app.post("/api/pos/sales/{sale_id}/payment")
async def process_payment(sale_id: str, reader_id: str):
    """Process payment via Stripe Terminal"""

    # 1. Get sale total
    sale = pos.get_sale(sale_id)

    # 2. Create Stripe PaymentIntent
    intent = stripe.PaymentIntent.create(
        amount=sale.total.amount_minor,
        currency="usd",
        payment_method_types=["card_present"],
        capture_method="manual",
    )

    # 3. Collect payment on reader
    reader = stripe.terminal.Reader.process_payment_intent(
        reader_id,
        payment_intent=intent.id,
    )

    # 4. Capture payment
    stripe.PaymentIntent.capture(intent.id)

    # 5. Record in our event store
    pos.take_payment(
        sale_id,
        sale.total,
        PaymentMethod.CARD_PRESENT,
        card_last_four=intent.charges.data[0].payment_method_details.card_present.last4
    )

    return {"status": "captured", "payment_id": intent.id}
```

**Deploy to Render.com:**
```bash
# render.yaml
services:
  - type: web
    name: pos-api
    env: python
    buildCommand: "pip install -r requirements.txt"
    startCommand: "uvicorn api.main:app --host 0.0.0.0 --port $PORT"
    envVars:
      - key: DATABASE_URL
        value: YOUR_SUPABASE_CONNECTION_STRING
      - key: STRIPE_SECRET_KEY
        value: YOUR_STRIPE_SECRET_KEY
```

---

### Day 5: Build Simple Checkout UI

**File: `web/checkout.html`**
```html
<!DOCTYPE html>
<html>
<head>
    <title>POS Checkout</title>
    <script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
</head>
<body>
    <div id="root"></div>

    <script type="text/babel">
        function Checkout() {
            const [sale, setSale] = useState(null);
            const [items, setItems] = useState([]);

            const startSale = async () => {
                const res = await fetch('https://your-api.onrender.com/api/pos/sales', {
                    method: 'POST',
                    body: JSON.stringify({ barber_id: 'barber_123' })
                });
                const data = await res.json();
                setSale(data.sale_id);
            };

            const addItem = async (name, price) => {
                await fetch(`https://your-api.onrender.com/api/pos/sales/${sale}/items`, {
                    method: 'POST',
                    body: JSON.stringify({ name, price, quantity: 1 })
                });
                setItems([...items, { name, price }]);
            };

            const checkout = async () => {
                await fetch(`https://your-api.onrender.com/api/pos/sales/${sale}/payment`, {
                    method: 'POST',
                    body: JSON.stringify({ reader_id: 'tmr_xxx' })
                });
                alert('Payment successful!');
            };

            return (
                <div style={{ padding: '20px', maxWidth: '400px' }}>
                    <h1>POS Checkout</h1>

                    {!sale && (
                        <button onClick={startSale}>New Sale</button>
                    )}

                    {sale && (
                        <>
                            <button onClick={() => addItem('Haircut', 35)}>
                                Haircut - $35
                            </button>
                            <button onClick={() => addItem('Shave', 25)}>
                                Shave - $25
                            </button>

                            <div>
                                <h3>Items:</h3>
                                {items.map((item, i) => (
                                    <div key={i}>{item.name} - ${item.price}</div>
                                ))}
                            </div>

                            <button onClick={checkout}>
                                Charge ${items.reduce((sum, i) => sum + i.price, 0)}
                            </button>
                        </>
                    )}
                </div>
            );
        }

        ReactDOM.render(<Checkout />, document.getElementById('root'));
    </script>
</body>
</html>
```

**Test it:**
```bash
# Open in browser, click buttons
# When you click "Charge", Stripe reader should activate
# Tap test card → payment completes → event stored
```

---

## Week 2-3: Polish & Test

### Build Proper UI
- Use shadcn/ui for modern components
- Add numpad for custom amounts
- Show card reader connection status
- Handle errors gracefully

### Test with Real Hardware
- Connect Stripe Reader M2 via Bluetooth
- Process 10 test transactions
- Verify events in database
- Check BarberScore updates

### Add Basic Auth
- Supabase magic link login
- Protect API with JWT tokens
- Multi-tenant data isolation

---

## Decision Points Right Now

### 1. **Do you want mobile apps immediately, or start with web?**
   - **Web first:** Faster to market (2 weeks), works on iPad
   - **Mobile first:** Better UX, but 4-6 weeks

   **Recommendation:** Start web, add mobile in Phase 2

### 2. **What's your budget for hardware?**
   - **Stripe Reader M2:** $59 (cheapest, Bluetooth)
   - **BBPOS WisePOS E:** $299 (all-in-one Android terminal)
   - **iPad + Reader M2:** $329 + $59 = $388 (best UX)

   **Recommendation:** Start with Reader M2, upgrade later

### 3. **Free or paid?**
   - **Free + transaction fee:** 3.2% + 5¢ (Stripe 2.7% + your 0.5%)
   - **Monthly subscription:** $29/month + 2.9% + 5¢
   - **Freemium:** Free for Level 0-1, paid for Level 2+

   **Recommendation:** Free + 3.2% transaction fee (easiest)

---

## 🚀 Let's Start Building

I can start building the API layer right now. Here's what I'll create:

1. ✅ **FastAPI application** (`api/main.py`)
2. ✅ **POS endpoints** (create sale, add items, payment)
3. ✅ **Stripe Terminal integration** (`api/payment_processor.py`)
4. ✅ **Database connection** (PostgreSQL via Supabase)
5. ✅ **Basic authentication** (Supabase Auth)
6. ✅ **Deployment config** (Render.com `render.yaml`)

Should I proceed and build the API layer now?
