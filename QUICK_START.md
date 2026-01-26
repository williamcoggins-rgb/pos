# Quick Start Guide - BarberScore POS API

Get the API running in under 10 minutes!

## Prerequisites

- Python 3.11+
- PostgreSQL (or use Supabase)
- Stripe account (test mode is fine)
- Supabase account (free tier works)

---

## Step 1: Clone and Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
```

---

## Step 2: Set Up Supabase

1. Go to [supabase.com](https://supabase.com) and create a free project
2. Go to Settings → API to get your credentials
3. Run this SQL in the SQL Editor:

```sql
-- Create barbers table
CREATE TABLE barbers (
  id UUID PRIMARY KEY REFERENCES auth.users(id),
  barber_id TEXT UNIQUE NOT NULL,
  shop_name TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE barbers ENABLE ROW LEVEL SECURITY;

-- Policy: barbers can only see their own data
CREATE POLICY "Barbers can only see own data"
  ON barbers FOR SELECT
  USING (auth.uid() = id);
```

4. Update `.env` with your Supabase credentials:
```env
DATABASE_URL=postgresql://postgres:password@db.xxxx.supabase.co:5432/postgres
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=your_anon_key_here
SUPABASE_JWT_SECRET=your_jwt_secret_here
```

---

## Step 3: Set Up Stripe

1. Go to [stripe.com](https://stripe.com) and create an account
2. Go to Developers → API Keys
3. Copy your test keys to `.env`:

```env
STRIPE_SECRET_KEY=sk_test_xxxxxxxxxxxx
STRIPE_PUBLISHABLE_KEY=pk_test_xxxxxxxxxxxx
```

4. (Optional) Request Terminal access for card readers:
   - Go to Dashboard → Terminal
   - Click "Request Access" (instant approval for test mode)

---

## Step 4: Start the API

```bash
# Run the API
uvicorn api.main:app --reload

# API will be available at:
# http://localhost:8000

# View docs at:
# http://localhost:8000/docs
```

---

## Step 5: Test the API

### Register a barber:
```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "barber@example.com",
    "password": "password123",
    "shop_name": "The Fresh Cut"
  }'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "barber_id": "barber_abc123",
  "shop_name": "The Fresh Cut"
}
```

Save the `access_token` for next requests!

### Create a sale:
```bash
curl -X POST http://localhost:8000/api/pos/sales \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "barber_id": "barber_abc123",
    "metadata": {}
  }'
```

Response:
```json
{
  "sale_id": "abc-123-def-456"
}
```

### Add line items:
```bash
curl -X POST http://localhost:8000/api/pos/sales/abc-123-def-456/items \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "name": "Haircut",
    "quantity": 1,
    "unit_price_cents": 3500
  }'
```

### Calculate tax:
```bash
curl -X POST http://localhost:8000/api/pos/sales/abc-123-def-456/tax \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "tax_rate": 0.08
  }'
```

### Process payment:
```bash
curl -X POST http://localhost:8000/api/pos/sales/abc-123-def-456/payment \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "payment_method": "CASH"
  }'
```

Success! 🎉

---

## Step 6: View the UI

```bash
# Open the checkout UI in your browser
open web/index.html

# Or serve it with Python
cd web
python -m http.server 8080

# Then open http://localhost:8080
```

---

## Step 7: Check BarberScore

After processing 10+ transactions, check the score:

```bash
curl http://localhost:8000/api/eligibility/score/barber_abc123 \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

Response:
```json
{
  "barber_id": "barber_abc123",
  "score": 65,
  "tier": "Level 2",
  "metrics": {
    "qualified_transactions": 12,
    "total_revenue_cents": 42000,
    "refund_rate": 0.0,
    ...
  },
  "flags": [],
  "hard_gate_blocks": []
}
```

---

## Using Docker (Alternative)

```bash
# Start with Docker Compose
docker-compose up

# API runs at http://localhost:8000
# PostgreSQL at localhost:5432
```

---

## Troubleshooting

### Database connection error
- Make sure your `DATABASE_URL` is correct
- For Supabase, use the "Connection string" from Settings → Database
- Format: `postgresql://postgres:password@db.xxxx.supabase.co:5432/postgres`

### Stripe errors
- Verify your API keys are test keys (`sk_test_...` and `pk_test_...`)
- Check you've enabled Terminal in your Stripe dashboard

### Auth errors
- Make sure `SUPABASE_JWT_SECRET` is correct (Settings → API → JWT Settings)
- Check token hasn't expired (default 30 min)

### Import errors
- Run `pip install -r requirements.txt` again
- Check you're using Python 3.11+

---

## Next Steps

1. ✅ **Connect a card reader**
   - Order Stripe Reader M2 ($59)
   - Connect via Bluetooth
   - Use `reader_id` in payment requests

2. ✅ **Deploy to production**
   - Push to GitHub
   - Connect Render.com (reads `render.yaml` automatically)
   - Set environment variables in dashboard

3. ✅ **Build mobile app**
   - Use React Native
   - Connect to your deployed API
   - Same endpoints work for web and mobile

4. ✅ **Unlock procurement**
   - Process 10+ transactions
   - Reach Level 1 (score 50+)
   - Access procurement store

---

## API Documentation

Full API docs available at:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

---

## Support

- Issues: https://github.com/your-org/pos/issues
- Docs: See `docs/` folder
- Email: support@barberscore.com

---

**You're ready to go! 🚀**

The POS is now accepting payments, calculating BarberScore, and enforcing procurement access.
