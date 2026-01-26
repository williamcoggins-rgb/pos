# 🚀 Deploy POS UI to Vercel - Step by Step

This guide will get your POS UI deployed to Vercel in 10 minutes.

---

## Prerequisites

1. **GitHub account** - To push your code
2. **Vercel account** - Free at [vercel.com](https://vercel.com)

---

## Step 1: Push Code to GitHub (2 minutes)

If you haven't already pushed to GitHub:

```bash
cd /home/user/pos

# Make sure you're on the right branch
git checkout claude/pos-barberscore-integration-tkqbD

# Push to GitHub
git push origin claude/pos-barberscore-integration-tkqbD
```

---

## Step 2: Sign Up for Vercel (1 minute)

1. Go to [vercel.com](https://vercel.com)
2. Click **"Sign Up"**
3. Choose **"Continue with GitHub"**
4. Authorize Vercel to access your repositories

---

## Step 3: Import Project (2 minutes)

1. In Vercel dashboard, click **"Add New"** → **"Project"**

2. Find your `pos` repository and click **"Import"**

3. **Configure Project:**
   - **Framework Preset:** Other (no framework)
   - **Root Directory:** Leave as `.` (root)
   - **Build Command:** Leave empty or put: `echo "Static site"`
   - **Output Directory:** `web`
   - **Install Command:** Leave empty

4. Click **"Deploy"**

---

## Step 4: Wait for Deployment (2 minutes)

Vercel will:
- Build your project
- Deploy to a `.vercel.app` URL
- Show you the deployment status

You'll see: `✅ Building... → ✅ Deployed`

---

## Step 5: Visit Your POS!

Your app will be live at:
```
https://your-project-name.vercel.app
```

Click the link to see your POS interface!

---

## Common Errors & Fixes

### Error: "No Output Directory Found"

**Fix:** Make sure `vercel.json` in root has:
```json
{
  "outputDirectory": "web"
}
```

This tells Vercel where to find your files.

### Error: "404 Page Not Found"

**Fix:** The rewrite rules need to be set correctly. Check `vercel.json`:
```json
{
  "rewrites": [
    { "source": "/", "destination": "/app.html" }
  ]
}
```

### Error: "Failed to Load Resource"

**Cause:** API not deployed yet or wrong API URL

**Fix:**
1. Deploy your API to Render first (see `DEPLOYMENT.md`)
2. Update `web/api-client.js` line 5 with your API URL:
   ```javascript
   const API_URL = window.location.hostname === 'localhost'
       ? 'http://localhost:8000'
       : 'https://YOUR-API.onrender.com';
   ```
3. Redeploy to Vercel

### Error: "Authentication Failed"

**Cause:** API isn't configured or isn't deployed

**Fix:** Deploy your API first following `DEPLOYMENT.md`, then try the UI

### Error: "Build Failed"

**Cause:** Vercel is trying to build something it doesn't need to

**Fix:**
1. Go to Project Settings → General
2. Set **Build Command** to: `echo "No build needed"`
3. Set **Output Directory** to: `web`
4. Redeploy

---

## Using Custom Domain (Optional)

1. Go to your project in Vercel
2. Click **"Settings"** → **"Domains"**
3. Add your domain (e.g., `mypos.com`)
4. Follow Vercel's DNS instructions
5. Wait for DNS propagation (~5-10 minutes)

---

## Alternative: Deploy via CLI (Advanced)

```bash
# Install Vercel CLI
npm install -g vercel

# Login
vercel login

# Deploy
cd /home/user/pos
vercel --prod

# Follow prompts:
# - Set root directory: web
# - Override settings: Yes
# - Output directory: . (current dir, since we're in web/)
```

---

## Connecting to Your API

After deploying the UI, you need to:

1. **Deploy API to Render** (see `DEPLOYMENT.md`)
2. **Get your API URL** (e.g., `https://barberscore-api.onrender.com`)
3. **Update `web/api-client.js`:**
   ```javascript
   const API_URL = window.location.hostname === 'localhost'
       ? 'http://localhost:8000'
       : 'https://YOUR-ACTUAL-API-URL.onrender.com';
   ```
4. **Push changes and redeploy:**
   ```bash
   git add web/api-client.js
   git commit -m "Update production API URL"
   git push
   ```
   Vercel will auto-deploy the update!

---

## Automatic Deployments

Once connected to GitHub, Vercel automatically deploys:
- **Every push to main** → Production deployment
- **Every push to other branches** → Preview deployment
- **Every pull request** → Preview deployment with unique URL

---

## Environment Variables (Not Needed for UI)

The UI doesn't need environment variables because:
- It's a static site
- API URL is in `api-client.js`
- Auth tokens are stored in browser localStorage

Your **API** needs environment variables (Supabase, Stripe, etc.)

---

## Monitoring & Logs

1. Go to your project in Vercel
2. Click **"Deployments"** to see all deployments
3. Click any deployment → **"View Function Logs"**
4. Check for errors in browser console (F12)

---

## Testing Your Deployment

1. Visit: `https://your-project.vercel.app`
2. You should see the login/register screen
3. Try to register (will fail if API not deployed yet)
4. Check browser console (F12) for API errors

---

## Complete Flow (UI + API)

For the complete working system:

1. ✅ **Deploy API to Render** (`DEPLOYMENT.md` Steps 1-3)
2. ✅ **Deploy UI to Vercel** (this guide)
3. ✅ **Update API URL** in `api-client.js`
4. ✅ **Test end-to-end** (register → login → process sale)

---

## Rollback a Deployment

If something breaks:

1. Go to Vercel dashboard → **"Deployments"**
2. Find a working previous deployment
3. Click **"..."** → **"Promote to Production"**
4. Instant rollback! ✅

---

## URLs After Deployment

Save these:
- **Production UI:** https://your-project.vercel.app
- **Vercel Dashboard:** https://vercel.com/dashboard
- **GitHub Repo:** https://github.com/your-username/pos
- **API (Render):** https://your-api.onrender.com

---

## Support

**Still getting errors?**

1. Check the exact error message in Vercel logs
2. Check browser console (F12) for client-side errors
3. Verify your API is deployed and working (visit: `https://your-api.onrender.com/health`)
4. Make sure `vercel.json` exists in project root
5. Confirm `outputDirectory` is set to `web`

**Common mistakes:**
- ❌ Not deploying API first
- ❌ Wrong API URL in api-client.js
- ❌ Missing vercel.json configuration
- ❌ Wrong output directory setting

---

**🎉 Your POS UI is now live on Vercel!**

Next: Deploy your API to Render (see `DEPLOYMENT.md`)
