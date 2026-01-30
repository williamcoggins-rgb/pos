# 🚀 Quick Start - Deploy BarberScore POS Backend

Follow these steps to get your backend live in 10 minutes.

## ☑️ Deployment Checklist

### Step 1: Railway Account (2 minutes)
- [ ] Go to https://railway.app
- [ ] Click "Start a New Project"
- [ ] Login with GitHub
- [ ] Authorize Railway to access your repos

### Step 2: Create Project (3 minutes)
- [ ] Click "Deploy from GitHub repo"
- [ ] Select `williamcoggins-rgb/pos`
- [ ] Railway will auto-detect your backend
- [ ] Wait for initial build to complete

### Step 3: Add Database (1 minute)
- [ ] Click "+ New" in your project
- [ ] Select "Database" → "PostgreSQL"
- [ ] Railway automatically sets `DATABASE_URL`
- [ ] Wait for database to provision

### Step 4: Environment Variables (2 minutes)
- [ ] Click on your backend service
- [ ] Go to "Variables" tab
- [ ] Add these variables:

NODE_ENV=production
JWT_SECRET=<generate using command below>
CORS_ORIGIN=https://pos-ivrc.vercel.app

Generate JWT_SECRET:
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"

### Step 5: Configure Build (1 minute)
- [ ] Go to "Settings" tab
- [ ] Set "Root Directory": backend
- [ ] Set "Build Command": npm install
- [ ] Set "Start Command": npm start

### Step 6: Run Database Migration (2 minutes)
- [ ] Click on PostgreSQL service
- [ ] Click "Data" tab → "Query"
- [ ] Copy contents of backend/schema.sql
- [ ] Paste and run in Railway

### Step 7: Get Your API URL
- [ ] Click backend service → Settings → Domains
- [ ] Click "Generate Domain"
- [ ] Copy URL: https://xxxxx.up.railway.app

### Step 8: Test Deployment
cd /home/user/pos/backend
./test-deployment.sh

## ✅ Complete! Your API is live.

Next: Update web/api-service.js with your Railway URL
Then: Open web/migrate-data.html to migrate your data
