"""
Business Logic layer -- reconciliation.py

Implements the core inventory reconciliation engine. All inventory state
mutations are performed here, wrapped in SQLite transactions to guarantee
atomicity. No route handler may write to the database directly; all writes
must go through this module.

Layer: Business Logic (engine/)
Depends on: db/models.py, db/database.py
"""

from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from db.models import InventoryState, PickEvent, DamageReport


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class InsufficientInventoryError(Exception):
    """
    Raised when a requested operation would produce a negative Available
    or Physical count, violating the core inventory invariant.

    Layer: Business Logic
    """
    pass


class SKUNotFoundError(Exception):
    """
    Raised when a requested SKU does not exist in the inventory database.

    Layer: Business Logic
    """
    pass


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ReconciliationEngine:
    """
    Core business logic for inventory state mutations.

    Layer: Business Logic

    This class is the single point through which all inventory writes flow.
    Route handlers call engine methods; they never write to the database
    directly. This enforces the layered architecture constraint.

    All mutating methods wrap their reads and writes in a SQLAlchemy
    transaction. On any failure the transaction is rolled back and state
    is left unchanged (atomicity guarantee).
    """

    def __init__(self, db: Session):
        """
        Initialise the engine with an active database session.

        Parameters:
            db (Session): SQLAlchemy session injected by FastAPI's dependency system.
        """
        self.db = db

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_inventory(self, sku: str) -> InventoryState:
        """
        Return the current inventory state for a single SKU.

        Parameters:
            sku (str): the SKU identifier to look up.

        Returns:
            InventoryState: the ORM row for this SKU.

        Raises:
            SKUNotFoundError: if no InventoryState row exists for the SKU.
        """
        state = (
            self.db.query(InventoryState)
            .filter(InventoryState.sku == sku)
            .first()
        )
        if state is None:
            raise SKUNotFoundError(f"SKU '{sku}' not found in inventory.")
        return state

    def get_all_inventory(self) -> List[InventoryState]:
        """
        Return the current inventory state for all SKUs, ordered by SKU.

        Returns:
            list[InventoryState]: all rows from the inventory_state table.
        """
        return (
            self.db.query(InventoryState)
            .order_by(InventoryState.sku)
            .all()
        )

    # ------------------------------------------------------------------
    # Pick event
    # ------------------------------------------------------------------

    def process_pick(self, sku: str, quantity: int) -> InventoryState:
        """
        Process a pick event: decrement Physical and Reserved counts atomically.

        A pick represents units removed from the warehouse shelf to fulfil a
        committed order. Physical decreases (items leave the shelf) and
        Reserved decreases (the open-order commitment is fulfilled).
        Available = Physical - Reserved is mathematically unchanged by a pick,
        but is recalculated and persisted to keep the DB invariant explicit.

        Parameters:
            sku (str): the SKU being picked.
            quantity (int): number of units to pick (must be > 0).

        Returns:
            InventoryState: the updated inventory state after the pick.

        Raises:
            ValueError: if quantity <= 0.
            SKUNotFoundError: if the SKU does not exist.
            InsufficientInventoryError: if quantity exceeds the Reserved count
                (a pick can only draw against committed units).

        Architectural constraint: this is the ONLY place in the codebase where
        pick events are recorded and inventory decremented. Route handlers
        delegate here and never touch the DB directly.
        """
        if quantity <= 0:
            raise ValueError("Pick quantity must be a positive integer.")

        # --- Transaction boundary begins ---
        # Both the InventoryState update and the PickEvent audit record
        # are written in the same commit. Either both succeed or neither does.

        state = self.get_inventory(sku)

        # Business rule: a pick draws against reserved units only.
        # Reject if the requested quantity exceeds what has been reserved.
        if quantity > state.reserved:
            raise InsufficientInventoryError(
                f"Pick quantity {quantity} exceeds reserved count "
                f"{state.reserved} for SKU '{sku}'."
            )

        state.physical -= quantity
        state.reserved -= quantity
        # Recalculate available explicitly so the DB invariant is always
        # stored directly rather than inferred by callers.
        state.available = state.physical - state.reserved

        # Audit record -- persisted in the same transaction as the state update.
        self.db.add(PickEvent(sku=sku, quantity=quantity))

        # Commit both the state update and the event record atomically.
        self.db.commit()
        self.db.refresh(state)
        return state

    # ------------------------------------------------------------------
    # Damage report
    # ------------------------------------------------------------------

    def process_damage(self, sku: str, quantity: int) -> InventoryState:
        """
        Process a damage report: decrement Physical and Available counts atomically.

        Damaged units leave the warehouse in a non-sellable state.
        Physical decreases (items are gone) and Available decreases (they can
        no longer be sold). Reserved is unaffected -- those order commitments
        remain against the remaining undamaged stock.

        Parameters:
            sku (str): the SKU with damaged units.
            quantity (int): number of units damaged (must be > 0).

        Returns:
            InventoryState: the updated inventory state after the damage report.

        Raises:
            ValueError: if quantity <= 0.
            SKUNotFoundError: if the SKU does not exist.
            InsufficientInventoryError: if quantity exceeds the Available count.
                Available must never go negative -- this is the primary guard.

        Architectural constraint: same as process_pick -- only this method
        records damage events and decrements counts.
        """
        if quantity <= 0:
            raise ValueError("Damage quantity must be a positive integer.")

        # --- Transaction boundary begins ---
        state = self.get_inventory(sku)

        # Business rule: Available must not go negative.
        # This is the primary invariant enforced by the engine.
        if quantity > state.available:
            raise InsufficientInventoryError(
                f"Damage quantity {quantity} exceeds available count "
                f"{state.available} for SKU '{sku}'."
            )

        state.physical -= quantity
        state.available -= quantity
        # Reserved is unchanged; the invariant available = physical - reserved still holds.

        self.db.add(DamageReport(sku=sku, quantity=quantity))

        # Commit the state update and the damage record atomically.
        self.db.commit()
        self.db.refresh(state)
        return state
