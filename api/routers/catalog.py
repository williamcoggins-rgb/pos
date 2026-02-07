"""
Catalog API endpoints
Handles CRUD for services/products in the barber's catalog
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from typing import Optional, List
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from catalog_service import CatalogService, CatalogItem
from event_store import Money
from api.database import get_cloud_store
from api.services.auth_service import AuthService

router = APIRouter(prefix="/api/catalog", tags=["Catalog"])

# Services
auth_service = AuthService()

# Singleton catalog service (will be initialized on first request)
_catalog_service: Optional[CatalogService] = None


def get_catalog_service() -> CatalogService:
    """Get or create catalog service singleton"""
    global _catalog_service
    if _catalog_service is None:
        _catalog_service = CatalogService(get_cloud_store())
    return _catalog_service


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


# Request/Response Models

class CreateCatalogItemRequest(BaseModel):
    """Request to create a catalog item"""
    name: str = Field(..., min_length=1, description="Item name")
    price_cents: int = Field(..., ge=0, description="Price in cents")
    category: str = Field(default="service", description="Category: service or product")
    description: Optional[str] = Field(None, description="Item description")
    duration_minutes: Optional[int] = Field(None, ge=1, description="Duration in minutes (for services)")


class UpdateCatalogItemRequest(BaseModel):
    """Request to update a catalog item"""
    name: Optional[str] = Field(None, min_length=1, description="Item name")
    price_cents: Optional[int] = Field(None, ge=0, description="Price in cents")
    category: Optional[str] = Field(None, description="Category: service or product")
    description: Optional[str] = Field(None, description="Item description")
    duration_minutes: Optional[int] = Field(None, ge=1, description="Duration in minutes")


class CatalogItemResponse(BaseModel):
    """Catalog item response"""
    item_id: str
    barber_id: str
    name: str
    price: dict  # {"amount_minor": int, "currency": str}
    category: str
    description: Optional[str]
    duration_minutes: Optional[int]
    is_active: bool
    created_at: str
    updated_at: str


def _item_to_response(item: CatalogItem) -> CatalogItemResponse:
    """Convert CatalogItem to response model"""
    return CatalogItemResponse(
        item_id=item.item_id,
        barber_id=item.barber_id,
        name=item.name,
        price={"amount_minor": item.price.amount_minor, "currency": item.price.currency},
        category=item.category,
        description=item.description,
        duration_minutes=item.duration_minutes,
        is_active=item.is_active,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )


# Endpoints

@router.get("/items", response_model=List[CatalogItemResponse])
async def list_catalog_items(
    category: Optional[str] = None,
    include_inactive: bool = False,
    barber_id: str = Depends(get_current_barber),
):
    """List all catalog items for the authenticated barber"""
    catalog = get_catalog_service()
    items = catalog.list_items(
        barber_id=barber_id,
        include_inactive=include_inactive,
        category=category,
    )
    return [_item_to_response(item) for item in items]


@router.post("/items", response_model=CatalogItemResponse, status_code=201)
async def create_catalog_item(
    request: CreateCatalogItemRequest,
    barber_id: str = Depends(get_current_barber),
):
    """Create a new catalog item"""
    catalog = get_catalog_service()

    item_id = catalog.create_item(
        barber_id=barber_id,
        name=request.name,
        price=Money(request.price_cents),
        category=request.category,
        description=request.description,
        duration_minutes=request.duration_minutes,
    )

    item = catalog.get_item(item_id)
    if not item:
        raise HTTPException(status_code=500, detail="Failed to create item")

    return _item_to_response(item)


@router.get("/items/{item_id}", response_model=CatalogItemResponse)
async def get_catalog_item(
    item_id: str,
    barber_id: str = Depends(get_current_barber),
):
    """Get a specific catalog item"""
    catalog = get_catalog_service()
    item = catalog.get_item(item_id)

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if item.barber_id != barber_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return _item_to_response(item)


@router.put("/items/{item_id}", response_model=CatalogItemResponse)
async def update_catalog_item(
    item_id: str,
    request: UpdateCatalogItemRequest,
    barber_id: str = Depends(get_current_barber),
):
    """Update a catalog item"""
    catalog = get_catalog_service()

    try:
        item = catalog.update_item(
            barber_id=barber_id,
            item_id=item_id,
            name=request.name,
            price=Money(request.price_cents) if request.price_cents is not None else None,
            category=request.category,
            description=request.description,
            duration_minutes=request.duration_minutes,
        )
        return _item_to_response(item)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/items/{item_id}", status_code=204)
async def delete_catalog_item(
    item_id: str,
    barber_id: str = Depends(get_current_barber),
):
    """Delete (soft-delete) a catalog item"""
    catalog = get_catalog_service()

    try:
        catalog.delete_item(barber_id=barber_id, item_id=item_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
