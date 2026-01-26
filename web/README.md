# BarberScore POS - Frontend

Modern POS interface with Square meets Footlocker design aesthetic.

## Files

- **app.html** - Main POS application (production)
- **api-client.js** - API wrapper for backend communication
- **styles.css** - Complete stylesheet
- **vercel.json** - Vercel deployment configuration
- **index.html** - Original demo (reference only)

## Quick Start

### Local Development

```bash
# From project root
cd web
python -m http.server 8080

# Open: http://localhost:8080/app.html
```

### Production Deployment

See `../VERCEL_DEPLOY.md` for complete Vercel deployment guide.

**Quick deploy:**
```bash
vercel --prod
```

## Configuration

### API URL

Edit `api-client.js` line 3-5 to set your production API:

```javascript
const API_URL = window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : 'https://YOUR-API-URL.onrender.com'; // ← Change this
```

## Features

✅ User authentication (register/login)
✅ Service selection with visual grid
✅ Shopping cart with real-time calculations
✅ Tax calculation (8% default)
✅ Payment processing (Stripe via API)
✅ Success/error animations
✅ BarberScore integration
✅ Responsive design
✅ Mobile-friendly

## Design

**Color Palette:**
- Black: `#1a1a1a` (primary background)
- Purple: `#8b5cf6` (accent, buttons)
- Neon Green: `#10b981` (success, money)
- White: `#ffffff` (text)
- Gray: `#2a2a2a` (cards, inputs)

**Typography:**
- Font: System UI / -apple-system
- Weights: 400 (regular), 500 (medium), 600 (semibold), 700 (bold)

**Layout:**
- Left side: Service selection grid
- Right side: Shopping cart + checkout
- Top: Header with shop name + logout
- Mobile: Stacked layout

## Dependencies

**Runtime:**
- React 18 (via CDN)
- ReactDOM 18 (via CDN)
- Babel Standalone (for JSX transformation)

**No build step required!** Everything loads from CDN.

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (iOS Safari, Chrome Mobile)

## API Integration

This frontend connects to the FastAPI backend:

**Required endpoints:**
- `POST /api/auth/register` - Create account
- `POST /api/auth/login` - Authenticate
- `POST /api/pos/sales` - Create sale
- `POST /api/pos/sales/{id}/items` - Add items
- `POST /api/pos/sales/{id}/tax` - Calculate tax
- `POST /api/pos/sales/{id}/payment` - Process payment
- `GET /api/eligibility/score/{barber_id}` - Get score
- `POST /api/eligibility/score/{barber_id}/update` - Update score

See API docs: `http://localhost:8000/docs`

## Authentication Flow

1. User enters email/password
2. Frontend calls `/api/auth/register` or `/api/auth/login`
3. Backend returns JWT token
4. Frontend stores token in `localStorage`
5. All subsequent requests include: `Authorization: Bearer {token}`

## State Management

**localStorage keys:**
- `auth_token` - JWT authentication token
- `barber_id` - Current barber's ID
- `shop_name` - Shop name for display

**React state:**
- `user` - Current authenticated user
- `saleId` - Active sale ID
- `cart` - Array of cart items
- `subtotal`, `tax`, `total` - Calculated amounts
- `processing` - Payment in progress flag
- `success` - Payment success flag
- `error` - Error message (if any)

## Testing

### Manual Testing

1. Open `app.html` in browser
2. Register a new account
3. Add services to cart
4. Process payment
5. Check browser console for API calls
6. Verify success animation

### Check API Connection

Open browser console (F12):

```javascript
// Check API client
const api = new APIClient();
console.log(api.isAuthenticated());

// Test login
await api.login('test@example.com', 'password');

// Test sale creation
const sale = await api.createSale();
console.log(sale);
```

## Troubleshooting

### "Failed to create sale"
- Check API is running: `http://localhost:8000/health`
- Check browser console for CORS errors
- Verify JWT token is valid (check localStorage)

### "Login failed"
- Verify API is configured with Supabase
- Check email/password are correct
- Check browser console for specific error

### "Payment failed"
- Verify Stripe is configured in API
- Check API logs for Stripe errors
- Ensure sale has items and tax calculated

### CORS errors
- API must allow your domain in CORS settings
- Check `api/main.py` CORS configuration
- For local dev, API should allow `localhost`

## Performance

**Initial load:**
- HTML: ~18KB
- CSS: ~11KB
- JS: ~4KB
- React (CDN): ~130KB (cached)
- Total: ~160KB first load, ~33KB after caching

**Optimization:**
- Images: None (using emoji icons)
- Minification: Not needed for development
- CDN: React loaded from unpkg.com
- Caching: Browser caches all static assets

## Security

✅ JWT tokens stored in localStorage (httpOnly not possible for static sites)
✅ HTTPS required in production (enforced by Vercel)
✅ API handles all validation and authorization
✅ No sensitive data in frontend code
✅ CORS configured to restrict API access

**Note:** For production mobile apps, use secure storage (Keychain/Keystore)

## Deployment Checklist

Before deploying to production:

- [ ] Update API URL in `api-client.js`
- [ ] Verify API is deployed and accessible
- [ ] Test registration flow
- [ ] Test payment processing
- [ ] Check mobile responsiveness
- [ ] Verify CORS allows your domain
- [ ] Test error handling
- [ ] Configure custom domain (optional)

## Next Steps

1. Deploy API to Render (see `../DEPLOYMENT.md`)
2. Deploy UI to Vercel (see `../VERCEL_DEPLOY.md`)
3. Update API URL in production
4. Test end-to-end flow
5. Share URL with users!

## Support

- Main docs: `../README.md`
- Deployment guide: `../VERCEL_DEPLOY.md`
- API docs: `../QUICK_START.md`
- Architecture: `../docs/ARCHITECTURE.md`
