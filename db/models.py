"""
Persistence layer -- models.py

Defines all SQLAlchemy ORM models for the inventory system.
Each class maps to one SQLite table and captures a distinct aspect of
warehouse state or operational history.

Layer: Persistence (db/)
Depends on: db/database.py (Base)
"""

from sqlalchemy import Column, String, Integer, DateTime, func

from db.database import Base


class Product(Base):
    """
    Warehouse product record -- one row per SKU.

    Layer: Persistence
    Stores the human-readable product name and the physical bin location
    where units are stored in the warehouse.
    """

    __tablename__ = "products"

    sku = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    bin_location = Column(String, nullable=False)


class InventoryState(Base):
    """
    Current inventory counts for a single SKU.

    Layer: Persistence

    Invariant enforced by the reconciliation engine:
        available = physical - reserved
        available >= 0 at all times

    This row is the single source of truth for warehouse stock levels.
    External storefront state is always treated as downstream of this record.
    """

    __tablename__ = "inventory_state"

    sku = Column(String, primary_key=True, index=True)
    physical = Column(Integer, nullable=False)   # units physically in warehouse
    reserved = Column(Integer, nullable=False)   # units committed to open orders
    available = Column(Integer, nullable=False)  # physical - reserved


class PickEvent(Base):
    """
    Audit record for a pick attempt (successful or rejected).

    Layer: Persistence

    status is "success" when the pick was applied, "rejected" when the engine
    refused it. rejection_reason is populated only on rejection.
    Immutable after insertion -- never updated, only inserted.
    """

    __tablename__ = "pick_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sku = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="success")
    rejection_reason = Column(String, nullable=True)
    timestamp = Column(DateTime, server_default=func.now())


class DamageReport(Base):
    """
    Audit record for a damage report attempt (successful or rejected).

    Layer: Persistence

    status is "success" when the report was applied, "rejected" when refused.
    rejection_reason is populated only on rejection.
    Immutable after insertion -- never updated, only inserted.
    """

    __tablename__ = "damage_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sku = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="success")
    rejection_reason = Column(String, nullable=True)
    timestamp = Column(DateTime, server_default=func.now())


class OrderEvent(Base):
    """
    Audit record for an incoming customer order attempt (successful or rejected).

    Layer: Persistence

    A successful order increments Reserved and decrements Available. Physical is
    unchanged. status is "success" or "rejected"; rejection_reason is populated
    only on rejection.
    Immutable after insertion -- never updated, only inserted.
    """

    __tablename__ = "order_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sku = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="success")
    rejection_reason = Column(String, nullable=True)
    timestamp = Column(DateTime, server_default=func.now())


class SyncLog(Base):
    """
    Record of one full sync run to the storefront adapter.

    Layer: Persistence
    One row is created per sync run, capturing the overall outcome and
    the number of SKUs pushed to the adapter.
    """

    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operation = Column(String, nullable=False)   # e.g. "sync_all"
    outcome = Column(String, nullable=False)     # e.g. "success"
    details = Column(String, nullable=True)      # e.g. "30 SKUs synced"
    timestamp = Column(DateTime, server_default=func.now())
