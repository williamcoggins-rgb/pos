# 🔧 Fix Vercel Deployment - Simple Steps

Your new POS is ready, but Vercel is looking at the wrong branch. Here's how to fix it (takes 2 minutes):

---

## Step 1: Open Vercel

1. Go to: **https://vercel.com/dashboard**
2. Sign in if needed
3. Click on your **"pos"** project

---

## Step 2: Change the Branch

1. Click **"Settings"** (in the top menu)
2. Click **"Git"** (in the left sidebar)
3. Look for **"Production Branch"**
4. Change it from `main` or `master` to:
   ```
   claude/pos-barberscore-integration-tkqbD
   ```
5. Click **"Save"**

---

## Step 3: Redeploy

1. Click **"Deployments"** (in the top menu)
2. You'll see a list of deployments
3. Click the **"..."** button (three dots) on the top deployment
4. Click **"Redeploy"**
5. Wait 1-2 minutes for it to finish

---

## Step 4: See Your New POS!

1. Go to your Vercel URL (like `https://your-project.vercel.app`)
2. Press **Ctrl + Shift + R** (Windows) or **Cmd + Shift + R** (Mac) to hard refresh
3. You should now see:
   - A dark background with animated gradient
   - 💈 Barber icon
   - "BarberScore POS" title
   - "Get Started" button

---

## ✅ What You Should See

**OLD (if fix didn't work):**
- Bright purple/pink checkout screen
- "BarberScore POS" at top
- Service buttons already showing

**NEW (if fix worked):**
- Dark background with subtle animation
- Welcome screen with features list
- "Get Started" button
- Modern glassmorphism design

---

## 🆘 Still Not Working?

If you still see the old version after following the steps above, there are two other quick fixes:

### Option A: Tell me what you see
Just tell me: "I followed the steps but I still see [describe what you see]" and I'll diagnose it further.

### Option B: Alternative deployment
I can set up a different deployment method that doesn't require branch configuration.

---

## 📸 Visual Guide

When you get to the Git settings in Vercel, you're looking for a field that says:

```
Production Branch: [main          ▼]
```

Change it to:
```
Production Branch: [claude/pos-barberscore-integration-tkqbD]
```

Then scroll down and click the **Save** button.

---

**That's it!** Once you save and redeploy, Vercel will use the new code with all your requested features:
- ✅ User signup/onboarding
- ✅ 4-digit passcode
- ✅ Add your own services
- ✅ Modern 2026 design
- ✅ Checkout logging

Let me know if you get stuck on any step!
