"""
Database connection and session management
Provides PostgreSQL connections for event store and entitlement ledger
"""

from contextlib import contextmanager
from typing import Generator
import sys
import os

# Add parent directory to path to import our modules
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from event_store import CloudEventStore, LocalEventQueue
from entitlement_ledger import EntitlementLedger
from eligibility_engine import EligibilityEngine
from procurement_service import ProcurementService
from api.config import get_settings

settings = get_settings()


# Singleton instances
_cloud_store = None
_local_queue = None
_entitlement_ledger = None
_eligibility_engine = None
_procurement_service = None


def get_cloud_store() -> CloudEventStore:
    """Get or create CloudEventStore singleton"""
    global _cloud_store
    if _cloud_store is None:
        # Convert postgres:// to postgresql:// if needed (for SQLAlchemy)
        db_url = settings.DATABASE_URL
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)

        _cloud_store = CloudEventStore(db_url)
    return _cloud_store


def get_local_queue() -> LocalEventQueue:
    """Get or create LocalEventQueue singleton"""
    global _local_queue
    if _local_queue is None:
        # Use local SQLite for queue (offline buffer)
        _local_queue = LocalEventQueue("local_queue.db")
    return _local_queue


def get_entitlement_ledger() -> EntitlementLedger:
    """Get or create EntitlementLedger singleton"""
    global _entitlement_ledger
    if _entitlement_ledger is None:
        # Convert postgres:// to postgresql:// if needed
        db_url = settings.DATABASE_URL
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)

        _entitlement_ledger = EntitlementLedger(db_url)
        # Subscribe to cloud store events
        _entitlement_ledger.subscribe_to_events(get_cloud_store())
    return _entitlement_ledger


def get_eligibility_engine() -> EligibilityEngine:
    """Get or create EligibilityEngine singleton"""
    global _eligibility_engine
    if _eligibility_engine is None:
        _eligibility_engine = EligibilityEngine(
            get_cloud_store(),
            config_dir="config"
        )
    return _eligibility_engine


def get_procurement_service() -> ProcurementService:
    """Get or create ProcurementService singleton"""
    global _procurement_service
    if _procurement_service is None:
        _procurement_service = ProcurementService(get_cloud_store())
    return _procurement_service


# Dependency injection for FastAPI
def get_db_dependencies():
    """Get all database dependencies for DI"""
    return {
        "cloud_store": get_cloud_store(),
        "local_queue": get_local_queue(),
        "entitlement_ledger": get_entitlement_ledger(),
        "eligibility_engine": get_eligibility_engine(),
        "procurement_service": get_procurement_service(),
    }
