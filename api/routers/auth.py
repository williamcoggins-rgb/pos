"""
Authentication API endpoints
Handles registration, login, PIN, and onboarding status.
"""

from fastapi import APIRouter, HTTPException, Depends
from api.models import (
    RegisterRequest, LoginRequest, TokenResponse,
    PINLoginRequest, SetPINRequest, UserProfileResponse
)
from api.dependencies import get_current_user_id, get_auth_service
from api.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse)
async def register(request: RegisterRequest):
    """Register a new barber account"""
    try:
        access_token, barber_id, shop_name = await get_auth_service().register(
            email=request.email,
            password=request.password,
            shop_name=request.shop_name,
            owner_name=request.owner_name,
            phone=request.phone,
        )

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            barber_id=barber_id,
            shop_name=shop_name,
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Login to existing barber account"""
    try:
        access_token, barber_id, shop_name = await get_auth_service().login(
            email=request.email,
            password=request.password,
        )

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            barber_id=barber_id,
            shop_name=shop_name,
        )

    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/verify", response_model=dict)
async def verify_token(token: str):
    """Verify a JWT token"""
    payload = get_auth_service().verify_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    return {"valid": True, "payload": payload}


@router.post("/login-pin", response_model=TokenResponse)
async def login_with_pin(request: PINLoginRequest):
    """Login using email and 4-digit PIN"""
    try:
        access_token, barber_id, shop_name = await get_auth_service().login_with_pin(
            email=request.email,
            pin=request.pin,
        )

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            barber_id=barber_id,
            shop_name=shop_name,
        )

    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/set-pin")
async def set_pin(
    request: SetPINRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Set or update user's 4-digit PIN (step 3 of onboarding)"""
    try:
        await get_auth_service().set_pin(user_id=user_id, pin=request.pin)
        return {"success": True, "message": "PIN set successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(user_id: str = Depends(get_current_user_id)):
    """Get user profile"""
    try:
        profile = await get_auth_service().get_profile(user_id=user_id)
        return UserProfileResponse(**profile)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/onboarding-status")
async def get_onboarding_status(user_id: str = Depends(get_current_user_id)):
    """
    Get onboarding progress for the current user.
    Returns which step they need to complete next.

    Flow: register -> stripe_connect -> (pending_verification) -> set_pin -> ready

    Uses the actual Stripe account status, not just whether an ID exists in the DB.
    This correctly handles test-to-live transitions and pending Stripe verification.
    """
    auth = get_auth_service()

    try:
        profile = await auth.get_profile(user_id=user_id)
    except Exception:
        return {
            "step": "register",
            "complete": False,
            "message": "Account not found. Please register.",
        }

    has_pin = profile.get("has_pin", False)

    # Check actual Stripe account status (not just whether an ID is stored)
    from api.routers.stripe_connect import get_barber_stripe_account, _retrieve_account_safe
    from api.config import get_settings
    settings = get_settings()

    stripe_account_id = await get_barber_stripe_account(user_id)
    stripe_active = False
    stripe_pending = False

    if stripe_account_id and settings.STRIPE_SECRET_KEY:
        account = _retrieve_account_safe(stripe_account_id)
        if account is None:
            # Stale account (test/live mismatch) - clear it
            from api.routers.stripe_connect import clear_barber_stripe_account
            await clear_barber_stripe_account(user_id)
        elif account.charges_enabled and account.payouts_enabled:
            stripe_active = True
        elif account.details_submitted:
            stripe_pending = True

    if not stripe_active and not stripe_pending:
        return {
            "step": "stripe_connect",
            "complete": False,
            "message": "Connect your Stripe account to accept payments.",
        }

    if stripe_pending and not stripe_active:
        return {
            "step": "pending_verification",
            "complete": False,
            "message": "Stripe is verifying your account. This can take 1-2 business days. You'll be notified when it's ready.",
        }

    if not has_pin:
        return {
            "step": "set_pin",
            "complete": False,
            "message": "Set your 4-digit PIN for quick login.",
        }

    return {
        "step": "ready",
        "complete": True,
        "message": "Onboarding complete. Welcome to BarberScore POS.",
    }
