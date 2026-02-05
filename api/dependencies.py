"""
Shared FastAPI dependencies.
Single source of truth for auth, database access, and service injection.
"""

from fastapi import Header, HTTPException, Depends
from typing import Optional

from api.services.auth_service import AuthService
from api.database import (
    get_cloud_store,
    get_local_queue,
    get_eligibility_engine,
    get_entitlement_ledger,
    get_procurement_service,
)
from enforcement_middleware import EnforcementMiddleware

# Single AuthService instance
_auth_service = AuthService()


def get_auth_service() -> AuthService:
    return _auth_service


async def get_current_user_id(authorization: Optional[str] = Header(None)) -> str:
    """
    Extract user_id from Bearer token.
    Use this when you need the raw Supabase user ID.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")
    payload = _auth_service.verify_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return user_id


async def get_current_barber(authorization: Optional[str] = Header(None)) -> str:
    """
    Extract barber_id from Bearer token.
    Use this when you need the barber_id for POS/eligibility/procurement operations.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")
    barber_id = _auth_service.get_barber_id_from_token(token)

    if not barber_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return barber_id


def get_enforcement_middleware() -> EnforcementMiddleware:
    """Get enforcement middleware with ledger and procurement wired up."""
    return EnforcementMiddleware(
        entitlement_ledger=get_entitlement_ledger(),
        procurement_service=get_procurement_service(),
    )
