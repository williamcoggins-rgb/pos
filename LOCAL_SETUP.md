# View Your POS in 5 Minutes - Local Setup

This guide gets you viewing your POS application on your computer right now.

---

## What You'll See

After this setup, you'll have:
- ✅ Complete POS interface running at `http://localhost:8080`
- ✅ API running at `http://localhost:8000`
- ✅ Ability to register accounts, process payments, view BarberScore
- ✅ Full working system on your machine

---

## Prerequisites (2 minutes)

You need just TWO accounts (both free):

### 1. Supabase (1 minute)
1. Go to [supabase.com](https://supabase.com)
2. Click "Start your project" → Sign in with GitHub
3. Click "New project"
   - Name: `barberscore-local`
   - Database Password: `your_password` (save this!)
   - Region: Choose closest to you
4. Wait 2 minutes for provisioning

### 2. Stripe (1 minute)
1. Go to [stripe.com](https://stripe.com)
2. Click "Sign in" or "Start now"
3. Create account (you'll start in test mode automatically)

---

## Step 1: Get Your Credentials (2 minutes)

### Supabase Credentials

1. In your Supabase project, go to **Settings** (⚙️) → **API**
2. Copy these three values:
   - **Project URL**: `https://xxxxx.supabase.co`
   - **anon public key**: `eyJhbGc...` (long string)
   - **service_role key**: Click "Reveal" to see

3. Go to **Settings** → **Database**
4. Scroll to "Connection string" → **URI** tab
5. Copy the connection string and replace `[YOUR-PASSWORD]` with your actual password:
   ```
   postgresql://postgres:your_password@db.xxxxx.supabase.co:5432/postgres
   ```

6. Go to **Settings** → **API** → **JWT Settings**
7. Copy the **JWT Secret**

### Stripe Credentials

1. Go to **Developers** → **API keys**
2. Copy:
   - **Publishable key**: `pk_test_xxxxx`
   - **Secret key**: `sk_test_xxxxx` (click "Reveal")

---

## Step 2: Create Database Table (1 minute)

1. In Supabase, click **SQL Editor** in left sidebar
2. Click "New Query"
3. Paste this SQL:

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

CREATE POLICY "Barbers can insert own data"
  ON barbers FOR INSERT
  WITH CHECK (auth.uid() = id);
```

4. Click **Run** (bottom right)
5. You should see "Success. No rows returned"

---

## Step 3: Configure Environment (30 seconds)

Run this script (it creates your `.env` file):

```bash
cd /home/user/pos
./setup-local.sh
```

When prompted, paste your credentials from Step 1.

---

## Step 4: Start Everything (1 minute)

### Option A: Using Docker (Easiest)

```bash
cd /home/user/pos
docker-compose up
```

### Option B: Without Docker

```bash
# Terminal 1 - Start API
cd /home/user/pos
pip install -r requirements.txt
uvicorn api.main:app --reload

# Terminal 2 - Serve UI
cd /home/user/pos/web
python -m http.server 8080
```

---

## Step 5: View Your POS! 🎉

1. Open browser to: **http://localhost:8080/app.html**

2. You'll see the login screen with Square meets Footlocker design

3. Click **"Register"**

4. Create your account:
   - Email: `you@example.com`
   - Password: `password123`
   - Shop Name: `Your Shop Name`

5. Click **"Register"** - you'll be logged in!

6. You'll now see the POS interface:
   - Left side: Service buttons (Haircut $35, Shave $25, etc.)
   - Right side: Shopping cart
   - Click services to add them to cart
   - Click **"💳 CHARGE"** button to process payment
   - See success animation!

---

## What's Working

- ✅ **User Registration/Login**: Creates real accounts in Supabase
- ✅ **POS Checkout**: Add services, calculate totals with tax
- ✅ **Payment Processing**: Processes payments via Stripe (test mode)
- ✅ **BarberScore**: Calculates score from your transactions
- ✅ **Multi-Tenant**: Each barber has isolated data
- ✅ **Event Sourcing**: All transactions stored as immutable events

---

## Test the Complete Flow

1. **Make some sales** (click services, click CHARGE, repeat 5-10 times)

2. **Check your score** - Open browser console (F12) and type:
   ```javascript
   const api = new APIClient();
   api.getBarberScore().then(score => console.log(score));
   ```

3. **View API docs** - Go to http://localhost:8000/docs

4. **Check database** - Go to Supabase → Table Editor → see events

---

## Next Steps

Now that you can view it locally, you can:

1. **Deploy to production** - Follow `DEPLOYMENT.md` to make it accessible from anywhere
2. **Customize services** - Edit the service list in `web/app.html`
3. **Add card reader** - Order Stripe Reader M2 for physical card payments
4. **Test BarberScore** - Process 10+ transactions to unlock procurement tiers

---

## Troubleshooting

### "Failed to create sale"
- Check API is running at http://localhost:8000/health
- Verify `.env` has correct DATABASE_URL from Supabase

### "Login failed"
- Check SUPABASE_JWT_SECRET in `.env` is correct
- Verify you ran the SQL to create `barbers` table

### "Payment failed"
- Verify STRIPE_SECRET_KEY starts with `sk_test_`
- Check Stripe Dashboard → Logs for errors

### Port already in use
- API: Change port with `uvicorn api.main:app --port 8001`
- UI: Change port with `python -m http.server 8081`

---

## URLs to Bookmark

- **POS UI**: http://localhost:8080/app.html
- **API Health**: http://localhost:8000/health
- **API Docs**: http://localhost:8000/docs
- **Supabase Dashboard**: https://app.supabase.com
- **Stripe Dashboard**: https://dashboard.stripe.com

---

**🎊 You can now view and use your POS system!**

Process payments, build BarberScore, and unlock procurement access - all running on your local machine.

When you're ready to share it with others or access from any device, follow `DEPLOYMENT.md` to deploy to production (takes 30 minutes).
