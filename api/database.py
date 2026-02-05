"""
Database and service singletons.
Core modules use SQLite directly - this layer manages singleton instances
and wires them together with file-based SQLite storage.
"""

import os
import sys

# Ensure parent directory is importable for core modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from event_store import CloudEventStore, LocalEventQueue
from entitlement_ledger import EntitlementLedger
from eligibility_engine import EligibilityEngine
from procurement_service import ProcurementService

# Data directory for SQLite databases (configurable via env)
_DATA_DIR = os.environ.get(
    "DATA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"),
)
os.makedirs(_DATA_DIR, exist_ok=True)

# Config directory for scoring/entitlement JSON rules
_CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")

# Singletons
_cloud_store = None
_local_queue = None
_entitlement_ledger = None
_eligibility_engine = None
_procurement_service = None


def _db_path(filename: str) -> str:
    return os.path.join(_DATA_DIR, filename)


def get_cloud_store() -> CloudEventStore:
    global _cloud_store
    if _cloud_store is None:
        _cloud_store = CloudEventStore(_db_path("events.db"))
    return _cloud_store


def get_local_queue() -> LocalEventQueue:
    global _local_queue
    if _local_queue is None:
        _local_queue = LocalEventQueue(_db_path("local_queue.db"))
    return _local_queue


def get_entitlement_ledger() -> EntitlementLedger:
    global _entitlement_ledger
    if _entitlement_ledger is None:
        _entitlement_ledger = EntitlementLedger(_db_path("entitlements.db"))
        _entitlement_ledger.subscribe_to_events(get_cloud_store())
    return _entitlement_ledger


def get_eligibility_engine() -> EligibilityEngine:
    global _eligibility_engine
    if _eligibility_engine is None:
        _eligibility_engine = EligibilityEngine(
            get_cloud_store(),
            config_dir=_CONFIG_DIR,
        )
    return _eligibility_engine


def get_procurement_service() -> ProcurementService:
    global _procurement_service
    if _procurement_service is None:
        _procurement_service = ProcurementService(get_cloud_store())
    return _procurement_service
