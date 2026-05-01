# PROJECT_PLAN.md -- Multi-Channel Inventory Sync System

## Phase 0: Setup

**Goals:** Repository initialized, dependencies installed, database connected.

**Tasks:**
- Initialize repository with structure defined in CLAUDE.md
- Create `requirements.txt` with FastAPI, SQLAlchemy, Alembic, uvicorn
- Configure SQLite connection in `db/database.py`
- Define SQLAlchemy models in `db/models.py`:
  - `Product` (sku, name, bin_location)
  - `InventoryState` (sku, physical, reserved, available)
  - `PickEvent` (sku, quantity, timestamp)
  - `DamageReport` (sku, quantity, timestamp)
  - `SyncLog` (sku, operation, outcome, timestamp)
- Run initial Alembic migration to generate schema
- Verify database file is created and tables exist

**Testing:**
- Confirm all tables are created with correct columns and types
- Manually insert and query a test row in each table via a Python shell
- Confirm Alembic migration history is clean

---

## Phase 1: Seed Data

**Goals:** Database populated with realistic synthetic data.

**Tasks:**
- Write `db/seed.py` to populate:
  - 30 SKUs with names and bin locations
  - Randomized Physical counts (10--100 units)
  - Randomized Reserved counts (0--20% of Physical)
  - Derived Available counts (Physical minus Reserved)
- Run seed script and verify row counts
- Ensure no SKU has a negative Available count post-seed

**Testing:**
- Query all SKUs and confirm 30 rows exist in `InventoryState`
- Confirm no Available count is negative
- Confirm all SKUs have a corresponding bin location in `Product`

---

## Phase 2: Reconciliation Engine

**Goals:** Core business logic implemented with atomic state updates.

**Tasks:**
- Implement `engine/reconciliation.py` with the following methods:
  - `get_inventory(sku)` -- returns current Physical/Reserved/Available for a SKU
  - `get_all_inventory()` -- returns state for all SKUs
  - `process_pick(sku, quantity)` -- decrements Physical and Reserved atomically within a SQLite transaction; raises exception if Available would go negative
  - `process_damage(sku, quantity)` -- decrements Physical and Available atomically; raises exception if counts would go negative
- All write operations must be wrapped in SQLAlchemy transactions
- Engine must never return partial state on failure -- rollback on any exception

**Testing:**
- Pick event: confirm Physical and Reserved decrement correctly
- Pick event: confirm rejection when quantity exceeds Available count
- Damage report: confirm Physical and Available decrement correctly
- Damage report: confirm rejection when quantity exceeds Physical count
- Simulate a forced mid-transaction failure and confirm rollback leaves state unchanged
- Confirm no direct database writes exist outside the engine

---

## Phase 3: Adapter Layer

**Goals:** Abstract storefront interface defined; dummy Shopify adapter implemented.

**Tasks:**
- Define abstract base class in `adapters/base.py`:
  - `read_inventory(sku)` -- returns storefront-reported stock level for a SKU
  - `write_inventory(sku, quantity)` -- pushes Available count to storefront
- Implement `adapters/shopify_dummy.py`:
  - `read_inventory` returns a randomized or hardcoded stock level simulating a Shopify response
  - `write_inventory` logs the operation and returns a simulated success response
  - No external HTTP calls -- all responses are mocked in-process

**Testing:**
- Confirm `ShopifyDummyAdapter` is instantiatable via the base class type
- Call `read_inventory` on a known SKU and confirm a response is returned
- Call `write_inventory` on a known SKU and confirm a success response is returned
- Confirm no storefront-specific logic exists outside `adapters/`

---

## Phase 4: REST API

**Goals:** All planned endpoints implemented and returning correct responses.

**Tasks:**
- Initialize FastAPI app in `api/main.py`
- Implement routes:
  - `GET /inventory` -- returns all SKUs and state counts
  - `GET /inventory/{sku}` -- returns state for a single SKU; 404 if not found
  - `POST /events/pick` -- accepts `{sku, quantity}`; delegates to engine; returns updated state
  - `POST /events/damage` -- accepts `{sku, quantity}`; delegates to engine; returns updated state
  - `POST /sync` -- calls adapter `write_inventory` for all SKUs; logs results to `SyncLog`
  - `GET /sync/logs` -- returns all sync log entries
- Configure CORS to allow requests from the frontend
- Confirm FastAPI auto-docs available at `/docs`

**Testing:**
- Use `/docs` or curl to test each endpoint
- `GET /inventory` returns all 30 seeded SKUs
- `GET /inventory/{sku}` returns correct state for a valid SKU; 404 for an invalid SKU
- `POST /events/pick` with valid quantity returns updated state with decremented counts
- `POST /events/pick` with quantity exceeding Available returns a 400 error
- `POST /events/damage` with valid quantity returns updated state
- `POST /sync` populates `SyncLog` with one entry per SKU
- `GET /sync/logs` returns all log entries with timestamps and outcomes

---

## Phase 5: Frontend Dashboard

**Goals:** Single-page dashboard sufficient to demonstrate the full demo scenario.

**Tasks:**
- Build `frontend/index.html` with React loaded from CDN
- Implement the following views/interactions:
  - Inventory table showing all SKUs with Physical/Reserved/Available counts
  - Pick event form (SKU input, quantity input, submit button)
  - Damage report form (SKU input, quantity input, submit button)
  - Sync button triggering `POST /sync`
  - Sync log table showing recent sync entries
- All API calls use `fetch()` against the local FastAPI server
- Display error messages when the API returns a 400 or 404

**Testing:**
- Load dashboard in browser and confirm inventory table populates
- Submit a pick event and confirm the inventory table updates without a page refresh
- Submit a pick event exceeding Available count and confirm error is displayed
- Submit a damage report and confirm counts update
- Trigger sync and confirm sync log table populates
- Confirm all interactions work end-to-end against the live FastAPI server

---

## Phase 6: End-to-End Demo Validation

**Goals:** Full demo scenario verified end-to-end before submission.

**Demo scenario walkthrough:**
1. Load dashboard -- confirm all 30 SKUs visible with correct state
2. Select a SKU -- note current Physical/Reserved/Available counts
3. Submit a pick event -- confirm counts decrement correctly
4. Attempt an invalid pick (quantity exceeds Available) -- confirm rejection and error message
5. Submit a damage report -- confirm Physical and Available decrement
6. Trigger a sync -- confirm dummy adapter responds and sync log is populated
7. Review sync log -- confirm timestamps, SKUs, and outcomes are recorded

**Final checks:**
- No direct database writes occur outside the engine layer
- No storefront-specific logic exists outside the adapter layer
- All routes delegate to the engine; no business logic in route handlers
- All functions and classes are commented per the standards in CLAUDE.md
- FastAPI `/docs` accurately reflects all implemented endpoints
