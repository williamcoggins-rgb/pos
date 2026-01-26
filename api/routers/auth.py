"""
Authentication API endpoints
Handles registration and login
"""

from fastapi import APIRouter, HTTPException
from api.models import RegisterRequest, LoginRequest, TokenResponse, ErrorResponse
from api.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

auth_service = AuthService()


@router.post("/register", response_model=TokenResponse)
async def register(request: RegisterRequest):
    """Register a new barber account"""
    try:
        access_token, barber_id, shop_name = await auth_service.register(
            email=request.email,
            password=request.password,
            shop_name=request.shop_name,
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
