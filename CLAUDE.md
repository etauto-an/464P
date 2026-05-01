# CLAUDE.md -- Multi-Channel Inventory Sync System

## Project Overview

Middleware synchronization engine that maintains consistency between the physical inventory state of a warehouse and the digital inventory state of multiple e-commerce storefronts. This is a class project (CPSC 464) prototype demonstrating a layered architecture with an explicit adapter pattern.

The middleware is the sole focus. There is no mobile or desktop client -- all operations are submitted via the REST API or the web dashboard.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.x, FastAPI |
| Database | SQLite (local, single file) |
| ORM / Migrations | SQLAlchemy + Alembic |
| Frontend | HTML / CSS / React (CDN, no build toolchain) |
| Dummy API | Mock Shopify adapter (in-repo, no external dependencies) |

---

## Architecture

**Pattern:** Layered Architecture with Adapter Pattern for storefront integrations.

**Layers:**
- `api/` -- FastAPI route handlers (Presentation layer)
- `engine/` -- Reconciliation engine (Business Logic layer)
- `adapters/` -- Abstract storefront interface + dummy Shopify implementation (Adapter layer)
- `db/` -- SQLAlchemy models, schema, and seed scripts (Persistence layer)
- `frontend/` -- Single-page HTML/CSS/React dashboard

**Core architectural decisions:**
- All inventory state mutations go through the reconciliation engine. Routes never write to the database directly.
- The adapter layer is the only place that contains storefront-specific logic. The engine calls the abstract interface only.
- SQLite transactions are used to enforce atomicity on all state updates. A pick event must not partially update counts.
- SQLite is the single source of truth. External storefront state is treated as downstream.

---

## Inventory State Model

Each SKU maintains three distinct counts:

- **Physical** -- actual units present in the warehouse
- **Reserved** -- units committed to open orders but not yet picked
- **Available** -- units available for new orders (Physical minus Reserved)

Pick events decrement Physical and Reserved. Damage reports decrement Physical and Available. Available must never go negative -- the engine must reject any operation that would produce a negative Available count.

---

## Dummy API

The Shopify adapter is a mock implementation of the abstract storefront interface. It returns hardcoded or randomized responses simulating Shopify inventory read/write operations. No real API credentials are used. The mock is self-contained in `adapters/shopify_dummy.py`.

---

## Key Constraints

- Do not put storefront-specific logic in the engine layer.
- Do not write to the database from route handlers -- always go through the engine.
- Do not use async database writes unless SQLite concurrency implications are explicitly handled.
- SQLite is for the prototype only. The schema should be portable to PostgreSQL for Phase II.
- The abstract storefront interface must be defined such that a real Shopify adapter can replace the dummy without changes to the engine.

---

## REST API Endpoints (planned)

| Method | Route | Description |
|---|---|---|
| GET | `/inventory` | Query all SKUs and current state counts |
| GET | `/inventory/{sku}` | Query a single SKU |
| POST | `/events/pick` | Submit a pick event |
| POST | `/events/damage` | Submit a damage report |
| POST | `/sync` | Trigger a sync operation to the storefront adapter |
| GET | `/sync/logs` | Retrieve sync log entries |

---

## Seed Data

The database should be seeded with synthetic data:
- Minimum 20-30 SKUs with randomized Physical/Reserved/Available counts
- Each SKU mapped to at least one bin location
- Seed script located at `db/seed.py`

---

## Demo Scenario

The MVP is demoed via the web dashboard. A complete demo should walk through:

1. Query current inventory state for a SKU
2. Submit a pick event and observe state update
3. Submit a damage report and observe state update
4. Trigger a sync and observe the dummy adapter response
5. Retrieve the sync log

---

## Code Commenting Standards

All code must be thoroughly commented. This is a class project and comments serve both evaluation and knowledge transfer purposes.

**Modules and files** -- every file must open with a module-level docstring describing its role in the layered architecture and which layer it belongs to.

**Classes** -- every class must have a docstring describing its responsibility, the layer it belongs to, and any interfaces it implements or depends on.

**Functions and methods** -- every function must have a docstring covering:
- What the function does
- Parameters and types
- Return value and type
- Any exceptions raised
- Any architectural constraints being enforced (e.g., "validates Available count before committing transaction")

**Inline comments** -- use inline comments to explain non-obvious logic, especially:
- Transaction boundaries and why they are placed where they are
- Any place where a business rule (e.g., Available must not go negative) is enforced in code
- Any place where the adapter interface boundary is crossed

**Architectural intent comments** -- at key decision points, include a short comment explaining the architectural reasoning. Example:
```python
# Routed through the engine rather than writing directly to the DB.
# This enforces the layered architecture constraint -- the API layer
# has no direct dependency on the persistence layer.
result = engine.process_pick(sku, quantity)
```

**TODO comments** -- use `# TODO:` to flag anything deferred to Phase II (e.g., real Shopify adapter, webhook handling, authentication).

---

## Out of Scope (Prototype)

- Real Shopify API credentials or live API calls
- Webhook event processing
- Authentication or authorization on any endpoint
- CSV export fallback
- Deployment beyond local Docker Compose or `uvicorn` dev server
