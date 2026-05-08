"""
Presentation layer tests -- test_api.py

Tests the FastAPI route handlers via TestClient. No real server process is
started. The in-memory SQLite database is injected by overriding FastAPI's
get_db dependency, so every request hits the test database instead of the
production inventory.db file.

Layer tested: Presentation (api/)
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.main import app
from db.database import Base, get_db
from db.models import Product, InventoryState, SyncLog, PickEvent, DamageReport, OrderEvent


# ---------------------------------------------------------------------------
# Per-test client fixture with an injected in-memory database
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """
    Return a FastAPI TestClient backed by a fresh in-memory SQLite database.

    The get_db dependency is overridden for the lifetime of this fixture so
    that every route handler receives a session bound to the test engine.
    The override is removed after the test to avoid leaking state.

    Yields:
        TestClient: configured client with in-memory DB injection.
    """
    # StaticPool forces all sessions to share one connection, so the seed
    # inserts and the route handler queries all see the same in-memory database.
    # Without it, each new connection gets an empty, separate SQLite database.
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        """Dependency override: yield a session bound to the in-memory engine."""
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    # Inject the override into the FastAPI app.
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        # Expose the session factory so tests can seed data directly.
        c._test_session_factory = TestSession
        yield c

    # Remove override after the test.
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


def _seed(client, sku: str, physical: int, reserved: int):
    """
    Insert one Product and one InventoryState row into the test database.

    Parameters:
        client: the TestClient fixture (carries _test_session_factory).
        sku (str): SKU identifier.
        physical (int): physical unit count.
        reserved (int): reserved unit count.
    """
    session = client._test_session_factory()
    available = physical - reserved
    session.add(Product(sku=sku, name=f"Product {sku}", bin_location="A-01"))
    session.add(InventoryState(sku=sku, physical=physical, reserved=reserved, available=available))
    session.commit()
    session.close()


# ---------------------------------------------------------------------------
# GET /inventory
# ---------------------------------------------------------------------------

class TestGetAllInventory:
    """Tests for GET /inventory."""

    def test_empty_returns_200_and_empty_list(self, client):
        """Returns HTTP 200 and an empty list when no SKUs exist."""
        response = client.get("/inventory")
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_all_seeded_skus(self, client):
        """Returns one entry per seeded SKU."""
        _seed(client, "SKU-A", 10, 3)
        _seed(client, "SKU-B", 5, 5)

        response = client.get("/inventory")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_response_shape(self, client):
        """Each entry contains the required inventory response fields."""
        _seed(client, "SKU-SHAPE", 8, 2)

        response = client.get("/inventory")
        item = response.json()[0]
        assert {"sku", "physical", "reserved", "available"}.issubset(item.keys())


# ---------------------------------------------------------------------------
# GET /inventory/{sku}
# ---------------------------------------------------------------------------

class TestGetSingleInventory:
    """Tests for GET /inventory/{sku}."""

    def test_returns_correct_counts(self, client):
        """Returns the correct physical/reserved/available counts for a known SKU."""
        _seed(client, "SKU-READ", 15, 4)

        response = client.get("/inventory/SKU-READ")
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "SKU-READ"
        assert data["physical"] == 15
        assert data["reserved"] == 4
        assert data["available"] == 11

    def test_unknown_sku_returns_404(self, client):
        """Returns HTTP 404 for a SKU that does not exist."""
        response = client.get("/inventory/DOES-NOT-EXIST")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /events/order
# ---------------------------------------------------------------------------

class TestOrderEvent:
    """Tests for POST /events/order."""

    def test_valid_order_returns_200(self, client):
        """A valid order returns HTTP 200 with updated counts."""
        _seed(client, "SKU-ORD", 10, 3)

        response = client.post("/events/order", json={"sku": "SKU-ORD", "quantity": 4})
        assert response.status_code == 200
        data = response.json()
        assert data["physical"] == 10   # unchanged
        assert data["reserved"] == 7    # 3 + 4
        assert data["available"] == 3   # 7 - 4

    def test_order_entire_available_returns_200(self, client):
        """An order equal to the full available count returns HTTP 200."""
        _seed(client, "SKU-ORDALL", 10, 3)

        response = client.post("/events/order", json={"sku": "SKU-ORDALL", "quantity": 7})
        assert response.status_code == 200
        data = response.json()
        assert data["available"] == 0

    def test_order_exceeds_available_returns_400(self, client):
        """An order larger than available returns HTTP 400."""
        _seed(client, "SKU-ORDOV", 10, 3)

        response = client.post("/events/order", json={"sku": "SKU-ORDOV", "quantity": 8})
        assert response.status_code == 400

    def test_order_zero_available_returns_400(self, client):
        """An order against a SKU with zero available returns HTTP 400."""
        _seed(client, "SKU-ORDNOAV", 5, 5)

        response = client.post("/events/order", json={"sku": "SKU-ORDNOAV", "quantity": 1})
        assert response.status_code == 400

    def test_order_zero_quantity_returns_400(self, client):
        """An order of quantity 0 returns HTTP 400."""
        _seed(client, "SKU-ORDZERO", 10, 3)

        response = client.post("/events/order", json={"sku": "SKU-ORDZERO", "quantity": 0})
        assert response.status_code == 400

    def test_order_unknown_sku_returns_404(self, client):
        """An order against an unknown SKU returns HTTP 404."""
        response = client.post("/events/order", json={"sku": "GHOST", "quantity": 1})
        assert response.status_code == 404

    def test_order_then_pick_lifecycle(self, client):
        """An order followed by a pick completes the full reservation lifecycle."""
        _seed(client, "SKU-LIFE", 10, 2)
        # available = 8; place an order for 3
        client.post("/events/order", json={"sku": "SKU-LIFE", "quantity": 3})
        # reserved = 5, available = 5; now pick 3
        response = client.post("/events/pick", json={"sku": "SKU-LIFE", "quantity": 3})
        assert response.status_code == 200
        data = response.json()
        assert data["physical"] == 7
        assert data["reserved"] == 2
        assert data["available"] == 5


# ---------------------------------------------------------------------------
# POST /events/pick
# ---------------------------------------------------------------------------

class TestPickEvent:
    """Tests for POST /events/pick."""

    def test_valid_pick_returns_200(self, client):
        """A valid pick returns HTTP 200 with updated counts."""
        _seed(client, "SKU-PICK", 10, 3)

        response = client.post("/events/pick", json={"sku": "SKU-PICK", "quantity": 2})
        assert response.status_code == 200
        data = response.json()
        assert data["physical"] == 8
        assert data["reserved"] == 1
        assert data["available"] == 7  # unchanged by a pick

    def test_pick_entire_reserved_returns_200(self, client):
        """A pick equal to the full reserved count returns HTTP 200."""
        _seed(client, "SKU-FULL", 5, 5)

        response = client.post("/events/pick", json={"sku": "SKU-FULL", "quantity": 5})
        assert response.status_code == 200

    def test_pick_exceeds_reserved_returns_400(self, client):
        """A pick larger than reserved returns HTTP 400."""
        _seed(client, "SKU-OVER", 10, 3)

        response = client.post("/events/pick", json={"sku": "SKU-OVER", "quantity": 10})
        assert response.status_code == 400

    def test_pick_zero_quantity_returns_400(self, client):
        """A pick of quantity 0 returns HTTP 400."""
        _seed(client, "SKU-ZERO", 10, 3)

        response = client.post("/events/pick", json={"sku": "SKU-ZERO", "quantity": 0})
        assert response.status_code == 400

    def test_pick_unknown_sku_returns_404(self, client):
        """A pick against an unknown SKU returns HTTP 404."""
        response = client.post("/events/pick", json={"sku": "GHOST", "quantity": 1})
        assert response.status_code == 404

    def test_pick_state_persists_across_requests(self, client):
        """The updated state from a pick is visible in a subsequent GET."""
        _seed(client, "SKU-PERSIST", 10, 5)
        client.post("/events/pick", json={"sku": "SKU-PERSIST", "quantity": 3})

        response = client.get("/inventory/SKU-PERSIST")
        data = response.json()
        assert data["physical"] == 7
        assert data["reserved"] == 2


# ---------------------------------------------------------------------------
# POST /events/damage
# ---------------------------------------------------------------------------

class TestDamageEvent:
    """Tests for POST /events/damage."""

    def test_valid_damage_returns_200(self, client):
        """A valid damage report returns HTTP 200 with updated counts."""
        _seed(client, "SKU-DMG", 10, 3)

        response = client.post("/events/damage", json={"sku": "SKU-DMG", "quantity": 4})
        assert response.status_code == 200
        data = response.json()
        assert data["physical"] == 6
        assert data["reserved"] == 3   # unchanged
        assert data["available"] == 3  # 7 - 4

    def test_damage_exceeds_available_returns_400(self, client):
        """A damage report larger than available returns HTTP 400."""
        _seed(client, "SKU-DMGOV", 10, 3)

        # available=7; damaging 8 must be rejected
        response = client.post("/events/damage", json={"sku": "SKU-DMGOV", "quantity": 8})
        assert response.status_code == 400

    def test_damage_zero_available_returns_400(self, client):
        """A damage report against a SKU with zero available returns HTTP 400."""
        _seed(client, "SKU-NOAV", 5, 5)

        response = client.post("/events/damage", json={"sku": "SKU-NOAV", "quantity": 1})
        assert response.status_code == 400

    def test_damage_zero_quantity_returns_400(self, client):
        """A damage report of quantity 0 returns HTTP 400."""
        _seed(client, "SKU-DZERО", 10, 3)

        response = client.post("/events/damage", json={"sku": "SKU-DZERО", "quantity": 0})
        assert response.status_code == 400

    def test_damage_unknown_sku_returns_404(self, client):
        """A damage report against an unknown SKU returns HTTP 404."""
        response = client.post("/events/damage", json={"sku": "GHOST", "quantity": 1})
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /sync
# ---------------------------------------------------------------------------

class TestSyncInventory:
    """Tests for POST /sync."""

    def test_empty_inventory_syncs_zero(self, client):
        """Sync with no SKUs returns synced=0."""
        response = client.post("/sync")
        assert response.status_code == 200
        assert response.json()["synced"] == 0

    def test_sync_returns_sku_count(self, client):
        """Sync returns synced equal to the number of SKUs."""
        _seed(client, "SKU-S1", 10, 2)
        _seed(client, "SKU-S2", 5, 1)

        response = client.post("/sync")
        assert response.status_code == 200
        assert response.json()["synced"] == 2

    def test_sync_creates_one_log_entry_per_run(self, client):
        """A sync run writes exactly one SyncLog row regardless of SKU count."""
        _seed(client, "SKU-L1", 8, 2)
        _seed(client, "SKU-L2", 4, 1)
        client.post("/sync")

        session = client._test_session_factory()
        logs = session.query(SyncLog).all()
        session.close()
        assert len(logs) == 1
        assert logs[0].operation == "sync_all"
        assert logs[0].outcome == "success"

    def test_sync_log_details_contains_sku_count(self, client):
        """The SyncLog details field records how many SKUs were synced."""
        _seed(client, "SKU-D1", 10, 2)
        _seed(client, "SKU-D2", 5, 1)
        client.post("/sync")

        session = client._test_session_factory()
        log = session.query(SyncLog).first()
        session.close()
        assert "2" in log.details


# ---------------------------------------------------------------------------
# GET /sync/logs
# ---------------------------------------------------------------------------

class TestGetSyncLogs:
    """Tests for GET /sync/logs."""

    def test_empty_returns_200_and_empty_list(self, client):
        """Returns HTTP 200 and an empty list when no sync logs exist."""
        response = client.get("/sync/logs")
        assert response.status_code == 200
        assert response.json() == []

    def test_logs_appear_after_sync(self, client):
        """One sync log entry is visible via GET /sync/logs after a sync run."""
        _seed(client, "SKU-LOGQ", 10, 2)
        client.post("/sync")

        response = client.get("/sync/logs")
        assert response.status_code == 200
        logs = response.json()
        assert len(logs) == 1
        assert logs[0]["operation"] == "sync_all"
        assert logs[0]["outcome"] == "success"

    def test_log_response_shape(self, client):
        """Each log entry contains the required fields."""
        _seed(client, "SKU-SHAPE", 10, 2)
        client.post("/sync")

        entry = client.get("/sync/logs").json()[0]
        assert {"id", "operation", "outcome", "details"}.issubset(entry.keys())

    def test_multiple_syncs_produce_multiple_log_entries(self, client):
        """Each sync run appends a new log entry."""
        _seed(client, "SKU-MULTI", 10, 2)
        client.post("/sync")
        client.post("/sync")
        client.post("/sync")

        logs = client.get("/sync/logs").json()
        assert len(logs) == 3

    def test_limit_restricts_number_of_results(self, client):
        """limit=N returns at most N entries."""
        _seed(client, "SKU-LIM", 10, 2)
        for _ in range(5):
            client.post("/sync")

        logs = client.get("/sync/logs?limit=3").json()
        assert len(logs) == 3

    def test_offset_skips_entries(self, client):
        """offset=N skips the N most recent entries."""
        _seed(client, "SKU-OFF", 10, 2)
        for _ in range(4):
            client.post("/sync")

        all_logs = client.get("/sync/logs").json()
        page2    = client.get("/sync/logs?limit=2&offset=2").json()

        assert page2[0]["id"] == all_logs[2]["id"]
        assert page2[1]["id"] == all_logs[3]["id"]

    def test_offset_beyond_total_returns_empty(self, client):
        """An offset larger than the total number of rows returns an empty list."""
        _seed(client, "SKU-OFFBIG", 10, 2)
        client.post("/sync")

        logs = client.get("/sync/logs?offset=999").json()
        assert logs == []

    def test_invalid_limit_zero_returns_400(self, client):
        """limit=0 returns HTTP 400."""
        response = client.get("/sync/logs?limit=0")
        assert response.status_code == 400

    def test_invalid_limit_over_max_returns_400(self, client):
        """limit=201 returns HTTP 400."""
        response = client.get("/sync/logs?limit=201")
        assert response.status_code == 400

    def test_negative_offset_returns_400(self, client):
        """offset=-1 returns HTTP 400."""
        response = client.get("/sync/logs?offset=-1")
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /events/logs
# ---------------------------------------------------------------------------

class TestGetEventLogs:
    """Tests for GET /events/logs."""

    def test_empty_returns_200_and_empty_list(self, client):
        """Returns HTTP 200 and an empty list when no events exist."""
        response = client.get("/events/logs")
        assert response.status_code == 200
        assert response.json() == []

    def test_order_event_appears_in_log(self, client):
        """An order submitted via POST /events/order appears in GET /events/logs."""
        _seed(client, "SKU-EV", 10, 2)
        client.post("/events/order", json={"sku": "SKU-EV", "quantity": 3})

        logs = client.get("/events/logs").json()
        assert len(logs) == 1
        assert logs[0]["event_type"] == "order"
        assert logs[0]["sku"] == "SKU-EV"
        assert logs[0]["quantity"] == 3

    def test_pick_event_appears_in_log(self, client):
        """A pick submitted via POST /events/pick appears in GET /events/logs."""
        _seed(client, "SKU-PK", 10, 5)
        client.post("/events/pick", json={"sku": "SKU-PK", "quantity": 2})

        logs = client.get("/events/logs").json()
        assert len(logs) == 1
        assert logs[0]["event_type"] == "pick"
        assert logs[0]["quantity"] == 2

    def test_damage_event_appears_in_log(self, client):
        """A damage report via POST /events/damage appears in GET /events/logs."""
        _seed(client, "SKU-DM", 10, 2)
        client.post("/events/damage", json={"sku": "SKU-DM", "quantity": 3})

        logs = client.get("/events/logs").json()
        assert len(logs) == 1
        assert logs[0]["event_type"] == "damage"
        assert logs[0]["quantity"] == 3

    def test_all_event_types_appear_together(self, client):
        """Orders, picks, and damage reports all appear in the same log."""
        _seed(client, "SKU-ALL", 20, 5)
        client.post("/events/order",  json={"sku": "SKU-ALL", "quantity": 2})
        client.post("/events/pick",   json={"sku": "SKU-ALL", "quantity": 3})
        client.post("/events/damage", json={"sku": "SKU-ALL", "quantity": 1})

        logs = client.get("/events/logs").json()
        event_types = {e["event_type"] for e in logs}
        assert event_types == {"order", "pick", "damage"}

    def test_response_shape(self, client):
        """Each entry contains the required fields."""
        _seed(client, "SKU-SH", 10, 2)
        client.post("/events/order", json={"sku": "SKU-SH", "quantity": 1})

        entry = client.get("/events/logs").json()[0]
        assert {"id", "event_type", "sku", "quantity", "status", "rejection_reason", "timestamp"}.issubset(entry.keys())

    def test_successful_event_has_success_status(self, client):
        """A successful event log entry has status='success' and no rejection_reason."""
        _seed(client, "SKU-OK", 10, 2)
        client.post("/events/order", json={"sku": "SKU-OK", "quantity": 1})

        entry = client.get("/events/logs").json()[0]
        assert entry["status"] == "success"
        assert entry["rejection_reason"] is None

    def test_rejected_event_appears_in_log_with_rejected_status(self, client):
        """A rejected event (quantity exceeds available) still appears in the log with status='rejected'."""
        _seed(client, "SKU-FAIL", 5, 5)
        client.post("/events/order", json={"sku": "SKU-FAIL", "quantity": 1})  # available=0, will fail

        logs = client.get("/events/logs").json()
        assert len(logs) == 1
        assert logs[0]["status"] == "rejected"
        assert logs[0]["rejection_reason"] is not None

    def test_rejected_event_rejection_reason_is_descriptive(self, client):
        """The rejection_reason field contains a non-empty string explaining the refusal."""
        _seed(client, "SKU-WHY", 10, 3)
        client.post("/events/pick", json={"sku": "SKU-WHY", "quantity": 99})

        entry = client.get("/events/logs").json()[0]
        assert isinstance(entry["rejection_reason"], str)
        assert len(entry["rejection_reason"]) > 0

    def test_unknown_sku_event_appears_as_rejected(self, client):
        """An event against an unknown SKU appears in the log as rejected."""
        client.post("/events/order", json={"sku": "GHOST-SKU", "quantity": 1})

        logs = client.get("/events/logs").json()
        assert len(logs) == 1
        assert logs[0]["status"] == "rejected"
        assert logs[0]["sku"] == "GHOST-SKU"

    def test_invalid_limit_returns_400(self, client):
        """limit=0 returns HTTP 400."""
        response = client.get("/events/logs?limit=0")
        assert response.status_code == 400
