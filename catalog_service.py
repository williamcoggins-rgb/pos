"""
Catalog Service
Manages services/products offered by barbers (catalog items).
Event-sourced for audit trail and offline sync.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
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
    """A service or product in the catalog"""
    item_id: str
    barber_id: str
    name: str
    price: Money
    category: str = "service"  # "service" or "product"
    description: Optional[str] = None
    duration_minutes: Optional[int] = None  # For services
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CatalogService:
    """
    Manages catalog items (services/products) for barbers.
    Uses event sourcing for full audit trail.
    """

    def __init__(self, event_store: CloudEventStore):
        self.event_store = event_store
        self._items: Dict[str, CatalogItem] = {}
        self._rebuild_state()

    def _rebuild_state(self) -> None:
        """Rebuild catalog state from event store"""
        # Get all catalog_item events by aggregate_type
        events = self.event_store.get_events(aggregate_type="catalog_item")

        for event in events:
            self._apply_event(event)

    def _apply_event(self, event: Event) -> None:
        """Apply a single event to update state"""
        payload = event.payload
        # Handle both enum and string event types for comparison
        event_type = event.event_type.value if isinstance(event.event_type, EventType) else event.event_type

        if event_type == EventType.CATALOG_ITEM_CREATED.value:
            item = CatalogItem(
                item_id=payload["item_id"],
                barber_id=payload["barber_id"],
                name=payload["name"],
                price=Money(payload["price_cents"], payload.get("currency", "USD")),
                category=payload.get("category", "service"),
                description=payload.get("description"),
                duration_minutes=payload.get("duration_minutes"),
                is_active=True,
                created_at=datetime.fromisoformat(payload["created_at"]) if "created_at" in payload else datetime.now(timezone.utc),
                updated_at=datetime.fromisoformat(payload["created_at"]) if "created_at" in payload else datetime.now(timezone.utc),
            )
            self._items[item.item_id] = item

        elif event_type == EventType.CATALOG_ITEM_UPDATED.value:
            item_id = payload["item_id"]
            if item_id in self._items:
                item = self._items[item_id]
                if "name" in payload:
                    item.name = payload["name"]
                if "price_cents" in payload:
                    item.price = Money(payload["price_cents"], payload.get("currency", item.price.currency))
                if "category" in payload:
                    item.category = payload["category"]
                if "description" in payload:
                    item.description = payload["description"]
                if "duration_minutes" in payload:
                    item.duration_minutes = payload["duration_minutes"]
                item.updated_at = datetime.fromisoformat(payload["updated_at"]) if "updated_at" in payload else datetime.now(timezone.utc)

        elif event_type == EventType.CATALOG_ITEM_DELETED.value:
            item_id = payload["item_id"]
            if item_id in self._items:
                self._items[item_id].is_active = False
                self._items[item_id].updated_at = datetime.fromisoformat(payload["deleted_at"]) if "deleted_at" in payload else datetime.now(timezone.utc)

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
        now = utc_now()

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.CATALOG_ITEM_CREATED,
            aggregate_id=item_id,
            aggregate_type="catalog_item",
            payload={
                "item_id": item_id,
                "barber_id": barber_id,
                "name": name,
                "price_cents": price.amount_minor,
                "currency": price.currency,
                "category": category,
                "description": description,
                "duration_minutes": duration_minutes,
                "created_at": now,
            },
            created_at=now,
        )

        self.event_store.append(event)
        self._apply_event(event)

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
    ) -> CatalogItem:
        """Update an existing catalog item."""
        if item_id not in self._items:
            raise ValueError(f"Item {item_id} not found")

        item = self._items[item_id]
        if item.barber_id != barber_id:
            raise PermissionError("Cannot update another barber's catalog item")

        if not item.is_active:
            raise ValueError("Cannot update deleted item")

        now = utc_now()
        payload: Dict[str, Any] = {
            "item_id": item_id,
            "barber_id": barber_id,
            "updated_at": now,
        }

        if name is not None:
            payload["name"] = name
        if price is not None:
            payload["price_cents"] = price.amount_minor
            payload["currency"] = price.currency
        if category is not None:
            payload["category"] = category
        if description is not None:
            payload["description"] = description
        if duration_minutes is not None:
            payload["duration_minutes"] = duration_minutes

        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.CATALOG_ITEM_UPDATED,
            aggregate_id=item_id,
            aggregate_type="catalog_item",
            payload=payload,
            created_at=now,
        )

        self.event_store.append(event)
        self._apply_event(event)

        return self._items[item_id]

    def delete_item(self, barber_id: str, item_id: str) -> None:
        """Soft-delete a catalog item."""
        if item_id not in self._items:
            raise ValueError(f"Item {item_id} not found")

        item = self._items[item_id]
        if item.barber_id != barber_id:
            raise PermissionError("Cannot delete another barber's catalog item")

        if not item.is_active:
            return  # Already deleted

        now = utc_now()
        event = Event(
            event_id=generate_event_id(),
            event_type=EventType.CATALOG_ITEM_DELETED,
            aggregate_id=item_id,
            aggregate_type="catalog_item",
            payload={
                "item_id": item_id,
                "barber_id": barber_id,
                "deleted_at": now,
            },
            created_at=now,
        )

        self.event_store.append(event)
        self._apply_event(event)

    def get_item(self, item_id: str) -> Optional[CatalogItem]:
        """Get a catalog item by ID."""
        return self._items.get(item_id)

    def list_items(
        self,
        barber_id: str,
        include_inactive: bool = False,
        category: Optional[str] = None,
    ) -> List[CatalogItem]:
        """List catalog items for a barber."""
        items = [
            item for item in self._items.values()
            if item.barber_id == barber_id
        ]

        if not include_inactive:
            items = [item for item in items if item.is_active]

        if category:
            items = [item for item in items if item.category == category]

        # Sort by name
        items.sort(key=lambda x: x.name.lower())

        return items
