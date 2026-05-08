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

from db.models import InventoryState, PickEvent, DamageReport, OrderEvent


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

        All attempts -- successful or rejected -- are recorded in pick_events
        with a status of "success" or "rejected" and an optional rejection_reason.

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
        try:
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
            self.db.add(PickEvent(sku=sku, quantity=quantity, status="success"))

            # Commit both the state update and the event record atomically.
            self.db.commit()
            self.db.refresh(state)
            return state

        except (ValueError, SKUNotFoundError, InsufficientInventoryError) as exc:
            # Roll back any partial state, then record the rejected attempt.
            self.db.rollback()
            self.db.add(PickEvent(sku=sku, quantity=quantity, status="rejected", rejection_reason=str(exc)))
            self.db.commit()
            raise

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

        All attempts -- successful or rejected -- are recorded in damage_reports
        with a status of "success" or "rejected" and an optional rejection_reason.

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
        try:
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

            self.db.add(DamageReport(sku=sku, quantity=quantity, status="success"))

            # Commit the state update and the damage record atomically.
            self.db.commit()
            self.db.refresh(state)
            return state

        except (ValueError, SKUNotFoundError, InsufficientInventoryError) as exc:
            # Roll back any partial state, then record the rejected attempt.
            self.db.rollback()
            self.db.add(DamageReport(sku=sku, quantity=quantity, status="rejected", rejection_reason=str(exc)))
            self.db.commit()
            raise

    # ------------------------------------------------------------------
    # Order event
    # ------------------------------------------------------------------

    def process_order(self, sku: str, quantity: int) -> InventoryState:
        """
        Process an incoming customer order: increment Reserved and decrement
        Available atomically.

        An order commits stock to a customer before it is physically picked.
        Physical is unchanged (units are still on the shelf); Reserved increases
        (the commitment is recorded); Available decreases (those units can no
        longer be sold to anyone else).

        All attempts -- successful or rejected -- are recorded in order_events
        with a status of "success" or "rejected" and an optional rejection_reason.

        Parameters:
            sku (str): the SKU being ordered.
            quantity (int): number of units ordered (must be > 0).

        Returns:
            InventoryState: the updated inventory state after the order.

        Raises:
            ValueError: if quantity <= 0.
            SKUNotFoundError: if the SKU does not exist.
            InsufficientInventoryError: if quantity exceeds Available.
                Available must never go negative -- an order cannot be accepted
                for stock that does not exist or is already committed.

        Architectural constraint: same as process_pick and process_damage --
        only this method records order events and mutates counts. Route
        handlers delegate here and never touch the DB directly.
        """
        try:
            if quantity <= 0:
                raise ValueError("Order quantity must be a positive integer.")

            # --- Transaction boundary begins ---
            # Both the InventoryState update and the OrderEvent audit record
            # are written in the same commit. Either both succeed or neither does.
            state = self.get_inventory(sku)

            # Business rule: Available must not go negative.
            # An order can only be accepted if enough uncommitted stock exists.
            if quantity > state.available:
                raise InsufficientInventoryError(
                    f"Order quantity {quantity} exceeds available count "
                    f"{state.available} for SKU '{sku}'."
                )

            state.reserved += quantity
            state.available -= quantity
            # Physical is unchanged; the invariant available = physical - reserved still holds.

            # Audit record -- persisted in the same transaction as the state update.
            self.db.add(OrderEvent(sku=sku, quantity=quantity, status="success"))

            # Commit both the state update and the event record atomically.
            self.db.commit()
            self.db.refresh(state)
            return state

        except (ValueError, SKUNotFoundError, InsufficientInventoryError) as exc:
            # Roll back any partial state, then record the rejected attempt.
            self.db.rollback()
            self.db.add(OrderEvent(sku=sku, quantity=quantity, status="rejected", rejection_reason=str(exc)))
            self.db.commit()
            raise
