"""
Stripe Connect API endpoints
Handles Stripe Connect onboarding for barbers to accept payments
"""

from fastapi import APIRouter, HTTPException, Header
from typing import Optional
import stripe
import httpx

from api.config import get_settings
from api.services.auth_service import AuthService

settings = get_settings()
router = APIRouter(prefix="/api/stripe", tags=["Stripe Connect"])

auth_service = AuthService()

# Initialize Stripe
if settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY


async def get_user_id_from_token(authorization: str) -> str:
    """Extract user_id from Bearer token"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")
    payload = auth_service.verify_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return user_id


async def get_barber_stripe_account(user_id: str, token: str) -> Optional[str]:
    """Get barber's stripe_account_id from Supabase"""
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


async def save_barber_stripe_account(user_id: str, stripe_account_id: str, token: str) -> bool:
    """Save stripe_account_id to barber's Supabase record"""
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

        return response.status_code in (200, 204)


@router.get("/account-status")
async def get_account_status(authorization: str = Header(None)):
    """
    Get the Stripe Connect account status for the current user

    Returns:
        charges_enabled: Can accept payments
        payouts_enabled: Can receive payouts to bank
        onboarding_complete: Has completed Stripe onboarding
    """
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    user_id = await get_user_id_from_token(authorization)
    token = authorization.replace("Bearer ", "")

    # Get stored Stripe account ID
    stripe_account_id = await get_barber_stripe_account(user_id, token)

    if not stripe_account_id:
        # No Stripe account yet
        return {
            "has_account": False,
            "charges_enabled": False,
            "payouts_enabled": False,
            "onboarding_complete": False
        }

    try:
        # Get account status from Stripe
        account = stripe.Account.retrieve(stripe_account_id)

        return {
            "has_account": True,
            "charges_enabled": account.charges_enabled,
            "payouts_enabled": account.payouts_enabled,
            "onboarding_complete": account.details_submitted,
            "account_id": stripe_account_id
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")


@router.post("/create-account-link")
async def create_account_link(authorization: str = Header(None)):
    """
    Create or retrieve a Stripe Connect account and generate an onboarding link

    Returns:
        url: The Stripe onboarding URL to redirect the user to
    """
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    user_id = await get_user_id_from_token(authorization)
    token = authorization.replace("Bearer ", "")

    # Check for existing Stripe account
    stripe_account_id = await get_barber_stripe_account(user_id, token)

    try:
        if stripe_account_id:
            # Check if already fully onboarded
            account = stripe.Account.retrieve(stripe_account_id)

            if account.charges_enabled and account.payouts_enabled:
                # Already fully set up
                return {
                    "error": "Account already fully onboarded",
                    "already_onboarded": True,
                    "payouts_enabled": True,
                    "charges_enabled": True
                }
        else:
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
                    "platform": "barberscore_pos"
                }
            )
            stripe_account_id = account.id

            # Save to Supabase
            saved = await save_barber_stripe_account(user_id, stripe_account_id, token)
            if not saved:
                # Clean up the Stripe account if we couldn't save
                stripe.Account.delete(stripe_account_id)
                raise HTTPException(status_code=500, detail="Failed to save Stripe account")

        # Create account link for onboarding
        account_link = stripe.AccountLink.create(
            account=stripe_account_id,
            refresh_url=f"{settings.FRONTEND_URL}/stripe-refresh.html",
            return_url=f"{settings.FRONTEND_URL}/stripe-success.html",
            type="account_onboarding",
        )

        return {"url": account_link.url}

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")
