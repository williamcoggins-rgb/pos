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
from api.routers import pos, eligibility, procurement, auth, stripe_connect, catalog

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

# CORS middleware - use regex to allow all vercel.app subdomains
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_origin_regex=r"https://.*\.vercel\.app",
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
    """Handle uncaught exceptions - don't leak internal details in production"""
    import logging
    logging.exception(f"Unhandled error on {request.method} {request.url.path}")
    content = {"error": "Internal server error"}
    if settings.DEBUG:
        content["detail"] = str(exc)
    return JSONResponse(status_code=500, content=content)


# Include routers
app.include_router(auth.router)
app.include_router(stripe_connect.router)
app.include_router(pos.router)
app.include_router(eligibility.router)
app.include_router(procurement.router)
app.include_router(catalog.router)


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
    Handle Stripe webhook events.
    Records events in the event store for audit trail and score updates.
    """
    import json as json_module
    import logging
    from event_store import Event, EventType, generate_event_id, utc_now
    from api.database import get_cloud_store

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
        event = json_module.loads(payload)

    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})
    stripe_event_id = event.get("id", "")
    cloud_store = get_cloud_store()

    if event_type == "payment_intent.succeeded":
        payment_intent_id = data.get("id")
        amount = data.get("amount", 0)
        sale_id = data.get("metadata", {}).get("sale_id", payment_intent_id)

        store_event = Event(
            event_id=generate_event_id(),
            event_type=EventType.PAYMENT_CAPTURED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "payment_intent_id": payment_intent_id,
                "sale_id": sale_id,
                "amount": {"amount_minor": amount, "currency": "USD"},
                "tip": {"amount_minor": 0, "currency": "USD"},
                "captured_at": utc_now(),
                "source": "stripe_webhook",
            },
            created_at=utc_now(),
            idempotency_key=f"stripe_webhook_{stripe_event_id}",
            metadata={"stripe_event_id": stripe_event_id},
        )
        cloud_store.append(store_event)
        logging.info(f"Payment succeeded: {payment_intent_id} for {amount} cents")

    elif event_type == "payment_intent.payment_failed":
        payment_intent_id = data.get("id")
        error_msg = data.get("last_payment_error", {}).get("message", "Unknown error")
        sale_id = data.get("metadata", {}).get("sale_id", payment_intent_id)

        store_event = Event(
            event_id=generate_event_id(),
            event_type=EventType.PAYMENT_FAILED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "payment_intent_id": payment_intent_id,
                "sale_id": sale_id,
                "error": error_msg,
                "source": "stripe_webhook",
            },
            created_at=utc_now(),
            idempotency_key=f"stripe_webhook_{stripe_event_id}",
            metadata={"stripe_event_id": stripe_event_id},
        )
        cloud_store.append(store_event)
        logging.warning(f"Payment failed: {payment_intent_id} - {error_msg}")

    elif event_type == "charge.refunded":
        charge_id = data.get("id")
        amount_refunded = data.get("amount_refunded", 0)
        payment_intent_id = data.get("payment_intent")
        sale_id = data.get("metadata", {}).get("sale_id", charge_id)

        store_event = Event(
            event_id=generate_event_id(),
            event_type=EventType.REFUND_PROCESSED,
            aggregate_id=sale_id,
            aggregate_type="sale",
            payload={
                "charge_id": charge_id,
                "payment_intent_id": payment_intent_id,
                "sale_id": sale_id,
                "amount_refunded": {"amount_minor": amount_refunded, "currency": "USD"},
                "source": "stripe_webhook",
            },
            created_at=utc_now(),
            idempotency_key=f"stripe_webhook_{stripe_event_id}",
            metadata={"stripe_event_id": stripe_event_id},
        )
        cloud_store.append(store_event)
        logging.info(f"Refund processed: {charge_id} for {amount_refunded} cents")

    elif event_type == "charge.dispute.created":
        charge_id = data.get("charge")
        amount = data.get("amount", 0)
        reason = data.get("reason", "")

        store_event = Event(
            event_id=generate_event_id(),
            event_type=EventType.RISK_FLAG_RAISED,
            aggregate_id=charge_id,
            aggregate_type="dispute",
            payload={
                "charge_id": charge_id,
                "amount": {"amount_minor": amount, "currency": "USD"},
                "reason": reason,
                "dispute_status": "open",
                "source": "stripe_webhook",
            },
            created_at=utc_now(),
            idempotency_key=f"stripe_webhook_{stripe_event_id}",
            metadata={"stripe_event_id": stripe_event_id},
        )
        cloud_store.append(store_event)
        logging.warning(f"Dispute created: {charge_id} for {amount} cents - {reason}")

    elif event_type == "charge.dispute.closed":
        charge_id = data.get("charge")
        status = data.get("status", "")

        store_event = Event(
            event_id=generate_event_id(),
            event_type=EventType.RISK_FLAG_RAISED,
            aggregate_id=charge_id,
            aggregate_type="dispute",
            payload={
                "charge_id": charge_id,
                "dispute_status": status,
                "source": "stripe_webhook",
            },
            created_at=utc_now(),
            idempotency_key=f"stripe_webhook_{stripe_event_id}",
            metadata={"stripe_event_id": stripe_event_id},
        )
        cloud_store.append(store_event)
        logging.info(f"Dispute closed: {charge_id} - {status}")

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
