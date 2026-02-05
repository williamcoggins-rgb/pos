"""
Entitlement Ledger
Append-only storage for entitlements with fast query access.
Maintains current entitlement state for enforcement.
Supports both SQLite (local dev) and PostgreSQL (production).
"""

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from threading import Lock

from event_store import Event, EventType, CloudEventStore, _is_postgres_url


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
        self._use_postgres = _is_postgres_url(db_path)
        self._sqlite_conn = None

        if self._use_postgres:
            self._init_postgres()
        else:
            self._init_sqlite()

    def _get_pg_conn(self):
        """Get a psycopg2 connection"""
        import psycopg2
        url = self.db_path
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return psycopg2.connect(url)

    def _get_sqlite_conn(self):
        """Get SQLite connection (persistent for :memory:, new for file-based)"""
        if self.db_path == ":memory:":
            if self._sqlite_conn is None:
                self._sqlite_conn = sqlite3.connect(":memory:")
            return self._sqlite_conn
        return sqlite3.connect(self.db_path)

    def _init_postgres(self):
        """Create entitlements table in PostgreSQL"""
        conn = self._get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS entitlements (
                    barber_id TEXT PRIMARY KEY,
                    tier TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    entitlement_type TEXT NOT NULL,
                    access_list JSONB NOT NULL,
                    caps JSONB NOT NULL,
                    granted_at TEXT NOT NULL,
                    last_updated TEXT NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    blocked_reasons JSONB DEFAULT '[]'
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_tier ON entitlements(tier)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_active ON entitlements(is_active)")
            conn.commit()
        finally:
            conn.close()

    def _init_sqlite(self):
        """Create entitlements table in SQLite"""
        conn = self._get_sqlite_conn()
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tier ON entitlements(tier)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_active ON entitlements(is_active)")
        conn.commit()

    def _exec_sqlite(self, callback):
        """Execute a callback with a SQLite connection, handling :memory: connections"""
        conn = self._get_sqlite_conn()
        try:
            return callback(conn)
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def subscribe_to_events(self, cloud_store: CloudEventStore):
        """
        Subscribe to entitlement events from cloud store.
        Also replays existing events to build initial state.
        """
        self._cloud_store_ref = cloud_store
        self._initialized = False

        # Subscribe for future events
        cloud_store.subscribe(self._handle_event)

        # Replay existing events to build initial state
        self._ensure_initialized()

    def _ensure_initialized(self):
        """Replay events from store if ledger is empty (lazy init)."""
        if getattr(self, '_initialized', False):
            return

        store = getattr(self, '_cloud_store_ref', None)
        if store is None:
            return

        events = store.get_events()
        for event in events:
            if event.event_type in [
                EventType.BARBERSCORE_UPDATED,
                EventType.ENTITLEMENT_GRANTED,
                EventType.ENTITLEMENT_REVOKED,
                EventType.ENTITLEMENT_UPDATED,
            ]:
                self._handle_event(event)

        self._initialized = True

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

        if self._use_postgres:
            conn = self._get_pg_conn()
            try:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE entitlements SET score = %s, tier = %s, last_updated = %s WHERE barber_id = %s",
                    (score, tier, event.created_at, barber_id)
                )
                conn.commit()
            finally:
                conn.close()
        else:
            with self._lock:
                conn = self._get_sqlite_conn()
                conn.execute(
                    "UPDATE entitlements SET score = ?, tier = ?, last_updated = ? WHERE barber_id = ?",
                    (score, tier, event.created_at, barber_id)
                )
                conn.commit()

    def _grant_entitlement(self, event: Event):
        """Grant or update entitlement"""
        barber_id = event.payload["barber_id"]
        tier = event.payload["tier"]
        entitlement_type = event.payload["entitlement_type"]
        access_list = event.payload["access"]
        caps = event.payload["caps"]
        granted_at = event.payload["granted_at"]

        if self._use_postgres:
            conn = self._get_pg_conn()
            try:
                cur = conn.cursor()
                cur.execute("SELECT score FROM entitlements WHERE barber_id = %s", (barber_id,))
                row = cur.fetchone()
                score = row[0] if row else 0

                cur.execute("""
                    INSERT INTO entitlements
                    (barber_id, tier, score, entitlement_type, access_list, caps,
                     granted_at, last_updated, is_active, blocked_reasons)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, '[]')
                    ON CONFLICT(barber_id) DO UPDATE SET
                        tier = EXCLUDED.tier,
                        entitlement_type = EXCLUDED.entitlement_type,
                        access_list = EXCLUDED.access_list,
                        caps = EXCLUDED.caps,
                        granted_at = EXCLUDED.granted_at,
                        last_updated = EXCLUDED.last_updated,
                        is_active = TRUE,
                        blocked_reasons = '[]'
                """, (
                    barber_id, tier, score, entitlement_type,
                    json.dumps(access_list), json.dumps(caps),
                    granted_at, event.created_at,
                ))
                conn.commit()
            finally:
                conn.close()
        else:
            with self._lock:
                conn = self._get_sqlite_conn()
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT score FROM entitlements WHERE barber_id = ?", (barber_id,)
                )
                row = cursor.fetchone()
                score = row["score"] if row else 0

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
                    barber_id, tier, score, entitlement_type,
                    json.dumps(access_list), json.dumps(caps),
                    granted_at, event.created_at,
                ))
                conn.commit()

    def _revoke_entitlement(self, event: Event):
        """Revoke entitlement"""
        barber_id = event.payload["barber_id"]
        reasons = event.payload["reasons"]

        if self._use_postgres:
            conn = self._get_pg_conn()
            try:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE entitlements SET is_active = FALSE, blocked_reasons = %s, last_updated = %s WHERE barber_id = %s",
                    (json.dumps(reasons), event.created_at, barber_id)
                )
                conn.commit()
            finally:
                conn.close()
        else:
            with self._lock:
                conn = self._get_sqlite_conn()
                conn.execute(
                    "UPDATE entitlements SET is_active = 0, blocked_reasons = ?, last_updated = ? WHERE barber_id = ?",
                    (json.dumps(reasons), event.created_at, barber_id)
                )
                conn.commit()

    def _update_entitlement(self, event: Event):
        """Update entitlement details"""
        barber_id = event.payload["barber_id"]
        updates = event.payload.get("updates", {})

        set_clauses = []
        params = []

        if "tier" in updates:
            set_clauses.append("tier = %s" if self._use_postgres else "tier = ?")
            params.append(updates["tier"])

        if "access_list" in updates:
            set_clauses.append("access_list = %s" if self._use_postgres else "access_list = ?")
            params.append(json.dumps(updates["access_list"]))

        if "caps" in updates:
            set_clauses.append("caps = %s" if self._use_postgres else "caps = ?")
            params.append(json.dumps(updates["caps"]))

        set_clauses.append("last_updated = %s" if self._use_postgres else "last_updated = ?")
        params.append(event.created_at)
        params.append(barber_id)

        placeholder = "%s" if self._use_postgres else "?"
        query = f"UPDATE entitlements SET {', '.join(set_clauses)} WHERE barber_id = {placeholder}"

        if self._use_postgres:
            conn = self._get_pg_conn()
            try:
                cur = conn.cursor()
                cur.execute(query, params)
                conn.commit()
            finally:
                conn.close()
        else:
            with self._lock:
                conn = self._get_sqlite_conn()
                conn.execute(query, params)
                conn.commit()

    def get_entitlement(self, barber_id: str) -> Optional[CurrentEntitlement]:
        """Get current entitlement for a barber"""
        if self._use_postgres:
            return self._get_entitlement_pg(barber_id)
        return self._get_entitlement_sqlite(barber_id)

    def _get_entitlement_pg(self, barber_id: str) -> Optional[CurrentEntitlement]:
        conn = self._get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM entitlements WHERE barber_id = %s", (barber_id,))
            row = cur.fetchone()
            if not row:
                return None
            return CurrentEntitlement(
                barber_id=row[0],
                tier=row[1],
                score=row[2],
                entitlement_type=row[3],
                access_list=row[4] if isinstance(row[4], list) else json.loads(row[4]),
                caps=row[5] if isinstance(row[5], dict) else json.loads(row[5]),
                granted_at=row[6],
                last_updated=row[7],
                is_active=bool(row[8]),
                blocked_reasons=row[9] if isinstance(row[9], list) else (json.loads(row[9]) if row[9] else []),
            )
        finally:
            conn.close()

    def _get_entitlement_sqlite(self, barber_id: str) -> Optional[CurrentEntitlement]:
        conn = self._get_sqlite_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM entitlements WHERE barber_id = ?", (barber_id,)
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
        if self._use_postgres:
            conn = self._get_pg_conn()
            try:
                cur = conn.cursor()
                cur.execute("SELECT * FROM entitlements WHERE is_active = TRUE ORDER BY score DESC")
                rows = cur.fetchall()
                return [
                    CurrentEntitlement(
                        barber_id=row[0], tier=row[1], score=row[2],
                        entitlement_type=row[3],
                        access_list=row[4] if isinstance(row[4], list) else json.loads(row[4]),
                        caps=row[5] if isinstance(row[5], dict) else json.loads(row[5]),
                        granted_at=row[6], last_updated=row[7],
                        is_active=bool(row[8]),
                        blocked_reasons=row[9] if isinstance(row[9], list) else (json.loads(row[9]) if row[9] else []),
                    )
                    for row in rows
                ]
            finally:
                conn.close()
        else:
            conn = self._get_sqlite_conn()
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM entitlements WHERE is_active = 1 ORDER BY score DESC"
            )
            rows = cursor.fetchall()
            return [
                CurrentEntitlement(
                    barber_id=row["barber_id"], tier=row["tier"], score=row["score"],
                    entitlement_type=row["entitlement_type"],
                    access_list=json.loads(row["access_list"]),
                    caps=json.loads(row["caps"]),
                    granted_at=row["granted_at"], last_updated=row["last_updated"],
                    is_active=bool(row["is_active"]),
                    blocked_reasons=json.loads(row["blocked_reasons"]) if row["blocked_reasons"] else [],
                )
                for row in rows
            ]

    def get_barbers_by_tier(self, tier: str) -> List[str]:
        """Get all barber IDs in a specific tier"""
        if self._use_postgres:
            conn = self._get_pg_conn()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT barber_id FROM entitlements WHERE tier = %s AND is_active = TRUE", (tier,)
                )
                return [row[0] for row in cur.fetchall()]
            finally:
                conn.close()
        else:
            conn = self._get_sqlite_conn()
            cursor = conn.execute(
                "SELECT barber_id FROM entitlements WHERE tier = ? AND is_active = 1", (tier,)
            )
            return [row[0] for row in cursor.fetchall()]

    def rebuild_from_events(self, cloud_store: CloudEventStore):
        """Rebuild ledger from event store (disaster recovery)"""
        with self._lock:
            if self._use_postgres:
                conn = self._get_pg_conn()
                try:
                    cur = conn.cursor()
                    cur.execute("DELETE FROM entitlements")
                    conn.commit()
                finally:
                    conn.close()
            else:
                conn = self._get_sqlite_conn()
                conn.execute("DELETE FROM entitlements")
                conn.commit()

            events = cloud_store.get_events()
            for event in events:
                if event.event_type in [
                    EventType.BARBERSCORE_UPDATED,
                    EventType.ENTITLEMENT_GRANTED,
                    EventType.ENTITLEMENT_REVOKED,
                    EventType.ENTITLEMENT_UPDATED,
                ]:
                    self._handle_event(event)
