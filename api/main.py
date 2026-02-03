"""
BarberScore POS API
Main FastAPI application
"""

from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import sys
import os
import stripe

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from api.config import get_settings
from api.routers import pos, eligibility, procurement, auth, stripe_connect

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
app.include_router(stripe_connect.router)
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
