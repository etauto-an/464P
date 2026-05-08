"""
Persistence layer tests -- test_db.py

Verifies that the ORM models, table schema, and session mechanics work
correctly against an in-memory SQLite database. No business logic is tested
here -- the focus is on the persistence layer in isolation.

Layer tested: Persistence (db/)
"""

import pytest
from sqlalchemy.exc import IntegrityError

from db.models import Product, InventoryState, PickEvent, DamageReport, OrderEvent, SyncLog


class TestProductModel:
    """Tests for the Product ORM model."""

    def test_insert_and_query(self, db_session):
        """A Product row can be inserted and retrieved by primary key (sku)."""
        db_session.add(Product(sku="SKU-001", name="Widget", bin_location="B-12"))
        db_session.commit()

        row = db_session.query(Product).filter_by(sku="SKU-001").first()
        assert row is not None
        assert row.name == "Widget"
        assert row.bin_location == "B-12"

    def test_primary_key_is_sku(self, db_session):
        """Inserting duplicate SKU raises IntegrityError."""
        db_session.add(Product(sku="DUP", name="A", bin_location="X-1"))
        db_session.commit()
        db_session.add(Product(sku="DUP", name="B", bin_location="X-2"))
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_name_not_nullable(self, db_session):
        """Product.name has nullable=False; omitting it raises IntegrityError."""
        db_session.add(Product(sku="SKU-NULL", name=None, bin_location="A-1"))
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestInventoryStateModel:
    """Tests for the InventoryState ORM model."""

    def test_insert_and_query(self, db_session):
        """An InventoryState row can be inserted and all three counts retrieved."""
        db_session.add(InventoryState(sku="SKU-INV", physical=20, reserved=5, available=15))
        db_session.commit()

        row = db_session.query(InventoryState).filter_by(sku="SKU-INV").first()
        assert row.physical == 20
        assert row.reserved == 5
        assert row.available == 15

    def test_counts_are_mutable(self, db_session):
        """InventoryState counts can be updated and the change persists."""
        db_session.add(InventoryState(sku="SKU-MUT", physical=10, reserved=2, available=8))
        db_session.commit()

        row = db_session.query(InventoryState).filter_by(sku="SKU-MUT").first()
        row.physical = 9
        row.reserved = 2
        row.available = 7
        db_session.commit()

        refreshed = db_session.query(InventoryState).filter_by(sku="SKU-MUT").first()
        assert refreshed.physical == 9
        assert refreshed.available == 7


class TestAuditModels:
    """Tests for PickEvent, DamageReport, OrderEvent, and SyncLog audit tables."""

    def test_pick_event_insert(self, db_session):
        """A successful PickEvent row is inserted with status='success'."""
        db_session.add(PickEvent(sku="SKU-PE", quantity=3, status="success"))
        db_session.commit()

        row = db_session.query(PickEvent).filter_by(sku="SKU-PE").first()
        assert row is not None
        assert row.quantity == 3
        assert row.status == "success"
        assert row.rejection_reason is None

    def test_pick_event_rejected_insert(self, db_session):
        """A rejected PickEvent row stores status and rejection_reason."""
        db_session.add(PickEvent(sku="SKU-PE-R", quantity=99, status="rejected", rejection_reason="exceeds reserved"))
        db_session.commit()

        row = db_session.query(PickEvent).filter_by(sku="SKU-PE-R").first()
        assert row.status == "rejected"
        assert row.rejection_reason == "exceeds reserved"

    def test_damage_report_insert(self, db_session):
        """A successful DamageReport row is inserted with status='success'."""
        db_session.add(DamageReport(sku="SKU-DR", quantity=2, status="success"))
        db_session.commit()

        row = db_session.query(DamageReport).filter_by(sku="SKU-DR").first()
        assert row is not None
        assert row.quantity == 2
        assert row.status == "success"

    def test_order_event_insert(self, db_session):
        """A successful OrderEvent row is inserted with status='success'."""
        db_session.add(OrderEvent(sku="SKU-OE", quantity=5, status="success"))
        db_session.commit()

        row = db_session.query(OrderEvent).filter_by(sku="SKU-OE").first()
        assert row is not None
        assert row.quantity == 5
        assert row.status == "success"

    def test_sync_log_insert(self, db_session):
        """A SyncLog row is inserted with the correct fields."""
        db_session.add(SyncLog(operation="sync_all", outcome="success", details="10 SKUs synced"))
        db_session.commit()

        row = db_session.query(SyncLog).first()
        assert row.operation == "sync_all"
        assert row.outcome == "success"
        assert row.details == "10 SKUs synced"

    def test_sync_log_details_nullable(self, db_session):
        """SyncLog.details is nullable; omitting it does not raise an error."""
        db_session.add(SyncLog(operation="sync_all", outcome="success"))
        db_session.commit()

        row = db_session.query(SyncLog).first()
        assert row.details is None

    def test_multiple_events_same_sku(self, db_session):
        """Multiple audit rows for the same SKU are all persisted (no unique constraint)."""
        db_session.add(PickEvent(sku="SKU-MULTI", quantity=1))
        db_session.add(PickEvent(sku="SKU-MULTI", quantity=2))
        db_session.commit()

        rows = db_session.query(PickEvent).filter_by(sku="SKU-MULTI").all()
        assert len(rows) == 2
