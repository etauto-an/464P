"""
Business Logic layer tests -- test_engine.py

Tests the ReconciliationEngine directly using an in-memory database session.
No HTTP layer is involved. This is the most important test module because
the engine enforces all inventory invariants.

Layer tested: Business Logic (engine/)
"""

import pytest

from engine.reconciliation import ReconciliationEngine, SKUNotFoundError, InsufficientInventoryError
from db.models import InventoryState, PickEvent, DamageReport, OrderEvent


class TestGetInventory:
    """Tests for ReconciliationEngine.get_inventory()."""

    def test_returns_state_for_known_sku(self, seeded_session):
        """get_inventory returns the correct InventoryState for an existing SKU."""
        engine = ReconciliationEngine(seeded_session)
        state = engine.get_inventory("SKU-A")
        assert state.sku == "SKU-A"
        assert state.physical == 10
        assert state.reserved == 3
        assert state.available == 7

    def test_raises_for_unknown_sku(self, seeded_session):
        """get_inventory raises SKUNotFoundError for a SKU that does not exist."""
        engine = ReconciliationEngine(seeded_session)
        with pytest.raises(SKUNotFoundError):
            engine.get_inventory("DOES-NOT-EXIST")


class TestGetAllInventory:
    """Tests for ReconciliationEngine.get_all_inventory()."""

    def test_returns_all_rows(self, seeded_session):
        """get_all_inventory returns one row for every seeded SKU."""
        engine = ReconciliationEngine(seeded_session)
        states = engine.get_all_inventory()
        skus = {s.sku for s in states}
        assert {"SKU-A", "SKU-B", "SKU-C"}.issubset(skus)

    def test_returns_ordered_by_sku(self, seeded_session):
        """Results are ordered alphabetically by SKU."""
        engine = ReconciliationEngine(seeded_session)
        states = engine.get_all_inventory()
        skus = [s.sku for s in states]
        assert skus == sorted(skus)

    def test_empty_database_returns_empty_list(self, db_session):
        """Returns an empty list when no SKUs exist."""
        engine = ReconciliationEngine(db_session)
        assert engine.get_all_inventory() == []


class TestProcessPick:
    """Tests for ReconciliationEngine.process_pick()."""

    def test_decrements_physical_and_reserved(self, seeded_session):
        """
        A valid pick decrements Physical and Reserved by the quantity.
        Available = Physical - Reserved is unchanged by a pick.
        """
        engine = ReconciliationEngine(seeded_session)
        # SKU-A: physical=10, reserved=3, available=7
        state = engine.process_pick("SKU-A", 2)

        assert state.physical == 8   # 10 - 2
        assert state.reserved == 1   # 3 - 2
        assert state.available == 7  # unchanged: 8 - 1

    def test_pick_entire_reserved_quantity(self, seeded_session):
        """A pick equal to the full reserved count is accepted."""
        engine = ReconciliationEngine(seeded_session)
        # SKU-B: physical=5, reserved=5, available=0
        state = engine.process_pick("SKU-B", 5)

        assert state.physical == 0
        assert state.reserved == 0
        assert state.available == 0

    def test_pick_single_unit(self, seeded_session):
        """A pick of quantity 1 is accepted."""
        engine = ReconciliationEngine(seeded_session)
        state = engine.process_pick("SKU-A", 1)
        assert state.physical == 9
        assert state.reserved == 2

    def test_raises_for_zero_quantity(self, seeded_session):
        """A pick of quantity 0 raises ValueError."""
        engine = ReconciliationEngine(seeded_session)
        with pytest.raises(ValueError):
            engine.process_pick("SKU-A", 0)

    def test_raises_for_negative_quantity(self, seeded_session):
        """A pick of negative quantity raises ValueError."""
        engine = ReconciliationEngine(seeded_session)
        with pytest.raises(ValueError):
            engine.process_pick("SKU-A", -1)

    def test_raises_when_quantity_exceeds_reserved(self, seeded_session):
        """A pick larger than the reserved count raises InsufficientInventoryError."""
        engine = ReconciliationEngine(seeded_session)
        # SKU-A: reserved=3; picking 4 must be rejected.
        with pytest.raises(InsufficientInventoryError):
            engine.process_pick("SKU-A", 4)

    def test_raises_for_unknown_sku(self, seeded_session):
        """A pick against a non-existent SKU raises SKUNotFoundError."""
        engine = ReconciliationEngine(seeded_session)
        with pytest.raises(SKUNotFoundError):
            engine.process_pick("NO-SUCH-SKU", 1)

    def test_pick_event_audit_row_created(self, seeded_session):
        """A successful pick inserts one PickEvent audit record with status='success'."""
        engine = ReconciliationEngine(seeded_session)
        engine.process_pick("SKU-A", 2)

        events = seeded_session.query(PickEvent).filter_by(sku="SKU-A").all()
        assert len(events) == 1
        assert events[0].quantity == 2
        assert events[0].status == "success"
        assert events[0].rejection_reason is None

    def test_failed_pick_creates_rejected_audit_row(self, seeded_session):
        """A rejected pick writes a PickEvent row with status='rejected'."""
        engine = ReconciliationEngine(seeded_session)
        with pytest.raises(InsufficientInventoryError):
            engine.process_pick("SKU-A", 99)

        events = seeded_session.query(PickEvent).filter_by(sku="SKU-A").all()
        assert len(events) == 1
        assert events[0].status == "rejected"
        assert events[0].rejection_reason is not None

    def test_failed_pick_does_not_mutate_state(self, seeded_session):
        """A rejected pick leaves InventoryState unchanged (atomicity guarantee)."""
        engine = ReconciliationEngine(seeded_session)
        with pytest.raises(InsufficientInventoryError):
            engine.process_pick("SKU-A", 99)

        state = engine.get_inventory("SKU-A")
        assert state.physical == 10
        assert state.reserved == 3
        assert state.available == 7

    def test_pick_unknown_sku_creates_rejected_audit_row(self, seeded_session):
        """A pick against an unknown SKU writes a rejected PickEvent row."""
        engine = ReconciliationEngine(seeded_session)
        with pytest.raises(SKUNotFoundError):
            engine.process_pick("NO-SUCH-SKU", 1)

        events = seeded_session.query(PickEvent).filter_by(sku="NO-SUCH-SKU").all()
        assert len(events) == 1
        assert events[0].status == "rejected"


class TestProcessDamage:
    """Tests for ReconciliationEngine.process_damage()."""

    def test_decrements_physical_and_available(self, seeded_session):
        """
        A valid damage report decrements Physical and Available by the quantity.
        Reserved is unchanged.
        """
        engine = ReconciliationEngine(seeded_session)
        # SKU-A: physical=10, reserved=3, available=7
        state = engine.process_damage("SKU-A", 3)

        assert state.physical == 7    # 10 - 3
        assert state.reserved == 3    # unchanged
        assert state.available == 4   # 7 - 3

    def test_damage_entire_available_quantity(self, seeded_session):
        """Damage equal to the full available count is accepted (available reaches zero)."""
        engine = ReconciliationEngine(seeded_session)
        # SKU-A: available=7
        state = engine.process_damage("SKU-A", 7)

        assert state.available == 0
        assert state.physical == 3   # 10 - 7; reserved (3) still committed

    def test_raises_for_zero_quantity(self, seeded_session):
        """A damage report of quantity 0 raises ValueError."""
        engine = ReconciliationEngine(seeded_session)
        with pytest.raises(ValueError):
            engine.process_damage("SKU-A", 0)

    def test_raises_for_negative_quantity(self, seeded_session):
        """A damage report of negative quantity raises ValueError."""
        engine = ReconciliationEngine(seeded_session)
        with pytest.raises(ValueError):
            engine.process_damage("SKU-A", -5)

    def test_raises_when_quantity_exceeds_available(self, seeded_session):
        """
        A damage report larger than Available raises InsufficientInventoryError.
        This is the primary invariant guard: Available must not go negative.
        """
        engine = ReconciliationEngine(seeded_session)
        # SKU-A: available=7; damaging 8 must be rejected.
        with pytest.raises(InsufficientInventoryError):
            engine.process_damage("SKU-A", 8)

    def test_raises_when_available_is_zero(self, seeded_session):
        """Damage against a SKU with zero available raises InsufficientInventoryError."""
        engine = ReconciliationEngine(seeded_session)
        # SKU-B: available=0
        with pytest.raises(InsufficientInventoryError):
            engine.process_damage("SKU-B", 1)

    def test_raises_for_unknown_sku(self, seeded_session):
        """A damage report against a non-existent SKU raises SKUNotFoundError."""
        engine = ReconciliationEngine(seeded_session)
        with pytest.raises(SKUNotFoundError):
            engine.process_damage("NO-SUCH-SKU", 1)

    def test_damage_report_audit_row_created(self, seeded_session):
        """A successful damage report inserts one DamageReport audit record with status='success'."""
        engine = ReconciliationEngine(seeded_session)
        engine.process_damage("SKU-A", 2)

        reports = seeded_session.query(DamageReport).filter_by(sku="SKU-A").all()
        assert len(reports) == 1
        assert reports[0].quantity == 2
        assert reports[0].status == "success"
        assert reports[0].rejection_reason is None

    def test_failed_damage_creates_rejected_audit_row(self, seeded_session):
        """A rejected damage report writes a DamageReport row with status='rejected'."""
        engine = ReconciliationEngine(seeded_session)
        with pytest.raises(InsufficientInventoryError):
            engine.process_damage("SKU-A", 99)

        reports = seeded_session.query(DamageReport).filter_by(sku="SKU-A").all()
        assert len(reports) == 1
        assert reports[0].status == "rejected"
        assert reports[0].rejection_reason is not None

    def test_failed_damage_does_not_mutate_state(self, seeded_session):
        """A rejected damage report leaves InventoryState unchanged (atomicity guarantee)."""
        engine = ReconciliationEngine(seeded_session)
        with pytest.raises(InsufficientInventoryError):
            engine.process_damage("SKU-A", 99)

        state = engine.get_inventory("SKU-A")
        assert state.physical == 10
        assert state.reserved == 3
        assert state.available == 7

    def test_available_invariant_physical_minus_reserved(self, seeded_session):
        """After damage, available == physical - reserved holds exactly."""
        engine = ReconciliationEngine(seeded_session)
        state = engine.process_damage("SKU-A", 4)
        assert state.available == state.physical - state.reserved


class TestProcessOrder:
    """Tests for ReconciliationEngine.process_order()."""

    def test_increments_reserved_and_decrements_available(self, seeded_session):
        """
        A valid order increments Reserved and decrements Available by the quantity.
        Physical is unchanged -- units are still on the shelf.
        """
        engine = ReconciliationEngine(seeded_session)
        # SKU-A: physical=10, reserved=3, available=7
        state = engine.process_order("SKU-A", 3)

        assert state.physical == 10   # unchanged
        assert state.reserved == 6    # 3 + 3
        assert state.available == 4   # 7 - 3

    def test_order_entire_available_quantity(self, seeded_session):
        """An order equal to the full available count is accepted (available reaches zero)."""
        engine = ReconciliationEngine(seeded_session)
        # SKU-A: available=7
        state = engine.process_order("SKU-A", 7)

        assert state.available == 0
        assert state.reserved == 10   # 3 + 7
        assert state.physical == 10   # unchanged

    def test_order_single_unit(self, seeded_session):
        """An order of quantity 1 is accepted."""
        engine = ReconciliationEngine(seeded_session)
        state = engine.process_order("SKU-C", 1)  # SKU-C: available=1
        assert state.reserved == 1
        assert state.available == 0

    def test_raises_for_zero_quantity(self, seeded_session):
        """An order of quantity 0 raises ValueError."""
        engine = ReconciliationEngine(seeded_session)
        with pytest.raises(ValueError):
            engine.process_order("SKU-A", 0)

    def test_raises_for_negative_quantity(self, seeded_session):
        """An order of negative quantity raises ValueError."""
        engine = ReconciliationEngine(seeded_session)
        with pytest.raises(ValueError):
            engine.process_order("SKU-A", -1)

    def test_raises_when_quantity_exceeds_available(self, seeded_session):
        """
        An order larger than Available raises InsufficientInventoryError.
        Available must not go negative -- stock cannot be oversold.
        """
        engine = ReconciliationEngine(seeded_session)
        # SKU-A: available=7; ordering 8 must be rejected.
        with pytest.raises(InsufficientInventoryError):
            engine.process_order("SKU-A", 8)

    def test_raises_when_available_is_zero(self, seeded_session):
        """An order against a SKU with zero available raises InsufficientInventoryError."""
        engine = ReconciliationEngine(seeded_session)
        # SKU-B: available=0
        with pytest.raises(InsufficientInventoryError):
            engine.process_order("SKU-B", 1)

    def test_raises_for_unknown_sku(self, seeded_session):
        """An order against a non-existent SKU raises SKUNotFoundError."""
        engine = ReconciliationEngine(seeded_session)
        with pytest.raises(SKUNotFoundError):
            engine.process_order("NO-SUCH-SKU", 1)

    def test_order_event_audit_row_created(self, seeded_session):
        """A successful order inserts one OrderEvent audit record with status='success'."""
        engine = ReconciliationEngine(seeded_session)
        engine.process_order("SKU-A", 2)

        events = seeded_session.query(OrderEvent).filter_by(sku="SKU-A").all()
        assert len(events) == 1
        assert events[0].quantity == 2
        assert events[0].status == "success"
        assert events[0].rejection_reason is None

    def test_failed_order_creates_rejected_audit_row(self, seeded_session):
        """A rejected order writes an OrderEvent row with status='rejected'."""
        engine = ReconciliationEngine(seeded_session)
        with pytest.raises(InsufficientInventoryError):
            engine.process_order("SKU-A", 99)

        events = seeded_session.query(OrderEvent).filter_by(sku="SKU-A").all()
        assert len(events) == 1
        assert events[0].status == "rejected"
        assert events[0].rejection_reason is not None

    def test_failed_order_does_not_mutate_state(self, seeded_session):
        """A rejected order leaves InventoryState unchanged (atomicity guarantee)."""
        engine = ReconciliationEngine(seeded_session)
        with pytest.raises(InsufficientInventoryError):
            engine.process_order("SKU-A", 99)

        state = engine.get_inventory("SKU-A")
        assert state.physical == 10
        assert state.reserved == 3
        assert state.available == 7

    def test_available_invariant_physical_minus_reserved(self, seeded_session):
        """After an order, available == physical - reserved holds exactly."""
        engine = ReconciliationEngine(seeded_session)
        state = engine.process_order("SKU-A", 3)
        assert state.available == state.physical - state.reserved

    def test_order_then_pick_full_lifecycle(self, seeded_session):
        """
        An order followed by a pick completes the full reservation lifecycle:
        order commits stock, pick clears the commitment and removes physical units.
        Available is unchanged across the full cycle.
        """
        engine = ReconciliationEngine(seeded_session)
        # SKU-A: physical=10, reserved=3, available=7
        engine.process_order("SKU-A", 4)
        # Now: physical=10, reserved=7, available=3
        state = engine.process_pick("SKU-A", 4)
        # Now: physical=6, reserved=3, available=3
        assert state.physical == 6
        assert state.reserved == 3
        assert state.available == 3
