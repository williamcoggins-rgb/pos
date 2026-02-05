"""
Service Catalog API endpoints
Manages barber service/product catalog items.
"""

from fastapi import APIRouter, HTTPException, Depends, Header, Query
from typing import Optional, List
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from catalog_service import CatalogService
from event_store import Money
from api.models import (
    CatalogItemRequest,
    CatalogItemResponse,
    MoneyModel,
)
from api.database import get_cloud_store
from api.services.auth_service import AuthService

router = APIRouter(prefix="/api/catalog", tags=["Catalog"])

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


def get_catalog_service() -> CatalogService:
    """Get catalog service instance"""
    return CatalogService(get_cloud_store())


def _item_to_response(item) -> CatalogItemResponse:
    """Convert CatalogItem to CatalogItemResponse"""
    return CatalogItemResponse(
        item_id=item.item_id,
        barber_id=item.barber_id,
        name=item.name,
        price=MoneyModel(amount_minor=item.price.amount_minor, currency=item.price.currency),
        category=item.category,
        description=item.description,
        duration_minutes=item.duration_minutes,
        is_active=item.is_active,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post("/items", response_model=CatalogItemResponse)
async def create_catalog_item(
    request: CatalogItemRequest,
    barber_id: str = Depends(get_current_barber)
):
    """Create a new catalog item (service or product)"""
    try:
        catalog = get_catalog_service()
        item_id = catalog.create_item(
            barber_id=barber_id,
            name=request.name,
            price=Money(amount_minor=request.price_cents),
            category=request.category,
            description=request.description,
            duration_minutes=request.duration_minutes,
        )
        item = catalog.get_item(item_id)
        return _item_to_response(item)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/items", response_model=List[CatalogItemResponse])
async def list_catalog_items(
    barber_id: str = Depends(get_current_barber),
    include_inactive: bool = Query(False, description="Include deleted/inactive items"),
):
    """List all catalog items for the current barber"""
    try:
        catalog = get_catalog_service()
        items = catalog.list_items(barber_id, include_inactive=include_inactive)
        return [_item_to_response(item) for item in items]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/items/{item_id}", response_model=CatalogItemResponse)
async def get_catalog_item(
    item_id: str,
    barber_id: str = Depends(get_current_barber)
):
    """Get a specific catalog item"""
    try:
        catalog = get_catalog_service()
        item = catalog.get_item(item_id)
        if item.barber_id != barber_id:
            raise HTTPException(status_code=403, detail="Cannot view other barbers' catalog items")
        return _item_to_response(item)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/items/{item_id}", response_model=CatalogItemResponse)
async def update_catalog_item(
    item_id: str,
    request: CatalogItemRequest,
    barber_id: str = Depends(get_current_barber)
):
    """Update a catalog item"""
    try:
        catalog = get_catalog_service()
        catalog.update_item(
            barber_id=barber_id,
            item_id=item_id,
            name=request.name,
            price=Money(amount_minor=request.price_cents),
            category=request.category,
            description=request.description,
            duration_minutes=request.duration_minutes,
            is_active=request.is_active,
        )
        item = catalog.get_item(item_id)
        return _item_to_response(item)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/items/{item_id}", response_model=dict)
async def delete_catalog_item(
    item_id: str,
    barber_id: str = Depends(get_current_barber)
):
    """Delete (deactivate) a catalog item"""
    try:
        catalog = get_catalog_service()
        catalog.delete_item(barber_id=barber_id, item_id=item_id)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
