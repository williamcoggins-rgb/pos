"""
Authentication API endpoints
Handles registration and login
"""

from fastapi import APIRouter, HTTPException, Header
from api.models import (
    RegisterRequest, LoginRequest, TokenResponse, ErrorResponse,
    PINLoginRequest, SetPINRequest, UserProfileResponse
)
from api.services.auth_service import AuthService
from typing import Optional

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

auth_service = AuthService()


def get_user_id_from_token(authorization: str) -> str:
    """Extract user_id from Authorization header"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")
    payload = auth_service.verify_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return user_id


@router.post("/register", response_model=TokenResponse)
async def register(request: RegisterRequest):
    """Register a new barber account"""
    try:
        access_token, barber_id, shop_name = await auth_service.register(
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
        access_token, barber_id, shop_name = await auth_service.login(
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
    payload = auth_service.verify_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    return {"valid": True, "payload": payload}


@router.post("/login-pin", response_model=TokenResponse)
async def login_with_pin(request: PINLoginRequest):
    """Login using email and 4-digit PIN"""
    try:
        access_token, barber_id, shop_name = await auth_service.login_with_pin(
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
    authorization: Optional[str] = Header(None)
):
    """Set or update user's 4-digit PIN"""
    user_id = get_user_id_from_token(authorization)

    try:
        await auth_service.set_pin(user_id=user_id, pin=request.pin)
        return {"success": True, "message": "PIN set successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(authorization: Optional[str] = Header(None)):
    """Get user profile"""
    user_id = get_user_id_from_token(authorization)

    try:
        profile = await auth_service.get_profile(user_id=user_id)
        return UserProfileResponse(**profile)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
