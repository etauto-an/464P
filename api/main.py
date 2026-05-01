"""
Presentation layer -- main.py

FastAPI application entry point. Defines all REST endpoints for the
Multi-Channel Inventory Sync System and wires them to the reconciliation
engine and storefront adapter.

Route handlers are intentionally thin: they validate input, delegate all
business logic to the ReconciliationEngine, and format the response.
No route handler writes to the database directly.

Layer: Presentation (api/)
Depends on: engine/reconciliation.py, adapters/shopify_dummy.py, db/models.py

Run with:
    uvicorn api.main:app --reload
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import engine, get_db
from db.models import Base, SyncLog, Product
from engine.reconciliation import (
    ReconciliationEngine,
    SKUNotFoundError,
    InsufficientInventoryError,
)
from adapters.shopify_dummy import ShopifyDummyAdapter

# Create all tables on startup (idempotent; safe to call every run).
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Multi-Channel Inventory Sync System",
    description=(
        "Middleware synchronisation engine maintaining consistency between "
        "a warehouse and multiple e-commerce storefronts. CPSC 464 prototype."
    ),
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# CORS -- allow the local Vite dev server (port 5173) to call the API.
# TODO: Phase II -- restrict origins to the production frontend domain.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Shared adapter instance.
# Routed through the engine rather than writing directly to the DB.
# This enforces the layered architecture constraint -- the API layer
# has no direct dependency on the persistence layer.
# ---------------------------------------------------------------------------
adapter = ShopifyDummyAdapter()


# ---------------------------------------------------------------------------
# Pydantic request/response schemas
# ---------------------------------------------------------------------------

class EventRequest(BaseModel):
    """
    Shared request body for pick and damage events.

    Layer: Presentation
    """
    sku: str
    quantity: int


class InventoryResponse(BaseModel):
    """
    Response shape for a single SKU's inventory state.

    Layer: Presentation
    """
    sku: str
    name: Optional[str] = None
    bin_location: Optional[str] = None
    physical: int
    reserved: int
    available: int

    class Config:
        from_attributes = True


class SyncLogResponse(BaseModel):
    """
    Response shape for a single sync log entry.

    Layer: Presentation
    """
    id: int
    sku: str
    operation: str
    outcome: str
    timestamp: Optional[datetime]

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Helper: build an InventoryResponse enriched with product metadata
# ---------------------------------------------------------------------------

def _enrich(state, db: Session) -> InventoryResponse:
    """
    Merge an InventoryState row with its corresponding Product row.

    Parameters:
        state: InventoryState ORM object.
        db (Session): active database session used to look up the Product.

    Returns:
        InventoryResponse: combined state and product metadata.
    """
    product = db.query(Product).filter(Product.sku == state.sku).first()
    return InventoryResponse(
        sku=state.sku,
        name=product.name if product else None,
        bin_location=product.bin_location if product else None,
        physical=state.physical,
        reserved=state.reserved,
        available=state.available,
    )


# ---------------------------------------------------------------------------
# Inventory read endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/inventory",
    response_model=list[InventoryResponse],
    summary="Get all SKU inventory states",
)
def get_all_inventory(db: Session = Depends(get_db)):
    """
    Return current Physical/Reserved/Available counts for every SKU.

    Returns:
        list[InventoryResponse]: all SKUs ordered by SKU code.
    """
    # Routed through the engine -- API layer has no direct DB dependency.
    engine_instance = ReconciliationEngine(db)
    states = engine_instance.get_all_inventory()
    return [_enrich(s, db) for s in states]


@app.get(
    "/inventory/{sku}",
    response_model=InventoryResponse,
    summary="Get a single SKU inventory state",
)
def get_inventory(sku: str, db: Session = Depends(get_db)):
    """
    Return current counts for a single SKU.

    Parameters:
        sku (str): SKU identifier (path parameter).

    Returns:
        InventoryResponse: the requested SKU's state.

    Raises:
        404: if the SKU does not exist.
    """
    engine_instance = ReconciliationEngine(db)
    try:
        state = engine_instance.get_inventory(sku)
    except SKUNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _enrich(state, db)


# ---------------------------------------------------------------------------
# Event endpoints
# ---------------------------------------------------------------------------

@app.post(
    "/events/pick",
    response_model=InventoryResponse,
    summary="Submit a pick event",
)
def pick_event(request: EventRequest, db: Session = Depends(get_db)):
    """
    Process a pick event: decrement Physical and Reserved for a SKU.

    Parameters:
        request (EventRequest): {sku, quantity}

    Returns:
        InventoryResponse: updated inventory state after the pick.

    Raises:
        400: if quantity is invalid or exceeds reserved stock.
        404: if the SKU does not exist.
    """
    # Routed through the engine rather than writing directly to the DB.
    # This enforces the layered architecture constraint -- the API layer
    # has no direct dependency on the persistence layer.
    engine_instance = ReconciliationEngine(db)
    try:
        state = engine_instance.process_pick(request.sku, request.quantity)
    except SKUNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (InsufficientInventoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _enrich(state, db)


@app.post(
    "/events/damage",
    response_model=InventoryResponse,
    summary="Submit a damage report",
)
def damage_event(request: EventRequest, db: Session = Depends(get_db)):
    """
    Process a damage report: decrement Physical and Available for a SKU.

    Parameters:
        request (EventRequest): {sku, quantity}

    Returns:
        InventoryResponse: updated inventory state after the damage report.

    Raises:
        400: if quantity is invalid or exceeds available stock.
        404: if the SKU does not exist.
    """
    # Routed through the engine rather than writing directly to the DB.
    engine_instance = ReconciliationEngine(db)
    try:
        state = engine_instance.process_damage(request.sku, request.quantity)
    except SKUNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (InsufficientInventoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _enrich(state, db)


# ---------------------------------------------------------------------------
# Sync endpoints
# ---------------------------------------------------------------------------

@app.post(
    "/sync",
    summary="Sync all SKUs to the storefront adapter",
)
def sync_inventory(db: Session = Depends(get_db)):
    """
    Push current Available counts for all SKUs to the storefront adapter
    and record the outcome in SyncLog.

    This is the adapter interface boundary crossing point: the engine
    retrieves all inventory states, and for each SKU the adapter's
    write_inventory() is called. The engine layer is not involved in
    the sync loop -- sync is an API-layer orchestration concern.

    Returns:
        dict: {"synced": int, "errors": int, "results": list[dict]}
    """
    engine_instance = ReconciliationEngine(db)
    states = engine_instance.get_all_inventory()

    results = []
    errors = 0

    for state in states:
        # Adapter interface boundary: cross from API layer into Adapter layer.
        # The adapter receives only the abstract write_inventory() call.
        response = adapter.write_inventory(state.sku, state.available)

        outcome = "success" if response.get("success") else "error"
        if outcome == "error":
            errors += 1

        # Record each sync outcome in SyncLog for auditability.
        log_entry = SyncLog(
            sku=state.sku,
            operation="write_inventory",
            outcome=outcome,
        )
        db.add(log_entry)
        results.append({"sku": state.sku, "outcome": outcome, "message": response.get("message")})

    db.commit()

    return {
        "synced": len(states) - errors,
        "errors": errors,
        "results": results,
    }


@app.get(
    "/sync/logs",
    response_model=list[SyncLogResponse],
    summary="Retrieve sync log entries",
)
def get_sync_logs(db: Session = Depends(get_db)):
    """
    Return all sync log entries, most recent first.

    Returns:
        list[SyncLogResponse]: all rows from sync_logs ordered by timestamp desc.
    """
    logs = (
        db.query(SyncLog)
        .order_by(SyncLog.timestamp.desc())
        .all()
    )
    return logs
