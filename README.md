# Multi-Channel Inventory Sync System

CPSC 464 prototype — middleware synchronization engine that maintains consistency between a warehouse's physical inventory and multiple e-commerce storefronts.

---

## Prerequisites

- Python 3.x
- Node.js 18+ and npm

---

## Setup

### 1. Install Python dependencies

From the project root:

```bash
pip install -r requirements.txt
```

### 2. Seed the database

```bash
python db/seed.py
```

This creates `inventory.db` and populates it with 30 synthetic SKUs.

### 3. Start the backend

```bash
uvicorn api.main:app --reload
```

The API will be available at `http://localhost:8000`.  
Interactive API docs (Swagger UI): `http://localhost:8000/docs`

### 4. Start the frontend

In a separate terminal, from the `frontend/` directory:

```bash
cd frontend
npm install
npm run dev
```

The dashboard will be available at `http://localhost:5173`.

---

## API Endpoints

| Method | Route | Description |
|---|---|---|
| GET | `/inventory` | List all SKUs and current counts |
| GET | `/inventory/{sku}` | Get a single SKU |
| POST | `/events/pick` | Submit a pick event |
| POST | `/events/damage` | Submit a damage report |
| POST | `/sync` | Sync all SKUs to the storefront adapter |
| GET | `/sync/logs` | Retrieve sync log entries |

**Pick / damage request body:**
```json
{ "sku": "SKU-1000", "quantity": 5 }
```

---

## Project Structure

```
├── api/          # FastAPI route handlers (Presentation layer)
├── engine/       # Reconciliation engine (Business Logic layer)
├── adapters/     # Abstract storefront interface + dummy Shopify adapter
├── db/           # SQLAlchemy models, database config, and seed script
└── frontend/     # React dashboard (Vite)
```

---

## Re-seeding

To reset the database to fresh synthetic data:

```bash
python db/seed.py
```

This clears and re-inserts all 30 SKUs. Sync logs are not cleared.
