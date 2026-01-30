# Deploy BarberScore POS Backend to Railway

## Step-by-Step Deployment Guide

### 1. Prerequisites
- GitHub account
- Railway account (sign up at https://railway.app - free tier available)
- Your backend code pushed to GitHub (✅ Already done!)

### 2. Deploy to Railway (5 minutes)

#### A. Create Railway Project

1. Go to https://railway.app
2. Click **"Start a New Project"**
3. Select **"Deploy from GitHub repo"**
4. Authorize Railway to access your GitHub
5. Select your repository: `williamcoggins-rgb/pos`
6. Railway will detect your backend automatically

#### B. Add PostgreSQL Database

1. In your Railway project, click **"+ New"**
2. Select **"Database"** → **"PostgreSQL"**
3. Railway will create a PostgreSQL instance and automatically set `DATABASE_URL`

#### C. Configure Environment Variables

1. Click on your backend service
2. Go to **"Variables"** tab
3. Add these variables:

```
DATABASE_URL (already set by Railway automatically)
NODE_ENV=production
JWT_SECRET=your-super-secret-random-string-change-this
CORS_ORIGIN=https://pos-ivrc.vercel.app
PORT=3000
```

**Generate a secure JWT_SECRET:**
```bash
# Run this locally to generate a random secret
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

#### D. Configure Build Settings

1. Go to **"Settings"** tab
2. Set **Root Directory**: `backend`
3. Set **Build Command**: `npm install`
4. Set **Start Command**: `npm start`

#### E. Run Database Migration

1. Click on **PostgreSQL** service
2. Click **"Data"** tab → **"Query"**
3. Copy contents of `/home/user/pos/backend/schema.sql`
4. Paste and click **"Run Query"**

Or use Railway CLI:
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Link to your project
railway link

# Run migration
railway run psql $DATABASE_URL -f schema.sql
```

#### F. Deploy!

1. Railway will automatically deploy when you push to GitHub
2. Your API will be available at: `https://your-project.up.railway.app`
3. Test health endpoint: `https://your-project.up.railway.app/health`

### 3. Get Your API URL

1. In Railway project, click your backend service
2. Go to **"Settings"** → **"Domains"**
3. Click **"Generate Domain"**
4. Copy the URL (e.g., `https://barberscore-pos-production.up.railway.app`)

### 4. Update Frontend CORS

Add your Railway URL to backend CORS:
```env
CORS_ORIGIN=https://pos-ivrc.vercel.app,http://localhost:3000
```

### 5. Test Your API

```bash
# Health check
curl https://your-project.up.railway.app/health

# Register a shop
curl -X POST https://your-project.up.railway.app/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "owner@example.com",
    "password": "secure123",
    "shopName": "Elite Cuts",
    "ownerName": "John Doe",
    "phone": "(555) 123-4567"
  }'
```

---

## Alternative: Deploy to Render

### 1. Create Render Account
- Go to https://render.com
- Sign up with GitHub

### 2. Create PostgreSQL Database
1. Click **"New +"** → **"PostgreSQL"**
2. Name: `barberscore-pos-db`
3. Choose free tier
4. Click **"Create Database"**
5. Copy the **Internal Database URL**

### 3. Create Web Service
1. Click **"New +"** → **"Web Service"**
2. Connect your GitHub repo
3. Configure:
   - **Name**: `barberscore-pos-api`
   - **Root Directory**: `backend`
   - **Environment**: `Node`
   - **Build Command**: `npm install`
   - **Start Command**: `npm start`

### 4. Add Environment Variables
```
DATABASE_URL=<paste Internal Database URL>
NODE_ENV=production
JWT_SECRET=<generate random secret>
CORS_ORIGIN=https://pos-ivrc.vercel.app
PORT=3000
```

### 5. Run Migration
1. Go to PostgreSQL database in Render
2. Click **"Connect"** → **"External Connection"**
3. Use credentials to connect via `psql` locally:
```bash
psql <external-database-url> -f backend/schema.sql
```

### 6. Deploy
- Render will auto-deploy on every push to GitHub
- Your API will be at: `https://barberscore-pos-api.onrender.com`

---

## Troubleshooting

### "Cannot connect to database"
- Check `DATABASE_URL` is set correctly
- Verify database migration ran successfully
- Check database logs in Railway/Render

### "CORS error"
- Add your frontend URL to `CORS_ORIGIN` environment variable
- Include protocol: `https://` not just domain

### "Port already in use"
- Railway automatically sets `PORT` - don't override
- Use `process.env.PORT || 3000` in code (already done ✅)

### "Migration failed"
- Check PostgreSQL version is 14+
- Run migration queries one at a time
- Check for syntax errors in `schema.sql`

---

## Post-Deployment Checklist

✅ Health endpoint returns 200: `GET /health`
✅ Can register new user: `POST /api/auth/register`
✅ Can login: `POST /api/auth/login`
✅ Database has all tables (check with `\dt` in psql)
✅ CORS allows your frontend domain
✅ Environment variables are set
✅ Auto-deploy on git push works

---

## Monitoring

### Railway
- View logs in **"Deployments"** tab
- Monitor usage in **"Metrics"** tab
- Free tier: 500 hours/month

### Render
- View logs in **"Logs"** tab
- Monitor in **"Metrics"** tab
- Free tier: Auto-sleep after 15 min inactivity

---

## Cost Estimates

### Railway (Free Tier)
- $0/month for 500 execution hours
- $0.10/GB RAM after free hours
- PostgreSQL: $5/month (500MB free storage)

### Render (Free Tier)
- $0/month for web services (with sleep)
- PostgreSQL: $0/month (90 days, then $7/month)

### Upgrade When You Need:
- Multiple shops (5+)
- 1000+ transactions/day
- Real-time sync across devices
- Advanced analytics

---

## Next Steps After Deployment

1. ✅ Backend deployed and accessible
2. Update frontend to call API (see `FRONTEND_API_INTEGRATION.md`)
3. Migrate localStorage data (see `MIGRATION.md`)
4. Test registration → login → create transaction flow
5. Monitor logs for errors
6. Set up automatic backups (Railway/Render both support this)

---

## Support

Railway Discord: https://discord.gg/railway
Render Status: https://status.render.com
PostgreSQL Docs: https://www.postgresql.org/docs/

Your backend is ready! 🚀
