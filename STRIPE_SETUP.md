# Stripe Payment Integration Setup Guide

## What is Stripe?

Stripe is a payment processor that allows you to accept credit cards, debit cards, Apple Pay, Google Pay, and more. It's trusted by millions of businesses worldwide.

## Benefits

- **Accept all major cards**: Visa, Mastercard, Amex, Discover
- **Apple Pay & Google Pay**: Tap-to-pay from phones
- **Automatic deposits**: Money goes directly to your bank account
- **Secure**: Stripe handles all security (PCI compliant)
- **Low fees**: 2.9% + $0.30 per transaction (standard pricing)

## Setup Steps

### Step 1: Create a Stripe Account

1. Go to https://stripe.com
2. Click **"Start now"** or **"Sign up"**
3. Enter your email and create a password
4. Fill in your business information:
   - Business name (your shop name)
   - Business type (Sole proprietorship or LLC)
   - Your personal info
   - Bank account (where you want money deposited)

### Step 2: Get Your API Keys

Once you're logged into Stripe:

1. Click **"Developers"** in the top menu
2. Click **"API keys"** in the left sidebar
3. You'll see two keys:
   - **Publishable key** (starts with `pk_test_` or `pk_live_`)
   - **Secret key** (starts with `sk_test_` or `sk_live_`)

**Important:**
- Use **Test keys** (`pk_test_` and `sk_test_`) while testing
- Use **Live keys** (`pk_live_` and `sk_live_`) when you're ready to accept real payments

### Step 3: Add Keys to Railway

1. Go to your Railway dashboard
2. Click on your **"pos"** service (backend)
3. Click on **"Variables"** tab
4. Click **"New Variable"**
5. Add these two variables:

   **Variable 1:**
   - Name: `STRIPE_SECRET_KEY`
   - Value: `sk_test_YOUR_KEY_HERE` (paste your secret key)

   **Variable 2:**
   - Name: `STRIPE_PUBLISHABLE_KEY`
   - Value: `pk_test_YOUR_KEY_HERE` (paste your publishable key)

6. Railway will automatically restart your backend with the new keys

### Step 4: Update Frontend

1. Open `web/stripe-payment.html` in your code
2. Find this line (around line 198):
   ```javascript
   const STRIPE_PUBLISHABLE_KEY = 'pk_test_YOUR_STRIPE_KEY';
   ```
3. Replace `pk_test_YOUR_STRIPE_KEY` with your actual publishable key
4. Save and push to GitHub (Vercel will auto-deploy)

### Step 5: Test Payment

**Using Test Mode:**

Stripe provides test card numbers that work in test mode:

- **Success**: `4242 4242 4242 4242`
- **Decline**: `4000 0000 0000 0002`
- **Requires 3D Secure**: `4000 0025 0000 3155`

Use any future expiration date (e.g., 12/34) and any 3-digit CVC (e.g., 123).

**Test it:**
1. Visit `https://pos-ivrc.vercel.app/stripe-payment.html?amount=10.00`
2. Enter customer info
3. Use test card: `4242 4242 4242 4242`
4. Expiration: `12/34`, CVC: `123`, ZIP: `12345`
5. Click "Pay Now"
6. Should see success message!

### Step 6: Go Live

When you're ready to accept real payments:

1. In Stripe dashboard, click **"Activate account"**
2. Complete the activation (verify identity, add business details)
3. Get your **Live API keys** (they start with `pk_live_` and `sk_live_`)
4. Replace the **Test keys** with **Live keys** in Railway and frontend
5. Now real cards will be charged!

## How Payment Flow Works

### Current Workflow:

**Before Stripe:**
1. Customer pays with their card through your card reader
2. You manually enter the sale in POS
3. POS just records the transaction

**With Stripe:**
1. Customer is ready to pay
2. You enter amount in POS
3. POS opens Stripe payment page
4. Customer enters their card info
5. Stripe processes payment automatically
6. POS receives confirmation and creates transaction record
7. Money goes to your bank account in 2 business days

## Integration with Your POS

### Backend API Endpoints

Your backend now has these payment endpoints:

- `POST /api/payments/create-payment-intent` - Start a payment
- `POST /api/payments/confirm-payment` - Confirm payment and create transaction
- `GET /api/payments/payment-status/:id` - Check payment status
- `POST /api/payments/refund` - Refund a payment

### Frontend Usage

**Option 1: Standalone Payment Page**
```
https://pos-ivrc.vercel.app/stripe-payment.html?amount=25.00
```

**Option 2: Integrate into POS**

Add a "Pay with Stripe" button in your POS that:
1. Calculates the total
2. Opens the payment page with the amount
3. Returns to POS when complete

## Fees

Standard Stripe pricing:
- **2.9% + $0.30** per successful transaction
- No monthly fees
- No setup fees
- No hidden fees

Example:
- $20 haircut → You pay $0.88 in fees → You receive $19.12
- $50 service → You pay $1.75 in fees → You receive $48.25

## Security

- Stripe is **PCI Level 1 certified** (highest security standard)
- Card numbers are **never stored** on your server
- All payments are **encrypted**
- **Fraud detection** built-in
- **3D Secure** for extra protection

## Support

- **Stripe Support**: https://support.stripe.com
- **Test Cards**: https://stripe.com/docs/testing
- **Dashboard**: https://dashboard.stripe.com

## Next Steps

1. Create Stripe account
2. Get API keys
3. Add keys to Railway
4. Update frontend with publishable key
5. Test with test cards
6. When ready, switch to live keys

**Need help?** Ask me any questions about the setup!
