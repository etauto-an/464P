# Multi-Channel Inventory Sync System — Technical Report

CPSC 464 — Erl-John Tauto-An

---

## Table of Contents

1. [Overview](#1-overview)
2. [Requirements](#2-requirements)
3. [Architecture](#3-architecture)
4. [Technologies](#4-technologies)
5. [Implementation](#5-implementation)
6. [Deployment](#6-deployment)
7. [Integration and Testing](#7-integration-and-testing)
8. [Conclusion](#8-conclusion)
9. [References](#9-references)
10. [Appendix](#10-appendix)

---

## 1. Overview

The Multi-Channel Inventory Sync System is a middleware synchronization engine designed to maintain consistency between a physical warehouse's inventory state and the digital inventory state of one or more e-commerce storefronts. The core problem it solves is inventory drift: a storefront's listed quantities can diverge from ground truth in the warehouse due to picks, damage events, and the latency of manual updates. Left uncorrected, this drift causes overselling, customer-facing stockouts, and fulfillment failures.

**Purpose:** The system acts as the authoritative source of truth for stock levels. It records every state-changing event (picks and damage reports), enforces business invariants on those events, and provides an explicit sync operation to propagate the correct Available count downstream to connected storefronts.

**Intended users:** Warehouse operations teams managing multi-channel retail, and developers integrating additional storefront platforms. In the prototype context, the intended audience is the CPSC 464 evaluators reviewing a layered middleware architecture.

The system exposes a REST API for all operations and a React web dashboard for interactive use. No mobile or desktop client is in scope; all operations are submitted through the API or dashboard.

---

## 2. Requirements

### 2.1 Functional Requirements

| ID | Requirement |
|---|---|
| FR-1 | The system must maintain three inventory counts per SKU: Physical, Reserved, and Available. |
| FR-2 | Physical is the actual unit count in the warehouse. Reserved is units committed to open orders. Available is Physical minus Reserved. |
| FR-3 | Pick events must atomically decrement both Physical and Reserved by the picked quantity. |
| FR-4 | Damage reports must atomically decrement both Physical and Available by the reported quantity. |
| FR-5 | Available must never go negative. The engine must reject any operation that would violate this invariant. |
| FR-6 | A sync operation must push the current Available count for all SKUs to the connected storefront adapter and record the outcome. |
| FR-7 | All sync outcomes must be persisted to a queryable sync log. |
| FR-8 | The system must expose REST endpoints for querying inventory, submitting events, triggering sync, and retrieving sync logs. |
| FR-9 | The database must be seeded with at minimum 20 SKUs with randomized counts and bin locations. |
| FR-10 | A web dashboard must support the full demo scenario: query → pick → damage → sync → logs. |

### 2.2 Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-1 | All state mutations must be atomic. A partial pick or partial damage write is not acceptable. |
| NFR-2 | SQLite is the single source of truth. Storefront state is treated as downstream and may be stale. |
| NFR-3 | The storefront adapter interface must be defined such that a real Shopify adapter can replace the dummy with zero changes to the engine or API layers. |
| NFR-4 | No route handler may write to the database directly. All writes must go through the reconciliation engine. |
| NFR-5 | The system must run without external service dependencies (no real API credentials, no external databases). |
| NFR-6 | The schema must be portable to PostgreSQL for Phase II without structural changes. |

### 2.3 Technical Specifications

- Python 3.x backend with FastAPI
- SQLite database (single file, local)
- SQLAlchemy ORM with Alembic for migrations
- React frontend served by Vite dev server
- All API communication over HTTP/JSON

---

## 3. Architecture

### 3.1 Architectural Style

The system uses a **Layered Architecture** with an explicit **Adapter Pattern** for storefront integrations. These two patterns were chosen together for the following reasons:

- **Layered Architecture** enforces a strict dependency rule: each layer may only depend on the layer directly below it. This makes the codebase easier to reason about, test in isolation, and extend.
- **Adapter Pattern** decouples the core engine from any specific storefront platform. The engine calls only the abstract `StorefrontAdapter` interface; it has no knowledge that a Shopify dummy is behind it. This means a real Shopify adapter, a Magento adapter, or a WooCommerce adapter can be slotted in without touching the engine.

### 3.2 Layer Descriptions

```
┌─────────────────────────────────────────────┐
│         Presentation Layer  (api/)          │
│   FastAPI route handlers, Pydantic schemas  │
│   React dashboard  (frontend/)              │
└───────────────────┬─────────────────────────┘
                    │ calls
┌───────────────────▼─────────────────────────┐
│       Business Logic Layer  (engine/)       │
│   ReconciliationEngine                      │
│   Enforces invariants, wraps transactions   │
└──────────┬────────────────────┬─────────────┘
           │ reads/writes       │ calls interface
┌──────────▼──────────┐  ┌──────▼──────────────┐
│  Persistence Layer  │  │   Adapter Layer      │
│  (db/)              │  │   (adapters/)        │
│  SQLAlchemy models  │  │   StorefrontAdapter  │
│  SQLite database    │  │   ShopifyDummyAdapter│
└─────────────────────┘  └─────────────────────┘
```

**Presentation Layer (`api/`, `frontend/`):** FastAPI route handlers receive HTTP requests, validate input via Pydantic models, delegate all logic to the engine, and format responses. The React dashboard communicates with this layer over the REST API. No route handler interacts with the database directly.

**Business Logic Layer (`engine/`):** The `ReconciliationEngine` class is the single point through which all inventory mutations flow. It enforces the Available ≥ 0 invariant, wraps all writes in SQLite transactions for atomicity, and records audit events (PickEvent, DamageReport) in the same transaction as the state update.

**Adapter Layer (`adapters/`):** The abstract `StorefrontAdapter` base class defines the contract (`read_inventory`, `write_inventory`). The `ShopifyDummyAdapter` implements this contract with in-process simulated responses. The engine and API layers reference only `StorefrontAdapter` — never the concrete class.

**Persistence Layer (`db/`):** SQLAlchemy ORM models map to SQLite tables. All database access uses the session factory from `db/database.py`. The seed script (`db/seed.py`) populates the database with 30 synthetic SKUs.

### 3.3 Data Model

```
products
─────────────────────────────────
sku          TEXT  PK
name         TEXT
bin_location TEXT

inventory_state
─────────────────────────────────
sku          TEXT  PK  FK→products.sku
physical     INT       actual units in warehouse
reserved     INT       units committed to open orders
available    INT       physical - reserved  (must be ≥ 0)

pick_events  (append-only audit log)
─────────────────────────────────
id           INT   PK  autoincrement
sku          TEXT
quantity     INT
timestamp    DATETIME  server default

damage_reports  (append-only audit log)
─────────────────────────────────
id           INT   PK  autoincrement
sku          TEXT
quantity     INT
timestamp    DATETIME  server default

sync_logs  (append-only audit log)
─────────────────────────────────
id           INT   PK  autoincrement
sku          TEXT
operation    TEXT      e.g. "write_inventory"
outcome      TEXT      "success" or "error"
timestamp    DATETIME  server default
```

### 3.4 Request Flow

A pick event follows this path through the layers:

```
HTTP POST /events/pick
        │
        ▼
[Presentation] pick_event() route handler
  validates EventRequest {sku, quantity}
        │
        ▼
[Business Logic] ReconciliationEngine.process_pick()
  checks quantity > 0
  checks quantity ≤ state.reserved
  decrements physical, reserved
  recalculates available
  inserts PickEvent audit record
  commits transaction atomically
        │
        ▼
[Persistence] SQLite commit
  inventory_state updated
  pick_events row inserted
        │
        ▼
[Presentation] returns InventoryResponse JSON
```

### 3.5 Architecture Rationale

This is a single-process monolith, not a microservices architecture. For a class prototype with a single SQLite file and no deployment infrastructure, a monolith is the correct choice. The layered architecture achieves the same separation-of-concerns benefits that microservices provide at scale, without the operational overhead of service discovery, inter-service networking, or distributed transactions. The adapter pattern specifically isolates the storefront integration boundary in a way that would make future extraction into a separate service straightforward.

---

## 4. Technologies

### Backend

**Python 3.x** — language of choice for the prototype. Broad library ecosystem, readable syntax appropriate for a class project.

**FastAPI** — modern Python web framework for building REST APIs. Chosen for its automatic OpenAPI/Swagger documentation generation, native Pydantic integration for request/response validation, and dependency injection system used for database session management.

**SQLAlchemy** — Python ORM providing an abstraction over the SQLite database. Manages the session lifecycle, ORM model definitions, and transaction boundaries. Using SQLAlchemy rather than raw SQL makes the schema portable to PostgreSQL for Phase II with minimal changes.

**Alembic** — database migration tool that works alongside SQLAlchemy. Included in dependencies for Phase II migration management; the prototype creates tables directly via `Base.metadata.create_all()`.

**Uvicorn** — ASGI server that runs the FastAPI application. Used in development mode with `--reload` for automatic restarts on code changes.

### Database

**SQLite** — embedded single-file relational database. Appropriate for a local prototype: zero configuration, no separate process, and the file can be version-controlled or reset trivially. The schema uses only standard SQL types to ensure PostgreSQL portability.

### Frontend

**React 19** — UI library for building the dashboard as a single-page application. Component-based structure maps cleanly onto the dashboard's four functional areas (inventory table, event forms, sync panel, sync log).

**Vite** — frontend build tool and development server. Provides fast hot module replacement during development. The Vite dev server runs on port 5173; the FastAPI backend explicitly allows this origin via CORS middleware.

### Adapter Pattern Implementation

**Python ABC (Abstract Base Classes)** — the `StorefrontAdapter` abstract class uses Python's `abc.ABC` and `@abstractmethod` decorators to enforce that all concrete adapters implement both `read_inventory` and `write_inventory`. This provides a compile-time-equivalent contract check at class instantiation.

---

## 5. Implementation

### 5.1 Inventory State Invariant

The central implementation challenge is enforcing `available = physical - reserved` and `available ≥ 0` at all times. This is handled entirely within the `ReconciliationEngine`:

- **Pick events:** quantity must not exceed `reserved`. Physical and Reserved are both decremented; Available is recalculated as `physical - reserved`. Mathematically, Available is unchanged by a pick, but it is recalculated and persisted explicitly so the database row always stores the correct value directly rather than requiring callers to infer it.

- **Damage reports:** quantity must not exceed `available`. Physical and Available are both decremented; Reserved is unchanged. This covers the case where damaged units were not previously reserved — they simply leave the sellable pool.

These checks happen inside the engine before the transaction is committed. If either check fails, a typed exception (`InsufficientInventoryError`) is raised and the transaction is never opened, leaving state unchanged.

### 5.2 Atomicity

SQLAlchemy's session commit is used as the transaction boundary. For both pick and damage operations, the inventory state update and the corresponding audit record (PickEvent or DamageReport) are added to the session and committed in a single `db.commit()` call. This guarantees that the audit log is never out of sync with the state: either both are written or neither is.

### 5.3 Adapter Isolation

A deliberate implementation decision was made to keep all Shopify-specific fields out of the engine and API layers. The `write_inventory()` response from the dummy adapter includes a `shopify_inventory_item_id` field that a real adapter would need. The sync route in `api/main.py` only inspects the `success` key and treats the rest of the response as opaque. This means adding platform-specific fields to a real adapter's response will not require changes anywhere outside the adapter.

### 5.4 Simulated Failures

The `ShopifyDummyAdapter` implements a 5% error rate (`ERROR_RATE = 0.05`) on `write_inventory()` calls to simulate transient storefront API failures (e.g., rate limiting). This ensures the sync log captures error outcomes during the demo, demonstrating that the system handles partial sync failures gracefully — the sync route counts and returns both successes and errors without aborting the whole run.

### 5.5 Challenges

**SQLite threading with FastAPI:** SQLite's default `check_same_thread=True` setting rejects database access from any thread other than the one that created the connection. FastAPI uses a thread pool for request handling, so this would cause errors on concurrent requests. This was resolved by passing `connect_args={"check_same_thread": False}` to the SQLAlchemy engine, which is the standard approach for SQLite in single-process ASGI applications.

**CORS for local development:** The frontend Vite dev server runs on port 5173 while the API runs on port 8000. Without CORS configuration, the browser blocks cross-origin requests. FastAPI's `CORSMiddleware` was added to explicitly allow origins `http://localhost:5173` and `http://127.0.0.1:5173`.

---

## 6. Deployment

The prototype is designed for local development deployment only. There is no containerization or cloud deployment in Phase I.

### Local Deployment Steps

1. Install Python dependencies: `pip install -r requirements.txt`
2. Seed the database: `python db/seed.py`
3. Start the API server: `uvicorn api.main:app --reload` (port 8000)
4. Install frontend dependencies: `cd frontend && npm install`
5. Start the frontend dev server: `npm run dev` (port 5173)

### Scalability and Reliability Considerations (Phase I)

Because SQLite is a file-based, single-writer database, horizontal scaling of the backend is not supported in this configuration. All requests are handled by a single Uvicorn process. This is acceptable for a prototype but is the primary scaling constraint to address in Phase II.

The reconciliation engine's use of SQLAlchemy transactions provides per-request reliability: a failed operation leaves the database in its pre-operation state. However, there is no retry logic for failed sync operations — they are logged as errors and require a manual re-sync.

### Phase II Deployment Path

- Replace SQLite with PostgreSQL to support multiple backend instances and concurrent writes.
- Containerize the backend and frontend with Docker; orchestrate with Docker Compose.
- Restrict CORS origins to the production frontend domain.
- Add authentication middleware to all API endpoints.

---

## 7. Integration and Testing

### 7.1 Integration Approach

The system uses constructor injection to wire layers together. The `ReconciliationEngine` receives a SQLAlchemy `Session` object at construction time (injected by FastAPI's `Depends(get_db)` dependency system). The `ShopifyDummyAdapter` is instantiated once at application startup as a module-level singleton in `api/main.py` and passed to the sync route.

This design makes the integration points explicit and testable: a test can construct a `ReconciliationEngine` with a test database session and verify its behavior without starting the HTTP server.

### 7.2 End-to-End Demo Scenario

The integration of all layers was validated by walking the full demo scenario through the React dashboard:

1. **Query inventory** — `GET /inventory` returns all 30 seeded SKUs with correct Physical/Reserved/Available counts.
2. **Submit pick event** — `POST /events/pick` with a valid SKU and quantity ≤ reserved; response reflects decremented Physical and Reserved.
3. **Reject invalid pick** — same endpoint with quantity > reserved returns HTTP 400, database unchanged.
4. **Submit damage report** — `POST /events/damage` with quantity ≤ available; response reflects decremented Physical and Available.
5. **Reject invalid damage** — quantity > available returns HTTP 400.
6. **Trigger sync** — `POST /sync` pushes all SKUs to the adapter; response includes success/error counts.
7. **View sync log** — `GET /sync/logs` returns entries with timestamps and outcomes including simulated errors.

### 7.3 Adapter Contract Verification

The abstract `StorefrontAdapter` interface uses Python ABCs, so instantiating any adapter that does not implement both `read_inventory` and `write_inventory` raises a `TypeError` at runtime. The dummy adapter was verified to satisfy the contract and return the expected response keys.

### 7.4 Automated Tests

The repository includes a test suite covering the reconciliation engine's business logic (valid picks, valid damage reports, over-pick rejection, over-damage rejection, and the Available invariant). Tests use an in-memory SQLite database to avoid filesystem side effects.

---

## 8. Conclusion

The Multi-Channel Inventory Sync System prototype successfully demonstrates a layered middleware architecture for warehouse-to-storefront inventory synchronization. The core invariant — Available must never go negative — is enforced at a single point in the codebase (the reconciliation engine), making it auditable and easy to reason about. The adapter pattern achieves genuine decoupling: the engine has no knowledge of Shopify or any other platform, and a real adapter can replace the dummy with no changes to any other layer.

**Lessons learned:**

- Defining the layer boundaries and the no-direct-DB-writes rule upfront made the codebase easier to reason about as features were added. The discipline of routing everything through the engine paid off when adding audit logging — it was a one-line addition inside the engine rather than a cross-cutting change.
- The adapter abstract base class caught interface mismatches at instantiation time rather than at runtime during a sync call, which shortened the feedback loop during development.
- SQLite's threading constraint is easy to overlook when first integrating with FastAPI. The `check_same_thread=False` fix is standard but not obvious.

**Future improvements (Phase II):**

- Replace the dummy adapter with a real Shopify REST/GraphQL adapter using OAuth and live credentials.
- Add webhook-based event processing so pick and damage events can be triggered by external order management systems.
- Migrate from SQLite to PostgreSQL and containerize with Docker Compose.
- Add authentication and authorization to all API endpoints.
- Implement retry logic for failed sync operations.
- Add a reservation management endpoint (`POST /events/reserve`) to close the order lifecycle.

---

## 9. References

- FastAPI documentation: https://fastapi.tiangolo.com
- SQLAlchemy documentation: https://docs.sqlalchemy.org
- Alembic documentation: https://alembic.sqlalchemy.org
- Vite documentation: https://vitejs.dev
- React documentation: https://react.dev
- Python `abc` module documentation: https://docs.python.org/3/library/abc.html
- Fowler, M. (2002). *Patterns of Enterprise Application Architecture.* Addison-Wesley. (Adapter pattern and Layered Architecture)

---

## 10. Appendix

### A. REST API Reference

| Method | Route | Request Body | Success Response |
|---|---|---|---|
| GET | `/inventory` | — | `200` list of InventoryResponse |
| GET | `/inventory/{sku}` | — | `200` InventoryResponse / `404` |
| POST | `/events/pick` | `{"sku": str, "quantity": int}` | `200` InventoryResponse / `400` / `404` |
| POST | `/events/damage` | `{"sku": str, "quantity": int}` | `200` InventoryResponse / `400` / `404` |
| POST | `/sync` | — | `200` `{"synced": int, "errors": int, "results": [...]}` |
| GET | `/sync/logs` | — | `200` list of SyncLogResponse |

**InventoryResponse schema:**
```json
{
  "sku": "SKU-1000",
  "name": "Wireless Keyboard",
  "bin_location": "A3-07",
  "physical": 72,
  "reserved": 8,
  "available": 64
}
```

### B. Database Tables

| Table | Purpose | Write pattern |
|---|---|---|
| `products` | SKU metadata (name, bin) | Seed only |
| `inventory_state` | Live Physical/Reserved/Available counts | Updated on every pick/damage event |
| `pick_events` | Immutable audit log of picks | Append-only |
| `damage_reports` | Immutable audit log of damage reports | Append-only |
| `sync_logs` | Outcome of each per-SKU sync push | Append-only |

### C. Project Directory Structure

```
464P/
├── api/
│   └── main.py              # FastAPI app, route handlers
├── engine/
│   └── reconciliation.py    # ReconciliationEngine, custom exceptions
├── adapters/
│   ├── base.py              # StorefrontAdapter abstract interface
│   └── shopify_dummy.py     # ShopifyDummyAdapter mock implementation
├── db/
│   ├── database.py          # SQLAlchemy engine and session factory
│   ├── models.py            # ORM models (5 tables)
│   └── seed.py              # Database seed script (30 SKUs)
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   └── components/
│   │       ├── InventoryTable.jsx
│   │       ├── EventForm.jsx
│   │       ├── SyncPanel.jsx
│   │       └── SyncLogTable.jsx
│   └── package.json
├── requirements.txt
├── README.md
└── CLAUDE.md
```

### D. Inventory State Invariants Summary

| Event | Physical | Reserved | Available |
|---|---|---|---|
| Pick (qty n) | −n | −n | unchanged (= P − R) |
| Damage (qty n) | −n | unchanged | −n |
| Constraint | — | — | must remain ≥ 0 |
