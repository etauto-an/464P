CPSC 464 -- Multi-Channel Inventory Sync System
Test Suite Documentation
================================================


OVERVIEW
--------
The test suite covers all four layers of the system's architecture. Every test
runs against an in-memory SQLite database (sqlite:///:memory:) so there are no
filesystem side effects and no dependency on the production inventory.db file.
The database is created fresh for each test function and destroyed when it ends.

73 tests across 4 files, organized to mirror the project structure:

    tests/
    |-- conftest.py       # shared fixtures (no tests)
    |-- test_db.py        # Persistence layer  (9 tests)
    |-- test_engine.py    # Business Logic layer (25 tests)
    |-- test_adapters.py  # Adapter layer (16 tests)
    |-- test_api.py       # Presentation layer (23 tests)


DEPENDENCIES
------------
The following packages are required to run the tests. They are not needed
to run the application itself.

    pytest
    pytest-cov
    httpx          (required internally by FastAPI's TestClient)

Install them with:

    pip install pytest pytest-cov httpx


HOW TO RUN
----------
All commands should be run from the project root (the directory that contains
the api/, engine/, db/, and tests/ folders).

Run the full suite:

    python -m pytest tests/

Run with verbose output (one line per test):

    python -m pytest tests/ -v

Run a single file:

    python -m pytest tests/test_engine.py -v

Run a single test class:

    python -m pytest tests/test_engine.py::TestProcessPick -v

Run a single test by name:

    python -m pytest tests/test_engine.py::TestProcessPick::test_raises_when_quantity_exceeds_reserved -v

Run with a coverage report printed to the terminal:

    python -m pytest tests/ --cov=. --cov-report=term-missing

    The --cov-report=term-missing flag prints a line-by-line summary showing
    which lines were not executed by any test.

Generate an HTML coverage report (opens as a website):

    python -m pytest tests/ --cov=. --cov-report=html
    # then open htmlcov/index.html in a browser


TEST FILES IN DETAIL
--------------------

conftest.py
    Contains the shared pytest fixtures used across all test files. No tests
    live here. Key fixtures:

    db_engine       -- creates a fresh in-memory SQLAlchemy engine with all
                       tables and tears it down after each test.
    db_session      -- yields a SQLAlchemy session bound to db_engine.
    seeded_session  -- a db_session pre-loaded with three test SKUs chosen to
                       exercise boundary conditions:
                         SKU-A  physical=10  reserved=3  available=7
                         SKU-B  physical=5   reserved=5  available=0
                         SKU-C  physical=1   reserved=0  available=1

test_db.py  (Persistence Layer)
    Tests the SQLAlchemy ORM models directly. No engine or route handler logic
    is involved -- only table operations.

    TestProductModel (3 tests)
        Verifies that Product rows can be inserted and queried by SKU, that
        duplicate SKUs raise an IntegrityError, and that the name column
        rejects NULL values.

    TestInventoryStateModel (2 tests)
        Verifies that InventoryState rows store all three count columns and
        that those counts can be updated and re-read correctly.

    TestAuditModels (4 tests)
        Verifies that PickEvent, DamageReport, and SyncLog rows can be
        inserted and queried. Also confirms that multiple audit rows for the
        same SKU are all persisted (there is no unique constraint on these
        tables -- every event creates a new row).

test_engine.py  (Business Logic Layer)
    Tests the ReconciliationEngine class by calling its methods directly with
    an in-memory database session. No HTTP layer is involved.

    TestGetInventory (2 tests)
        get_inventory() returns the correct row for a known SKU and raises
        SKUNotFoundError for an unknown one.

    TestGetAllInventory (3 tests)
        get_all_inventory() returns all rows, returns them sorted by SKU, and
        returns an empty list when the database is empty.

    TestProcessPick (10 tests)
        Covers pick event processing: valid picks decrement Physical and
        Reserved (Available is mathematically unchanged); a pick equal to the
        full reserved count is accepted; quantity=0 and quantity<0 raise
        ValueError; a quantity exceeding reserved raises
        InsufficientInventoryError; an unknown SKU raises SKUNotFoundError.

        Two atomicity tests verify that a rejected pick leaves the
        InventoryState row unchanged AND creates no PickEvent audit row --
        confirming that the transaction boundary prevents partial writes.

    TestProcessDamage (11 tests)
        Covers damage report processing: valid damage decrements Physical and
        Available (Reserved is unchanged); damage equal to the full available
        count is accepted (Available reaches zero); quantity=0 and quantity<0
        raise ValueError; a quantity exceeding Available raises
        InsufficientInventoryError (this is the primary invariant guard --
        Available must never go negative); an unknown SKU raises
        SKUNotFoundError. One test confirms the invariant
        available == physical - reserved holds exactly after damage.

        An atomicity test verifies that a rejected damage report leaves the
        InventoryState row unchanged.

test_adapters.py  (Adapter Layer)
    Tests the StorefrontAdapter abstract base class and the ShopifyDummyAdapter
    concrete implementation. No database or HTTP layer is involved.

    TestStorefrontAdapterABC (4 tests)
        Confirms that the ABC cannot be instantiated directly and that a
        subclass omitting either abstract method (read_inventory or
        write_inventory) raises TypeError on instantiation. A complete
        subclass instantiates without error.

    TestShopifyDummyAdapterReadInventory (5 tests)
        Verifies that read_inventory() returns a dict containing the required
        contract keys (sku, quantity, source), that the sku field echoes the
        input, and that quantity is a non-negative integer.

    TestShopifyDummyAdapterWriteInventory (7 tests)
        Verifies that write_inventory() returns a dict with the required
        contract keys (sku, success, message). Tests use the ERROR_RATE
        attribute to force deterministic outcomes: ERROR_RATE=0.0 guarantees
        success=True; ERROR_RATE=1.0 guarantees success=False. Both success
        and error paths are verified to satisfy the contract.

test_api.py  (Presentation Layer)
    Tests all six API routes using FastAPI's TestClient. No real server process
    is started. The in-memory database is injected by overriding FastAPI's
    get_db dependency, so route handlers hit the test database rather than the
    production inventory.db file.

    Note on StaticPool: the API fixture uses SQLAlchemy's StaticPool so that
    all sessions (the seed helper and the route handler) share one underlying
    connection. Without this, each new session in an in-memory SQLite database
    gets a completely separate, empty database.

    TestGetAllInventory (3 tests)
        GET /inventory returns 200 and an empty list with no data, returns
        one entry per seeded SKU, and each entry has the required fields.

    TestGetSingleInventory (2 tests)
        GET /inventory/{sku} returns the correct counts for a known SKU and
        returns 404 for an unknown one.

    TestPickEvent (6 tests)
        POST /events/pick: valid pick returns 200 with updated counts; full
        reserved pick returns 200; quantity exceeding reserved returns 400;
        quantity=0 returns 400; unknown SKU returns 404. A persistence test
        confirms the updated state is visible in a subsequent GET request.

    TestDamageEvent (5 tests)
        POST /events/damage: valid damage returns 200 with updated counts;
        quantity exceeding available returns 400; damage against zero-available
        SKU returns 400; quantity=0 returns 400; unknown SKU returns 404.

    TestSyncInventory (4 tests)
        POST /sync: syncing with no SKUs returns synced=0 errors=0; a sync
        over two SKUs returns two result entries; sync writes one SyncLog row
        per SKU to the database; synced+errors equals the total SKU count.

    TestGetSyncLogs (3 tests)
        GET /sync/logs returns 200 and an empty list before any sync; returns
        entries after a sync run; each entry has the required fields (id, sku,
        operation, outcome).
