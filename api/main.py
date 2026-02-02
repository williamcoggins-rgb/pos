"""
BarberScore POS API
Main FastAPI application
"""

from fastapi import FastAPI, Request, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional
import time
import sys
import os
import stripe
import httpx

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from api.config import get_settings
from api.routers import pos, eligibility, procurement, auth

settings = get_settings()

# Initialize Stripe
if settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY

# Create FastAPI app
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description="Event-sourced POS with BarberScore eligibility and procurement",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add processing time to response headers"""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions"""
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )


# Include routers
app.include_router(auth.router)
app.include_router(pos.router)
app.include_router(eligibility.router)
app.include_router(procurement.router)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": settings.API_VERSION,
    }


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "BarberScore POS API",
        "version": settings.API_VERSION,
        "docs": "/docs",
        "health": "/health",
    }


# Stripe Webhook endpoint
@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    """
    Handle Stripe webhook events
    Processes payment confirmations, failures, disputes, and refunds
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    # Verify webhook signature if secret is configured
    if settings.STRIPE_WEBHOOK_SECRET and sig_header:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid signature")
    else:
        # For testing without signature verification
        import json
        event = json.loads(payload)

    # Handle different event types
    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})

    if event_type == "payment_intent.succeeded":
        # Payment was successful
        payment_intent_id = data.get("id")
        amount = data.get("amount")
        print(f"Payment succeeded: {payment_intent_id} for {amount} cents")

    elif event_type == "payment_intent.payment_failed":
        # Payment failed
        payment_intent_id = data.get("id")
        error = data.get("last_payment_error", {}).get("message", "Unknown error")
        print(f"Payment failed: {payment_intent_id} - {error}")

    elif event_type == "charge.refunded":
        # Refund was processed
        charge_id = data.get("id")
        amount_refunded = data.get("amount_refunded")
        print(f"Refund processed: {charge_id} for {amount_refunded} cents")

    elif event_type == "charge.dispute.created":
        # Dispute/chargeback created
        charge_id = data.get("charge")
        amount = data.get("amount")
        reason = data.get("reason")
        print(f"Dispute created: {charge_id} for {amount} cents - {reason}")

    elif event_type == "charge.dispute.closed":
        # Dispute resolved
        charge_id = data.get("charge")
        status = data.get("status")
        print(f"Dispute closed: {charge_id} - {status}")

    return {"received": True, "type": event_type}


# Stripe config endpoint (for frontend to get publishable key)
@app.get("/api/stripe/config")
async def get_stripe_config():
    """
    Get Stripe configuration for frontend
    Returns the publishable key (safe to expose)
    """
    return {
        "publishableKey": settings.STRIPE_PUBLISHABLE_KEY,
    }


# ============================================================================
# Stripe Connect Endpoints
# ============================================================================

async def get_current_user_from_token(authorization: Optional[str] = Header(None)):
    """Extract user info from JWT token"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.split(" ")[1]

    from api.services.auth_service import AuthService
    auth_service = AuthService()
    payload = auth_service.verify_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return {"user_id": user_id, "token": token}


async def get_barber_stripe_account(user_id: str, token: str) -> Optional[str]:
    """Get Stripe account ID from Supabase barbers table"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.SUPABASE_URL}/rest/v1/barbers?id=eq.{user_id}&select=stripe_account_id",
            headers={
                "apikey": settings.SUPABASE_KEY,
                "Authorization": f"Bearer {token}",
            }
        )

        if response.status_code != 200:
            return None

        barbers = response.json()
        if not barbers:
            return None

        return barbers[0].get("stripe_account_id")


async def save_barber_stripe_account(user_id: str, token: str, stripe_account_id: str):
    """Save Stripe account ID to Supabase barbers table"""
    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"{settings.SUPABASE_URL}/rest/v1/barbers?id=eq.{user_id}",
            headers={
                "apikey": settings.SUPABASE_KEY,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            },
            json={"stripe_account_id": stripe_account_id}
        )

        return response.status_code == 204


@app.get("/api/stripe/account-status")
async def get_stripe_account_status(user: dict = Depends(get_current_user_from_token)):
    """
    Check Stripe Connect account status for current user
    Returns whether they can accept payments and receive payouts
    """
    try:
        # Get existing Stripe account ID
        stripe_account_id = await get_barber_stripe_account(user["user_id"], user["token"])

        if not stripe_account_id:
            return {
                "has_account": False,
                "charges_enabled": False,
                "payouts_enabled": False,
                "details_submitted": False,
            }

        # Get account status from Stripe
        account = stripe.Account.retrieve(stripe_account_id)

        return {
            "has_account": True,
            "stripe_account_id": stripe_account_id,
            "charges_enabled": account.charges_enabled,
            "payouts_enabled": account.payouts_enabled,
            "details_submitted": account.details_submitted,
            "business_type": account.business_type,
        }

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/stripe/create-account-link")
async def create_stripe_account_link(user: dict = Depends(get_current_user_from_token)):
    """
    Create Stripe Connect onboarding link
    Creates a new Express account if needed, then returns onboarding URL
    """
    try:
        # Get existing Stripe account ID
        stripe_account_id = await get_barber_stripe_account(user["user_id"], user["token"])

        # If no account exists, create one
        if not stripe_account_id:
            account = stripe.Account.create(
                type="express",
                country="US",
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
                business_type="individual",
            )
            stripe_account_id = account.id

            # Save to Supabase
            await save_barber_stripe_account(user["user_id"], user["token"], stripe_account_id)
        else:
            # Check if already fully onboarded
            account = stripe.Account.retrieve(stripe_account_id)
            if account.charges_enabled and account.payouts_enabled:
                return {
                    "already_onboarded": True,
                    "charges_enabled": True,
                    "payouts_enabled": True,
                }

        # Create account link for onboarding
        # Use the frontend URL for return/refresh
        frontend_url = "https://pos-ruby-seven.vercel.app"

        account_link = stripe.AccountLink.create(
            account=stripe_account_id,
            refresh_url=f"{frontend_url}/pos-v4.html?stripe_refresh=true",
            return_url=f"{frontend_url}/pos-v4.html?stripe_success=true",
            type="account_onboarding",
        )

        return {
            "url": account_link.url,
            "stripe_account_id": stripe_account_id,
        }

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
