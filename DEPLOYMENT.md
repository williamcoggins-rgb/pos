# Complete Deployment Guide

Get your POS system live in production in under 30 minutes.

---

## 🎯 What You're Deploying

```
┌─────────────────┐
│   Vercel        │  ← Your UI (web/app.html)
│   Frontend      │
└────────┬────────┘
         │ HTTPS
         ↓
┌─────────────────┐
│  Render.com     │  ← Your API (FastAPI)
│  Backend        │
└────────┬────────┘
         │
    ┌────┴────┐
    ↓         ↓
┌────────┐  ┌──────────┐
│Supabase│  │  Stripe  │
│Database│  │ Payments │
└────────┘  └──────────┘
```

---

## Step 1: Set Up Supabase (5 minutes)

### Create Project

1. Go to [supabase.com](https://supabase.com)
2. Click "New Project"
3. Fill in:
   - **Name:** barberscore-pos
   - **Database Password:** (save this!)
   - **Region:** Choose closest to you
4. Wait 2 minutes for it to provision

### Create Database Tables

1. Click "SQL Editor" in left sidebar
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

4. Click "Run" (bottom right)
5. You should see "Success. No rows returned"

### Get Credentials

1. Go to Settings (gear icon) → API
2. Copy these values (you'll need them later):
   - **Project URL:** `https://xxxxx.supabase.co`
   - **anon public key:** `eyJhbGc...` (long string)
   - **service_role key:** (click "Reveal" to see)

3. Go to Settings → Database
4. Scroll to "Connection string" → URI
5. Copy the connection string (replace `[YOUR-PASSWORD]` with your actual password)
   - Format: `postgresql://postgres:[YOUR-PASSWORD]@db.xxxxx.supabase.co:5432/postgres`

6. Go to Settings → API → JWT Settings
7. Copy the **JWT Secret** (you'll need this too)

✅ **Supabase Done!** Save all these values in a notes file.

---

## Step 2: Set Up Stripe (5 minutes)

### Create Account

1. Go to [stripe.com](https://stripe.com)
2. Create account (or login)
3. You'll start in **Test Mode** (perfect for now)

### Get API Keys

1. Go to Developers → API keys
2. Copy:
   - **Publishable key:** `pk_test_xxxxx`
   - **Secret key:** `sk_test_xxxxx` (click "Reveal")

### (Optional) Enable Terminal

1. Go to Products → Terminal
2. Click "Get Started"
3. Request access (instant approval in test mode)

✅ **Stripe Done!** Save your keys.

---

## Step 3: Deploy API to Render.com (10 minutes)

### Push Code to GitHub (if not already)

```bash
git add -A
git commit -m "Ready for deployment"
git push origin main
```

### Deploy on Render

1. Go to [render.com](https://render.com)
2. Click "Get Started" (or "New +")
3. Connect your GitHub account
4. Find your `pos` repository
5. Click "Connect"

### Configure Service

Render will auto-detect `render.yaml`! But you need to set env vars:

1. Click your service once created
2. Go to "Environment" tab
3. Add these environment variables:

```
DATABASE_URL = [Your Supabase connection string from Step 1]
STRIPE_SECRET_KEY = sk_test_xxxxx [From Step 2]
STRIPE_PUBLISHABLE_KEY = pk_test_xxxxx [From Step 2]
SUPABASE_URL = https://xxxxx.supabase.co [From Step 1]
SUPABASE_KEY = [Your Supabase anon key from Step 1]
SUPABASE_JWT_SECRET = [Your JWT secret from Step 1]
SECRET_KEY = [Click "Generate" - Render will create one]
```

4. Click "Save Changes"
5. Deployment will start automatically

### Wait for Deployment

- First deploy takes ~5 minutes
- Watch the logs in the "Logs" tab
- When done, you'll see: "Application startup complete"
- Your API is now live at: `https://your-service-name.onrender.com`

### Test Your API

```bash
# Replace with your Render URL
curl https://your-service-name.onrender.com/health

# Should return:
# {"status":"healthy","version":"1.0.0"}
```

✅ **API Deployed!** Copy your Render URL.

---

## Step 4: Deploy UI to Vercel (5 minutes)

### Update API URL

1. Open `web/api-client.js`
2. Find this line:
```javascript
: 'https://barberscore-pos-api.onrender.com'; // Change to your deployed API URL
```

3. Replace with YOUR Render URL:
```javascript
: 'https://your-service-name.onrender.com';
```

4. Save and commit:
```bash
git add web/api-client.js
git commit -m "Update API URL for production"
git push
```

### Deploy on Vercel

1. Go to [vercel.com](https://vercel.com)
2. Click "Add New..." → "Project"
3. Import your GitHub repository
4. Configure:
   - **Root Directory:** `web`
   - **Framework Preset:** Other
   - Leave build settings blank (it's just static files)
5. Click "Deploy"

### Wait for Deployment

- Takes ~1 minute
- When done, you'll see your live URL: `https://your-app.vercel.app`

### Test Your UI

1. Visit your Vercel URL
2. You should see the login screen
3. Click "Register"
4. Create an account:
   - Email: your@email.com
   - Password: (make one up)
   - Shop Name: "Test Shop"

5. You should be logged in and see the POS!

✅ **UI Deployed!** Bookmark your Vercel URL.

---

## Step 5: Process Your First Real Payment (5 minutes)

### Test the Flow

1. Open your Vercel URL on any device (computer, iPad, phone)
2. Login with the account you just created
3. Click a service (e.g., "Haircut - $35")
4. Click another service (e.g., "Shave - $25")
5. See them appear in the cart on the right
6. Click "💳 CHARGE $64.80"
7. Wait 2 seconds...
8. See "Payment Successful!" ✅

### Verify in Database

1. Go to Supabase → Table Editor → `events` table
2. You should see events:
   - `SALE_CREATED`
   - `LINE_ITEM_ADDED` (2 times)
   - `TAX_CALCULATED`
   - `PAYMENT_CAPTURED`

✅ **IT WORKS!** You just processed a payment!

---

## Step 6: Check Your BarberScore (After 10+ Transactions)

After processing 10+ sales:

1. Open browser console (F12)
2. Type:
```javascript
const api = new APIClient();
api.getBarberScore().then(score => console.log(score));
```

3. You'll see:
```json
{
  "score": 52,
  "tier": "Level 1",
  "metrics": {
    "qualified_transactions": 12,
    "total_revenue_cents": 42000,
    ...
  }
}
```

4. Once score ≥ 50, you've unlocked the procurement store!

---

## 🎉 You're Live!

### What You Have:

✅ **Production API:** Running on Render.com
✅ **Production UI:** Running on Vercel
✅ **Real Database:** PostgreSQL on Supabase
✅ **Real Payments:** Stripe (test mode)
✅ **Real Auth:** Supabase Authentication
✅ **BarberScore:** Calculating from real transactions

### What Works:

- Register/Login from any device
- Process payments (currently CASH mode)
- Calculate BarberScore
- Track all transactions in database
- View procurement entitlements

### URLs to Save:

- **Your POS:** `https://your-app.vercel.app`
- **Your API:** `https://your-service-name.onrender.com`
- **API Docs:** `https://your-service-name.onrender.com/docs`
- **Supabase Dashboard:** `https://app.supabase.com`
- **Stripe Dashboard:** `https://dashboard.stripe.com`

---

## Next Steps

### 1. Share with Others

Send your Vercel URL to anyone:
- They can register their own account
- Each barber has their own data (isolated)
- Each gets their own BarberScore

### 2. Connect a Card Reader (Optional)

Order hardware:
- **Stripe Reader M2:** $59
- Ships in 2-3 days

Once you have it:
1. Pair via Bluetooth to your device
2. Go to Stripe Dashboard → Terminal → Readers
3. Copy the `reader_id`
4. Update payment code to use `CARD_PRESENT` instead of `CASH`

### 3. Go Live (When Ready)

Currently in **Test Mode** - no real money.

To go live:
1. Stripe → Toggle "Test mode" OFF
2. Get new Live API keys
3. Update environment variables on Render
4. Re-deploy

### 4. Custom Domain (Optional)

Instead of `your-app.vercel.app`:
1. Buy domain (e.g., `getbarberscore.com`) on Namecheap ($12/year)
2. Vercel → Settings → Domains → Add
3. Follow DNS instructions
4. Your POS is at `pos.getbarberscore.com`

### 5. Mobile Apps

Once you're happy with web version:
- Build React Native app (2-3 weeks)
- Submit to App Store + Google Play
- Same backend, just different frontend

---

## Troubleshooting

### API won't start on Render
- Check environment variables are set correctly
- Check logs for specific error
- Make sure DATABASE_URL starts with `postgresql://` not `postgres://`

### UI shows "Failed to create sale"
- Check API URL in `web/api-client.js` is correct
- Open Network tab (F12) to see actual error
- Verify your Render service is running (green status)

### Login fails
- Check SUPABASE_JWT_SECRET is correct
- Make sure you ran the SQL to create `barbers` table
- Check Supabase logs for auth errors

### Payments fail
- Check STRIPE_SECRET_KEY is correct and starts with `sk_test_`
- Look at Stripe Dashboard → Logs for errors
- Make sure you're using test keys for test mode

---

## Costs

### Free Tier (What You're On Now):

- **Supabase:** Free up to 500MB database + 50,000 requests/month
- **Render:** Free tier available (sleeps after 15min of inactivity)
- **Vercel:** Free unlimited for personal projects
- **Stripe:** Free (only pay 2.7% + 5¢ when processing real payments)

**Total: $0/month** (until you outgrow free tiers)

### Paid Tier (When You Scale):

- **Supabase Pro:** $25/month (more database + no pausing)
- **Render Starter:** $7/month (no sleep, always on)
- **Vercel:** Free forever for non-commercial
- **Stripe:** Same rates

**Total: ~$32/month**

---

## Support

- **API Issues:** Check `https://your-api.onrender.com/docs` for endpoint docs
- **Code Issues:** See GitHub repo issues
- **Questions:** See QUICK_START.md and README.md

---

**🎊 Congratulations! Your POS is live!**

You can now:
- Access it from anywhere
- Process real payments
- Build your BarberScore
- Unlock procurement tiers

Share your Vercel URL with barbers and start onboarding!
