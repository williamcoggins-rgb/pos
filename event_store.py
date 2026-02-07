"""
Event Sourcing Infrastructure
Provides CloudEventStore (immutable ledger) and LocalEventQueue (offline buffer)
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from threading import Lock


class EventType(str, Enum):
    """All event types in the system"""

    # POS Events
    SALE_CREATED = "SALE_CREATED"
    LINE_ITEM_ADDED = "LINE_ITEM_ADDED"
    DISCOUNT_APPLIED = "DISCOUNT_APPLIED"
    TAX_CALCULATED = "TAX_CALCULATED"
    PAYMENT_INITIATED = "PAYMENT_INITIATED"
    PAYMENT_AUTHORIZED = "PAYMENT_AUTHORIZED"
    PAYMENT_CAPTURED = "PAYMENT_CAPTURED"
    PAYMENT_DECLINED = "PAYMENT_DECLINED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    REFUND_CREATED = "REFUND_CREATED"
    REFUND_PROCESSED = "REFUND_PROCESSED"
    VOID_APPLIED = "VOID_APPLIED"
    SHIFT_OPENED = "SHIFT_OPENED"
    SHIFT_CLOSED = "SHIFT_CLOSED"

    # Procurement Events
    PROCUREMENT_ORDER_CREATED = "PROCUREMENT_ORDER_CREATED"
    PROCUREMENT_ORDER_PAID = "PROCUREMENT_ORDER_PAID"
    PROCUREMENT_ORDER_CANCELED = "PROCUREMENT_ORDER_CANCELED"

    # Warehouse Events
    PICKLIST_CREATED = "PICKLIST_CREATED"
    ORDER_PICKED = "ORDER_PICKED"
    ORDER_PACKED = "ORDER_PACKED"
    SHIPMENT_DISPATCHED = "SHIPMENT_DISPATCHED"
    DELIVERY_CONFIRMED = "DELIVERY_CONFIRMED"
    RETURN_RECEIVED = "RETURN_RECEIVED"

    # Terms/Lending Events
    TERMS_INVOICE_ISSUED = "TERMS_INVOICE_ISSUED"
    TERMS_PAYMENT_RECEIVED = "TERMS_PAYMENT_RECEIVED"
    TERMS_PAST_DUE = "TERMS_PAST_DUE"

    # BarberScore Events
    BARBERSCORE_UPDATED = "BARBERSCORE_UPDATED"
    ENTITLEMENT_GRANTED = "ENTITLEMENT_GRANTED"
    ENTITLEMENT_REVOKED = "ENTITLEMENT_REVOKED"
    ENTITLEMENT_UPDATED = "ENTITLEMENT_UPDATED"
    RISK_FLAG_RAISED = "RISK_FLAG_RAISED"

    # Catalog Events
    CATALOG_ITEM_CREATED = "CATALOG_ITEM_CREATED"
    CATALOG_ITEM_UPDATED = "CATALOG_ITEM_UPDATED"
    CATALOG_ITEM_DELETED = "CATALOG_ITEM_DELETED"


@dataclass
class Money:
    """Money value object - always stored in minor units (cents)"""
    amount_minor: int  # Amount in cents
    currency: str = "USD"

    def __post_init__(self):
        if not isinstance(self.amount_minor, int):
            raise ValueError("amount_minor must be an integer")
        if self.amount_minor < 0:
            raise ValueError("amount_minor cannot be negative")

    @classmethod
    def from_dollars(cls, dollars: float, currency: str = "USD") -> "Money":
        """Create Money from dollar amount"""
        return cls(amount_minor=int(dollars * 100), currency=currency)

    @property
    def amount_dollars(self) -> float:
        """Get amount in dollars"""
        return self.amount_minor / 100.0

    def to_dict(self) -> Dict[str, Any]:
        return {"amount_minor": self.amount_minor, "currency": self.currency}


@dataclass
class Event:
    """Immutable event in the event stream"""
    event_id: str
    event_type: EventType
    aggregate_id: str  # barber_id, sale_id, order_id, etc.
    aggregate_type: str  # "barber", "sale", "order", etc.
    payload: Dict[str, Any]
    created_at: str  # ISO 8601 timestamp
    idempotency_key: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for storage"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value if isinstance(self.event_type, EventType) else self.event_type,
            "aggregate_id": self.aggregate_id,
            "aggregate_type": self.aggregate_type,
            "payload": self.payload,
            "created_at": self.created_at,
            "idempotency_key": self.idempotency_key,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """Create event from dictionary"""
        return cls(
            event_id=data["event_id"],
            event_type=EventType(data["event_type"]),
            aggregate_id=data["aggregate_id"],
            aggregate_type=data["aggregate_type"],
            payload=data["payload"],
            created_at=data["created_at"],
            idempotency_key=data.get("idempotency_key"),
            metadata=data.get("metadata", {}),
        )


class CloudEventStore:
    """
    Immutable append-only event ledger.
    Acts as single source of truth for all events.
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._lock = Lock()
        self._subscribers: List[Callable[[Event], None]] = []
        self._initialize_db()

    def _initialize_db(self):
        """Create events table with idempotency support"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    aggregate_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    idempotency_key TEXT,
                    metadata TEXT,
                    sequence INTEGER NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_aggregate
                ON events(aggregate_type, aggregate_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_event_type
                ON events(event_type)
            """)
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_idempotency
                ON events(idempotency_key)
                WHERE idempotency_key IS NOT NULL
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at
                ON events(created_at)
            """)
            conn.commit()

    def append(self, event: Event) -> bool:
        """
        Append event to immutable ledger.
        Returns True if event was added, False if duplicate (idempotency).
        """
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                # Check idempotency
                if event.idempotency_key:
                    cursor = conn.execute(
                        "SELECT event_id FROM events WHERE idempotency_key = ?",
                        (event.idempotency_key,)
                    )
                    if cursor.fetchone():
                        return False  # Duplicate, skip

                # Get next sequence number
                cursor = conn.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM events")
                sequence = cursor.fetchone()[0]

                # Append event
                conn.execute("""
                    INSERT INTO events
                    (event_id, event_type, aggregate_id, aggregate_type,
                     payload, created_at, idempotency_key, metadata, sequence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.event_id,
                    event.event_type.value,
                    event.aggregate_id,
                    event.aggregate_type,
                    json.dumps(event.payload),
                    event.created_at,
                    event.idempotency_key,
                    json.dumps(event.metadata),
                    sequence,
                ))
                conn.commit()

                # Notify subscribers
                for subscriber in self._subscribers:
                    try:
                        subscriber(event)
                    except Exception as e:
                        print(f"Subscriber error: {e}")

                return True

    def get_events(
        self,
        aggregate_type: Optional[str] = None,
        aggregate_id: Optional[str] = None,
        event_type: Optional[EventType] = None,
        since: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Event]:
        """Query events with filters"""
        query = "SELECT * FROM events WHERE 1=1"
        params = []

        if aggregate_type:
            query += " AND aggregate_type = ?"
            params.append(aggregate_type)

        if aggregate_id:
            query += " AND aggregate_id = ?"
            params.append(aggregate_id)

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type.value)

        if since:
            query += " AND created_at > ?"
            params.append(since)

        query += " ORDER BY sequence ASC"

        if limit:
            query += f" LIMIT {limit}"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            return [
                Event(
                    event_id=row["event_id"],
                    event_type=EventType(row["event_type"]),
                    aggregate_id=row["aggregate_id"],
                    aggregate_type=row["aggregate_type"],
                    payload=json.loads(row["payload"]),
                    created_at=row["created_at"],
                    idempotency_key=row["idempotency_key"],
                    metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                )
                for row in rows
            ]

    def subscribe(self, handler: Callable[[Event], None]):
        """Subscribe to all new events"""
        self._subscribers.append(handler)

    def replay_events(self, handler: Callable[[Event], None], aggregate_id: Optional[str] = None):
        """Replay all events (or for specific aggregate) to rebuild state"""
        events = self.get_events(aggregate_id=aggregate_id)
        for event in events:
            handler(event)


class LocalEventQueue:
    """
    Offline-first event buffer.
    Stores events locally when offline, syncs to CloudEventStore when online.
    """

    def __init__(self, queue_path: str = "local_events.db"):
        self.queue_path = queue_path
        self._lock = Lock()
        self._initialize_db()

    def _initialize_db(self):
        """Create local queue table"""
        with sqlite3.connect(self.queue_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS local_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_data TEXT NOT NULL,
                    queued_at TEXT NOT NULL,
                    synced INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    def enqueue(self, event: Event):
        """Add event to local queue"""
        with self._lock:
            with sqlite3.connect(self.queue_path) as conn:
                conn.execute(
                    "INSERT INTO local_queue (event_data, queued_at) VALUES (?, ?)",
                    (json.dumps(event.to_dict()), datetime.now(timezone.utc).isoformat())
                )
                conn.commit()

    def sync_to_cloud(self, cloud_store: CloudEventStore) -> int:
        """
        Sync all unsynced events to cloud store.
        Returns number of events synced.
        """
        with self._lock:
            with sqlite3.connect(self.queue_path) as conn:
                cursor = conn.execute(
                    "SELECT id, event_data FROM local_queue WHERE synced = 0 ORDER BY id"
                )
                rows = cursor.fetchall()

                synced_count = 0
                for row_id, event_data in rows:
                    event_dict = json.loads(event_data)
                    event = Event.from_dict(event_dict)

                    # Try to append to cloud (idempotency handled there)
                    cloud_store.append(event)

                    # Mark as synced
                    conn.execute("UPDATE local_queue SET synced = 1 WHERE id = ?", (row_id,))
                    synced_count += 1

                conn.commit()
                return synced_count

    def get_pending_count(self) -> int:
        """Get count of unsynced events"""
        with sqlite3.connect(self.queue_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM local_queue WHERE synced = 0")
            return cursor.fetchone()[0]


def utc_now() -> str:
    """Get current UTC timestamp in ISO 8601 format"""
    return datetime.now(timezone.utc).isoformat()


def generate_event_id() -> str:
    """Generate unique event ID"""
    return str(uuid.uuid4())
