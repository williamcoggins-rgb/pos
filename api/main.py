"""
BarberScore POS API - Main application.
Single Stripe init. Webhooks write to event store. Clean router mounting.
"""

import json
import logging
import time
import sys
import os

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import stripe

# Ensure core modules are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from api.config import get_settings
from api.routers import pos, eligibility, procurement, auth, stripe_connect
from api.database import get_cloud_store
from event_store import Event, EventType, generate_event_id, utc_now

logger = logging.getLogger(__name__)
settings = get_settings()

# --- Stripe init (ONCE, here only) ---
if settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY

# --- App ---
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description="Event-sourced POS with BarberScore eligibility and procurement",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ALLOW_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = str(time.time() - start_time)
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


# --- Routers ---
app.include_router(auth.router)
app.include_router(stripe_connect.router)
app.include_router(pos.router)
app.include_router(eligibility.router)
app.include_router(procurement.router)


# --- Health / Root ---
@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.API_VERSION}


@app.get("/")
async def root():
    return {
        "message": "BarberScore POS API",
        "version": settings.API_VERSION,
        "docs": "/docs",
        "health": "/health",
    }


# --- Stripe config (publishable key safe to expose) ---
@app.get("/api/stripe/config")
async def get_stripe_config():
    return {"publishableKey": settings.STRIPE_PUBLISHABLE_KEY}


# --- Stripe Webhook (writes to event store, not just print) ---
@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    """
    Handle Stripe webhook events.
    Records events in the event store so BarberScore stays accurate.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

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
        event = json.loads(payload)

    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})
    cloud_store = get_cloud_store()

    if event_type == "payment_intent.succeeded":
        cloud_store.append(Event(
            event_id=generate_event_id(),
            event_type=EventType.PAYMENT_CAPTURED,
            aggregate_id=data.get("id", ""),
            aggregate_type="payment",
            payload={
                "payment_id": data.get("id"),
                "amount": {"amount_minor": data.get("amount", 0), "currency": "USD"},
                "source": "stripe_webhook",
            },
            created_at=utc_now(),
            idempotency_key=f"webhook_{data.get('id')}",
        ))

    elif event_type == "payment_intent.payment_failed":
        cloud_store.append(Event(
            event_id=generate_event_id(),
            event_type=EventType.PAYMENT_FAILED,
            aggregate_id=data.get("id", ""),
            aggregate_type="payment",
            payload={
                "payment_id": data.get("id"),
                "error": data.get("last_payment_error", {}).get("message", "Unknown"),
                "source": "stripe_webhook",
            },
            created_at=utc_now(),
            idempotency_key=f"webhook_fail_{data.get('id')}",
        ))

    elif event_type == "charge.refunded":
        cloud_store.append(Event(
            event_id=generate_event_id(),
            event_type=EventType.REFUND_PROCESSED,
            aggregate_id=data.get("id", ""),
            aggregate_type="refund",
            payload={
                "charge_id": data.get("id"),
                "amount_refunded": data.get("amount_refunded", 0),
                "source": "stripe_webhook",
            },
            created_at=utc_now(),
            idempotency_key=f"webhook_refund_{data.get('id')}",
        ))

    elif event_type == "charge.dispute.created":
        cloud_store.append(Event(
            event_id=generate_event_id(),
            event_type=EventType.RISK_FLAG_RAISED,
            aggregate_id=data.get("charge", ""),
            aggregate_type="dispute",
            payload={
                "charge_id": data.get("charge"),
                "amount": data.get("amount", 0),
                "reason": data.get("reason", ""),
                "source": "stripe_webhook",
            },
            created_at=utc_now(),
            idempotency_key=f"webhook_dispute_{data.get('id')}",
        ))

    logger.info("Stripe webhook processed: %s", event_type)
    return {"received": True, "type": event_type}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
