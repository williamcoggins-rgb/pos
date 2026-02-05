"""
Service Catalog
Event-sourced catalog for barber services and products.
Each barber has their own catalog items (haircuts, shaves, products, etc.)
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from event_store import (
    Event,
    EventType,
    Money,
    CloudEventStore,
    utc_now,
    generate_event_id,
)


@dataclass
class CatalogItem:
    """A service or product in the barber's catalog"""
    item_id: str
    barber_id: str
    name: str
    price: Money
    category: str = "service"
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CatalogService:
    """
    Event-sourced service catalog.
    Stores service/product definitions per barber.
    """

    def __init__(self, cloud_store: CloudEventStore):
        self.cloud_store = cloud_store

    def create_item(
        self,
        barber_id: str,
        name: str,
        price: Money,
        category: str = "service",
        description: Optional[str] = None,
        duration_minutes: Optional[int] = None,
    ) -> str:
        """Create a new catalog item. Returns item_id."""
        item_id = str(uuid.uuid4())

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.CATALOG_ITEM_CREATED,
            aggregate_id=item_id,
            aggregate_type="catalog_item",
            payload={
                "item_id": item_id,
                "barber_id": barber_id,
                "name": name,
                "price": price.to_dict(),
                "category": category,
                "description": description,
                "duration_minutes": duration_minutes,
            },
            created_at=utc_now(),
            idempotency_key=f"catalog_item_created_{item_id}",
        )

        self.cloud_store.append(event)
        return item_id

    def update_item(
        self,
        barber_id: str,
        item_id: str,
        name: Optional[str] = None,
        price: Optional[Money] = None,
        category: Optional[str] = None,
        description: Optional[str] = None,
        duration_minutes: Optional[int] = None,
        is_active: Optional[bool] = None,
    ):
        """Update a catalog item."""
        # Verify ownership
        item = self.get_item(item_id)
        if item.barber_id != barber_id:
            raise ValueError(f"Item {item_id} does not belong to barber {barber_id}")

        updates = {}
        if name is not None:
            updates["name"] = name
        if price is not None:
            updates["price"] = price.to_dict()
        if category is not None:
            updates["category"] = category
        if description is not None:
            updates["description"] = description
        if duration_minutes is not None:
            updates["duration_minutes"] = duration_minutes
        if is_active is not None:
            updates["is_active"] = is_active

        if not updates:
            return

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.CATALOG_ITEM_UPDATED,
            aggregate_id=item_id,
            aggregate_type="catalog_item",
            payload={
                "item_id": item_id,
                "barber_id": barber_id,
                "updates": updates,
            },
            created_at=utc_now(),
            idempotency_key=f"catalog_item_updated_{item_id}_{generate_event_id()[:8]}",
        )

        self.cloud_store.append(event)

    def delete_item(self, barber_id: str, item_id: str):
        """Soft-delete a catalog item (marks as inactive)."""
        item = self.get_item(item_id)
        if item.barber_id != barber_id:
            raise ValueError(f"Item {item_id} does not belong to barber {barber_id}")

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.CATALOG_ITEM_DELETED,
            aggregate_id=item_id,
            aggregate_type="catalog_item",
            payload={
                "item_id": item_id,
                "barber_id": barber_id,
            },
            created_at=utc_now(),
            idempotency_key=f"catalog_item_deleted_{item_id}",
        )

        self.cloud_store.append(event)

    def get_item(self, item_id: str) -> CatalogItem:
        """Reconstruct a catalog item from events."""
        events = self.cloud_store.get_events(
            aggregate_type="catalog_item",
            aggregate_id=item_id,
        )

        if not events:
            raise ValueError(f"Catalog item {item_id} not found")

        item = None
        for event in events:
            if event.event_type == EventType.CATALOG_ITEM_CREATED:
                p = event.payload
                item = CatalogItem(
                    item_id=p["item_id"],
                    barber_id=p["barber_id"],
                    name=p["name"],
                    price=Money(**p["price"]),
                    category=p.get("category", "service"),
                    description=p.get("description"),
                    duration_minutes=p.get("duration_minutes"),
                    is_active=True,
                    created_at=event.created_at,
                    updated_at=event.created_at,
                )

            elif event.event_type == EventType.CATALOG_ITEM_UPDATED and item:
                updates = event.payload.get("updates", {})
                if "name" in updates:
                    item.name = updates["name"]
                if "price" in updates:
                    item.price = Money(**updates["price"])
                if "category" in updates:
                    item.category = updates["category"]
                if "description" in updates:
                    item.description = updates["description"]
                if "duration_minutes" in updates:
                    item.duration_minutes = updates["duration_minutes"]
                if "is_active" in updates:
                    item.is_active = updates["is_active"]
                item.updated_at = event.created_at

            elif event.event_type == EventType.CATALOG_ITEM_DELETED and item:
                item.is_active = False
                item.updated_at = event.created_at

        if not item:
            raise ValueError(f"Catalog item {item_id} not found")

        return item

    def list_items(self, barber_id: str, include_inactive: bool = False) -> List[CatalogItem]:
        """List all catalog items for a barber."""
        # Get all CATALOG_ITEM_CREATED events
        events = self.cloud_store.get_events(
            event_type=EventType.CATALOG_ITEM_CREATED,
        )

        item_ids = []
        for event in events:
            if event.payload.get("barber_id") == barber_id:
                item_ids.append(event.payload["item_id"])

        items = []
        for item_id in item_ids:
            try:
                item = self.get_item(item_id)
                if include_inactive or item.is_active:
                    items.append(item)
            except ValueError:
                continue

        return items
