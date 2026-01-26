"""
Eligibility and BarberScore API endpoints
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.models import (
    BarberScoreResponse,
    BarberMetricsResponse,
    EntitlementResponse,
    ErrorResponse,
)
from api.database import get_eligibility_engine, get_entitlement_ledger
from enforcement_middleware import EnforcementMiddleware
from procurement_service import ProcurementService
from api.database import get_cloud_store
from api.services.auth_service import AuthService

router = APIRouter(prefix="/api/eligibility", tags=["Eligibility"])

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


@router.get("/score/{barber_id}", response_model=BarberScoreResponse)
async def get_barberscore(
    barber_id: str,
    current_user: str = Depends(get_current_barber)
):
    """
    Get BarberScore for a barber
    (Barbers can only view their own score)
    """
    # Ensure barbers can only view their own score
    if barber_id != current_user:
        raise HTTPException(status_code=403, detail="Cannot view other barbers' scores")

    try:
        engine = get_eligibility_engine()
        score = engine.calculate_barberscore(barber_id)

        return BarberScoreResponse(
            barber_id=score.barber_id,
            score=score.score,
            tier=score.tier,
            metrics=BarberMetricsResponse(
                qualified_transactions=score.metrics.qualified_transactions,
                total_revenue_cents=score.metrics.total_revenue_cents,
                refund_count=score.metrics.refund_count,
                void_count=score.metrics.void_count,
                chargeback_count=score.metrics.chargeback_count,
                active_days=score.metrics.active_days,
                avg_ticket_cents=score.metrics.avg_ticket_cents,
                refund_rate=score.metrics.refund_rate,
                void_rate=score.metrics.void_rate,
                chargeback_rate=score.metrics.chargeback_rate,
            ),
            flags=score.flags,
            hard_gate_blocks=score.hard_gate_blocks,
            calculated_at=score.calculated_at,
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/score/{barber_id}/update", response_model=dict)
async def update_barberscore(
    barber_id: str,
    current_user: str = Depends(get_current_barber)
):
    """
    Force update BarberScore and emit entitlement events
    (Normally triggered automatically by POS events)
    """
    if barber_id != current_user:
        raise HTTPException(status_code=403, detail="Cannot update other barbers' scores")

    try:
        engine = get_eligibility_engine()
        engine.update_and_emit_entitlements(barber_id)
        return {"success": True, "message": "BarberScore updated"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/entitlements/{barber_id}", response_model=EntitlementResponse)
async def get_entitlements(
    barber_id: str,
    current_user: str = Depends(get_current_barber)
):
    """Get current entitlements for barber"""
    if barber_id != current_user:
        raise HTTPException(status_code=403, detail="Cannot view other barbers' entitlements")

    try:
        ledger = get_entitlement_ledger()
        procurement = ProcurementService(get_cloud_store())
        enforcement = EnforcementMiddleware(ledger, procurement)

        summary = enforcement.get_entitlement_summary(barber_id)

        return EntitlementResponse(**summary)

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/unlock-requirements/{barber_id}/{tier}", response_model=dict)
async def get_unlock_requirements(
    barber_id: str,
    tier: str,
    current_user: str = Depends(get_current_barber)
):
    """Get requirements to unlock a specific tier"""
    if barber_id != current_user:
        raise HTTPException(status_code=403, detail="Cannot view other barbers' data")

    try:
        ledger = get_entitlement_ledger()
        procurement = ProcurementService(get_cloud_store())
        enforcement = EnforcementMiddleware(ledger, procurement)

        requirements = enforcement.get_unlock_requirements(barber_id, tier)
        return requirements

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
