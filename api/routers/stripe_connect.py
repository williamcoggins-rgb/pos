"""
Stripe Connect API endpoints
Handles Stripe Connect onboarding for barbers to accept payments (step 2 of onboarding).

Handles real-world states that only exist in live mode:
- Account from test environment (mismatched keys)
- Pending Stripe verification (not instant like test mode)
- Expired onboarding links (user didn't finish)
- Account cleanup without delete (live mode doesn't allow delete)
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
import stripe
import httpx

from api.config import get_settings
from api.dependencies import get_current_user_id

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/stripe", tags=["Stripe Connect"])


async def get_barber_stripe_account(user_id: str) -> Optional[str]:
    """Get barber's stripe_account_id from Supabase"""
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        return None

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.SUPABASE_URL}/rest/v1/barbers?id=eq.{user_id}&select=stripe_account_id",
            headers={
                "apikey": settings.SUPABASE_KEY,
                "Authorization": f"Bearer {settings.SUPABASE_KEY}",
            }
        )

        if response.status_code != 200:
            return None

        barbers = response.json()
        if not barbers:
            return None

        return barbers[0].get("stripe_account_id")


async def save_barber_stripe_account(user_id: str, stripe_account_id: str) -> bool:
    """Save stripe_account_id to barber's Supabase record"""
    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"{settings.SUPABASE_URL}/rest/v1/barbers?id=eq.{user_id}",
            headers={
                "apikey": settings.SUPABASE_KEY,
                "Authorization": f"Bearer {settings.SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            },
            json={"stripe_account_id": stripe_account_id}
        )

        return response.status_code in (200, 204)


async def clear_barber_stripe_account(user_id: str) -> bool:
    """Clear a stale/invalid stripe_account_id from Supabase"""
    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"{settings.SUPABASE_URL}/rest/v1/barbers?id=eq.{user_id}",
            headers={
                "apikey": settings.SUPABASE_KEY,
                "Authorization": f"Bearer {settings.SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            },
            json={"stripe_account_id": None}
        )

        return response.status_code in (200, 204)


def _retrieve_account_safe(stripe_account_id: str) -> Optional[object]:
    """
    Retrieve a Stripe account, returning None if it doesn't exist.
    This handles the test-to-live key mismatch: an account created under
    sk_test_* doesn't exist when queried with sk_live_* (and vice versa).
    """
    try:
        return stripe.Account.retrieve(stripe_account_id)
    except stripe.error.PermissionError:
        # Account exists in a different environment (test vs live key mismatch)
        logger.warning("Stripe account %s not accessible (likely test/live mismatch)", stripe_account_id)
        return None
    except stripe.error.InvalidRequestError as e:
        if "No such account" in str(e):
            logger.warning("Stripe account %s does not exist (likely test/live mismatch)", stripe_account_id)
            return None
        raise


@router.get("/account-status")
async def get_account_status(user_id: str = Depends(get_current_user_id)):
    """
    Get the Stripe Connect account status for the current user.

    Returns all possible states:
    - no_account: User hasn't started Stripe Connect
    - stale_account: Stored account doesn't exist (test/live key mismatch) - cleared automatically
    - pending_onboarding: Account created but user hasn't completed Stripe's form
    - pending_verification: User submitted details, Stripe is reviewing
    - active: Charges and payouts enabled, ready to accept payments
    """
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    stripe_account_id = await get_barber_stripe_account(user_id)

    if not stripe_account_id:
        return {
            "status": "no_account",
            "has_account": False,
            "charges_enabled": False,
            "payouts_enabled": False,
            "onboarding_complete": False,
        }

    # Try to retrieve - handles test/live mismatch gracefully
    account = _retrieve_account_safe(stripe_account_id)

    if account is None:
        # Account doesn't exist in current Stripe environment.
        # Clear the stale ID so user can re-onboard.
        await clear_barber_stripe_account(user_id)
        logger.info("Cleared stale Stripe account for user %s", user_id)
        return {
            "status": "stale_account",
            "has_account": False,
            "charges_enabled": False,
            "payouts_enabled": False,
            "onboarding_complete": False,
            "message": "Your previous Stripe account was from a different environment. Please reconnect.",
        }

    charges = account.charges_enabled
    payouts = account.payouts_enabled
    submitted = account.details_submitted

    if charges and payouts:
        status = "active"
    elif submitted:
        status = "pending_verification"
    else:
        status = "pending_onboarding"

    return {
        "status": status,
        "has_account": True,
        "charges_enabled": charges,
        "payouts_enabled": payouts,
        "onboarding_complete": submitted,
        "account_id": stripe_account_id,
    }


@router.post("/create-account-link")
async def create_account_link(user_id: str = Depends(get_current_user_id)):
    """
    Create or resume Stripe Connect onboarding.

    Handles:
    - New user: creates Stripe account + onboarding link
    - Returning user with incomplete onboarding: generates fresh link
    - Stale account from test mode: clears it and creates new account
    - Already onboarded: returns status instead of link
    """
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    stripe_account_id = await get_barber_stripe_account(user_id)

    try:
        if stripe_account_id:
            # Verify the stored account still exists in current environment
            account = _retrieve_account_safe(stripe_account_id)

            if account is None:
                # Test/live mismatch - clear stale ID and create new
                await clear_barber_stripe_account(user_id)
                logger.info("Cleared stale Stripe account for user %s, creating new", user_id)
                stripe_account_id = None
            elif account.charges_enabled and account.payouts_enabled:
                return {
                    "already_onboarded": True,
                    "charges_enabled": True,
                    "payouts_enabled": True,
                }

        if not stripe_account_id:
            # Create new Stripe Connect Express account
            account = stripe.Account.create(
                type="express",
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
                business_type="individual",
                metadata={
                    "user_id": user_id,
                    "platform": "barberscore_pos",
                }
            )
            stripe_account_id = account.id

            saved = await save_barber_stripe_account(user_id, stripe_account_id)
            if not saved:
                # Cleanup: reject account since live mode doesn't support delete
                try:
                    stripe.Account.reject(stripe_account_id, reason="fraud")
                except Exception:
                    logger.error("Failed to reject orphaned Stripe account %s", stripe_account_id)
                raise HTTPException(status_code=500, detail="Failed to save Stripe account. Please try again.")

        # Generate onboarding link (works for both new and returning users)
        account_link = stripe.AccountLink.create(
            account=stripe_account_id,
            refresh_url=f"{settings.FRONTEND_URL}/stripe-refresh.html",
            return_url=f"{settings.FRONTEND_URL}/stripe-success.html",
            type="account_onboarding",
        )

        return {"url": account_link.url}

    except stripe.error.StripeError as e:
        logger.error("Stripe error for user %s: %s", user_id, str(e))
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")
