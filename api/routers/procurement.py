"""
Procurement API endpoints
Handles readiness signals — barber expresses interest, admin reaches out.
This is NOT an ordering system.
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional, List
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.models import (
    ReadinessSignalRequest,
    ReadinessSignalResponse,
    ErrorResponse,
)
from api.database import (
    get_cloud_store,
    get_entitlement_ledger,
    get_procurement_service,
    get_eligibility_engine,
)
from api.services.auth_service import AuthService

router = APIRouter(prefix="/api/procurement", tags=["Procurement"])

auth_service = AuthService()


def get_current_barber(authorization: Optional[str] = Header(None)) -> str:
    """Extract barber_id from Authorization header"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = parts[1]
    barber_id = auth_service.get_barber_id_from_token(token)

    if not barber_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    return barber_id


@router.post("/signal", response_model=ReadinessSignalResponse)
async def signal_readiness(
    request: ReadinessSignalRequest,
    current_user: str = Depends(get_current_barber),
):
    """
    Signal that you are ready for procurement access.
    Administration will be notified and reach out to you via your preferred contact method.
    """
    try:
        procurement = get_procurement_service()

        # Check if barber already has a pending/active signal
        if procurement.has_active_signal(current_user):
            raise HTTPException(
                status_code=409,
                detail="You already have an active procurement readiness signal. "
                       "Our team will reach out soon.",
            )

        # Get current score for the signal
        engine = get_eligibility_engine()
        barberscore = engine.calculate_barberscore(current_user)

        signal_id = procurement.signal_readiness(
            barber_id=current_user,
            tier=barberscore.tier,
            score=barberscore.score,
            contact_preference=request.contact_preference,
            message=request.message,
        )

        signal = procurement.get_signal(signal_id)

        return ReadinessSignalResponse(
            signal_id=signal.signal_id,
            barber_id=signal.barber_id,
            tier=signal.tier,
            score=signal.score,
            status=signal.status.value,
            contact_preference=signal.contact_preference,
            message=signal.message,
            created_at=signal.created_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/signals", response_model=List[ReadinessSignalResponse])
async def list_signals(
    current_user: str = Depends(get_current_barber),
):
    """List all your procurement readiness signals and their statuses."""
    try:
        procurement = get_procurement_service()
        signals = procurement.get_barber_signals(current_user)

        return [
            ReadinessSignalResponse(
                signal_id=s.signal_id,
                barber_id=s.barber_id,
                tier=s.tier,
                score=s.score,
                status=s.status.value,
                contact_preference=s.contact_preference,
                message=s.message,
                created_at=s.created_at,
                contacted_at=s.contacted_at,
                resolved_at=s.resolved_at,
            )
            for s in signals
        ]

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/signals/{signal_id}", response_model=ReadinessSignalResponse)
async def get_signal(
    signal_id: str,
    current_user: str = Depends(get_current_barber),
):
    """Get details of a specific readiness signal."""
    try:
        procurement = get_procurement_service()
        signal = procurement.get_signal(signal_id)

        if signal.barber_id != current_user:
            raise HTTPException(status_code=403, detail="Cannot view other barbers' signals")

        return ReadinessSignalResponse(
            signal_id=signal.signal_id,
            barber_id=signal.barber_id,
            tier=signal.tier,
            score=signal.score,
            status=signal.status.value,
            contact_preference=signal.contact_preference,
            message=signal.message,
            created_at=signal.created_at,
            contacted_at=signal.contacted_at,
            resolved_at=signal.resolved_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/status", response_model=dict)
async def get_procurement_status(
    current_user: str = Depends(get_current_barber),
):
    """
    Get barber's overall procurement readiness status.
    Returns tier info, whether they've signaled interest, and next steps.
    """
    try:
        procurement = get_procurement_service()
        engine = get_eligibility_engine()

        barberscore = engine.calculate_barberscore(current_user)
        signals = procurement.get_barber_signals(current_user)

        has_pending = any(s.status.value == "PENDING" for s in signals)
        has_active = any(s.status.value == "ACTIVE" for s in signals)
        has_contacted = any(s.status.value == "CONTACTED" for s in signals)

        # Determine next step
        if has_active:
            next_step = "Your procurement access is active. Our team will be in touch with available products and pricing."
        elif has_contacted:
            next_step = "Our team has reached out to you. Check your email or phone for next steps."
        elif has_pending:
            next_step = "Your interest has been noted. Our team will reach out soon."
        elif barberscore.score >= 50:
            next_step = "You're eligible for procurement access. Signal your interest to get started."
        else:
            next_step = "Keep using the POS to build your BarberScore. Procurement unlocks at Level 1 (50+ points)."

        return {
            "barber_id": current_user,
            "tier": barberscore.tier,
            "score": barberscore.score,
            "eligible": barberscore.score >= 50,
            "has_signaled": has_pending or has_contacted or has_active,
            "signal_status": (
                "ACTIVE" if has_active
                else "CONTACTED" if has_contacted
                else "PENDING" if has_pending
                else "NONE"
            ),
            "next_step": next_step,
            "signals_count": len(signals),
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
