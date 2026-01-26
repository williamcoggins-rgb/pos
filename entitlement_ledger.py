"""
Entitlement Ledger
Append-only storage for entitlements with fast query access.
Maintains current entitlement state for enforcement.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from threading import Lock

from event_store import Event, EventType, CloudEventStore


@dataclass
class CurrentEntitlement:
    """Current active entitlement for a barber"""
    barber_id: str
    tier: str
    score: int
    entitlement_type: str
    access_list: List[str]
    caps: Dict[str, int]
    granted_at: str
    last_updated: str
    is_active: bool = True
    blocked_reasons: List[str] = field(default_factory=list)


class EntitlementLedger:
    """
    Fast queryable storage for current entitlements.
    Subscribes to CloudEventStore and maintains materialized view.
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._lock = Lock()
        self._initialize_db()

    def _initialize_db(self):
        """Create entitlements table"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS entitlements (
                    barber_id TEXT PRIMARY KEY,
                    tier TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    entitlement_type TEXT NOT NULL,
                    access_list TEXT NOT NULL,
                    caps TEXT NOT NULL,
                    granted_at TEXT NOT NULL,
                    last_updated TEXT NOT NULL,
                    is_active INTEGER NOT NULL,
                    blocked_reasons TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tier
                ON entitlements(tier)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_active
                ON entitlements(is_active)
            """)
            conn.commit()

    def subscribe_to_events(self, cloud_store: CloudEventStore):
        """Subscribe to entitlement events from cloud store"""
        cloud_store.subscribe(self._handle_event)

    def _handle_event(self, event: Event):
        """Handle entitlement-related events"""
        if event.event_type == EventType.BARBERSCORE_UPDATED:
            self._update_score(event)
        elif event.event_type == EventType.ENTITLEMENT_GRANTED:
            self._grant_entitlement(event)
        elif event.event_type == EventType.ENTITLEMENT_REVOKED:
            self._revoke_entitlement(event)
        elif event.event_type == EventType.ENTITLEMENT_UPDATED:
            self._update_entitlement(event)

    def _update_score(self, event: Event):
        """Update BarberScore"""
        barber_id = event.payload["barber_id"]
        score = event.payload["score"]
        tier = event.payload["tier"]

        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE entitlements
                    SET score = ?, tier = ?, last_updated = ?
                    WHERE barber_id = ?
                """, (score, tier, event.created_at, barber_id))
                conn.commit()

    def _grant_entitlement(self, event: Event):
        """Grant or update entitlement"""
        barber_id = event.payload["barber_id"]
        tier = event.payload["tier"]
        entitlement_type = event.payload["entitlement_type"]
        access_list = event.payload["access"]
        caps = event.payload["caps"]
        granted_at = event.payload["granted_at"]

        # Get current score (if exists)
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT score FROM entitlements WHERE barber_id = ?",
                    (barber_id,)
                )
                row = cursor.fetchone()
                score = row["score"] if row else 0

                # Upsert entitlement
                conn.execute("""
                    INSERT INTO entitlements
                    (barber_id, tier, score, entitlement_type, access_list, caps,
                     granted_at, last_updated, is_active, blocked_reasons)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, '[]')
                    ON CONFLICT(barber_id) DO UPDATE SET
                        tier = excluded.tier,
                        entitlement_type = excluded.entitlement_type,
                        access_list = excluded.access_list,
                        caps = excluded.caps,
                        granted_at = excluded.granted_at,
                        last_updated = excluded.last_updated,
                        is_active = 1,
                        blocked_reasons = '[]'
                """, (
                    barber_id,
                    tier,
                    score,
                    entitlement_type,
                    json.dumps(access_list),
                    json.dumps(caps),
                    granted_at,
                    event.created_at,
                ))
                conn.commit()

    def _revoke_entitlement(self, event: Event):
        """Revoke entitlement"""
        barber_id = event.payload["barber_id"]
        reasons = event.payload["reasons"]

        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE entitlements
                    SET is_active = 0,
                        blocked_reasons = ?,
                        last_updated = ?
                    WHERE barber_id = ?
                """, (json.dumps(reasons), event.created_at, barber_id))
                conn.commit()

    def _update_entitlement(self, event: Event):
        """Update entitlement details"""
        barber_id = event.payload["barber_id"]
        updates = event.payload.get("updates", {})

        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                # Build dynamic update query
                set_clauses = []
                params = []

                if "tier" in updates:
                    set_clauses.append("tier = ?")
                    params.append(updates["tier"])

                if "access_list" in updates:
                    set_clauses.append("access_list = ?")
                    params.append(json.dumps(updates["access_list"]))

                if "caps" in updates:
                    set_clauses.append("caps = ?")
                    params.append(json.dumps(updates["caps"]))

                set_clauses.append("last_updated = ?")
                params.append(event.created_at)

                params.append(barber_id)

                query = f"""
                    UPDATE entitlements
                    SET {', '.join(set_clauses)}
                    WHERE barber_id = ?
                """

                conn.execute(query, params)
                conn.commit()

    def get_entitlement(self, barber_id: str) -> Optional[CurrentEntitlement]:
        """Get current entitlement for a barber"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM entitlements WHERE barber_id = ?",
                (barber_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            return CurrentEntitlement(
                barber_id=row["barber_id"],
                tier=row["tier"],
                score=row["score"],
                entitlement_type=row["entitlement_type"],
                access_list=json.loads(row["access_list"]),
                caps=json.loads(row["caps"]),
                granted_at=row["granted_at"],
                last_updated=row["last_updated"],
                is_active=bool(row["is_active"]),
                blocked_reasons=json.loads(row["blocked_reasons"]) if row["blocked_reasons"] else [],
            )

    def has_access(self, barber_id: str, access_type: str) -> bool:
        """Check if barber has specific access"""
        entitlement = self.get_entitlement(barber_id)

        if not entitlement or not entitlement.is_active:
            return False

        return access_type in entitlement.access_list

    def get_cap(self, barber_id: str, cap_name: str) -> Optional[int]:
        """Get specific cap value for barber"""
        entitlement = self.get_entitlement(barber_id)

        if not entitlement or not entitlement.is_active:
            return None

        return entitlement.caps.get(cap_name)

    def get_all_active_entitlements(self) -> List[CurrentEntitlement]:
        """Get all active entitlements"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM entitlements WHERE is_active = 1 ORDER BY score DESC"
            )
            rows = cursor.fetchall()

            return [
                CurrentEntitlement(
                    barber_id=row["barber_id"],
                    tier=row["tier"],
                    score=row["score"],
                    entitlement_type=row["entitlement_type"],
                    access_list=json.loads(row["access_list"]),
                    caps=json.loads(row["caps"]),
                    granted_at=row["granted_at"],
                    last_updated=row["last_updated"],
                    is_active=bool(row["is_active"]),
                    blocked_reasons=json.loads(row["blocked_reasons"]) if row["blocked_reasons"] else [],
                )
                for row in rows
            ]

    def get_barbers_by_tier(self, tier: str) -> List[str]:
        """Get all barber IDs in a specific tier"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT barber_id FROM entitlements WHERE tier = ? AND is_active = 1",
                (tier,)
            )
            return [row[0] for row in cursor.fetchall()]

    def rebuild_from_events(self, cloud_store: CloudEventStore):
        """Rebuild ledger from event store (disaster recovery)"""
        with self._lock:
            # Clear existing data
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM entitlements")
                conn.commit()

            # Replay all entitlement events
            events = cloud_store.get_events()
            for event in events:
                if event.event_type in [
                    EventType.BARBERSCORE_UPDATED,
                    EventType.ENTITLEMENT_GRANTED,
                    EventType.ENTITLEMENT_REVOKED,
                    EventType.ENTITLEMENT_UPDATED,
                ]:
                    self._handle_event(event)
