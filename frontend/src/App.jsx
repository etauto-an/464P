/**
 * Presentation layer -- App.jsx
 *
 * Root React component for the Multi-Channel Inventory Sync dashboard.
 * Manages top-level state and orchestrates the four main UI panels:
 *   - Inventory table (all SKUs with Physical / Reserved / Available counts)
 *   - Pick event form
 *   - Damage report form
 *   - Sync panel + sync log table
 *
 * All API calls use the Fetch API against the local FastAPI server
 * (proxied via Vite to http://localhost:8000).
 */

import { useState, useEffect, useCallback } from 'react'
import InventoryTable from './components/InventoryTable'
import EventForm from './components/EventForm'
import SyncPanel from './components/SyncPanel'
import SyncLogTable from './components/SyncLogTable'
import EventLogTable from './components/EventLogTable'

export default function App() {
  const [inventory, setInventory] = useState([])
  const [loadingInventory, setLoadingInventory] = useState(true)

  // SKU of the most recently-updated row, used to flash a highlight
  const [updatedSku, setUpdatedSku] = useState(null)

  const [syncRefreshToken, setSyncRefreshToken] = useState(0)
  const [eventRefreshToken, setEventRefreshToken] = useState(0)

  // -----------------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------------

  const fetchInventory = useCallback(async () => {
    setLoadingInventory(true)
    try {
      const res = await fetch('/inventory')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setInventory(await res.json())
    } finally {
      setLoadingInventory(false)
    }
  }, [])

  // Load inventory on mount (SyncLogTable fetches its own data)
  useEffect(() => {
    fetchInventory()
  }, [fetchInventory])

  // -----------------------------------------------------------------------
  // Event handlers -- called by child forms after a successful mutation
  // -----------------------------------------------------------------------

  /**
   * Merge one updated inventory row into the table without a full reload,
   * then flash its row and re-fetch in the background to stay in sync.
   *
   * @param {object} updatedRow - the InventoryResponse returned by the API
   */
  function handleInventoryUpdate(updatedRow) {
    setInventory(prev =>
      prev.map(item => item.sku === updatedRow.sku ? updatedRow : item)
    )
    // Flash the updated row
    setUpdatedSku(updatedRow.sku)
    setTimeout(() => setUpdatedSku(null), 1600)
    setEventRefreshToken(t => t + 1)
  }

  /**
   * After a sync completes, refresh the inventory table and signal
   * SyncLogTable to reset to page 1 and re-fetch.
   */
  function handleSyncComplete() {
    fetchInventory()
    setSyncRefreshToken(t => t + 1)
  }

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <>
      <header className="app-header">
        <div>
          <h1>Inventory Sync Dashboard</h1>
          <p className="subtitle">Multi-Channel Inventory Sync System &mdash; CPSC 464 Prototype</p>
        </div>
      </header>

      <main className="app-body">
        {/* Inventory table -- primary read view */}
        <div className="card">
          <div className="card-header">
            <h2>Inventory State</h2>
            <button
              className="btn-refresh"
              onClick={fetchInventory}
              disabled={loadingInventory}
            >
              {loadingInventory ? 'Loading…' : '↻ Refresh'}
            </button>
          </div>
          <InventoryTable
            inventory={inventory}
            loading={loadingInventory}
            updatedSku={updatedSku}
          />
        </div>

        {/* Event forms and sync panel -- 2x2 grid */}
        <div className="panels-row">
          <EventForm
            title="Incoming Order"
            endpoint="/events/order"
            submitLabel="Place Order"
            btnClass="btn-order"
            onSuccess={handleInventoryUpdate}
            description="Increments Reserved and decrements Available."
          />

          <EventForm
            title="Pick Event"
            endpoint="/events/pick"
            submitLabel="Submit Pick"
            btnClass="btn-primary"
            onSuccess={handleInventoryUpdate}
            description="Decrements Physical and Reserved."
          />

          <EventForm
            title="Damage Report"
            endpoint="/events/damage"
            submitLabel="Report Damage"
            btnClass="btn-danger"
            onSuccess={handleInventoryUpdate}
            description="Decrements Physical and Available."
          />

          <SyncPanel onSyncComplete={handleSyncComplete} />
        </div>

        {/* Event log table */}
        <div className="card">
          <div className="card-header">
            <h2>Event Log</h2>
            <button
              className="btn-refresh"
              onClick={() => setEventRefreshToken(t => t + 1)}
            >
              ↻ Refresh
            </button>
          </div>
          <EventLogTable refreshToken={eventRefreshToken} />
        </div>

        {/* Sync log table */}
        <div className="card">
          <div className="card-header">
            <h2>Sync Log</h2>
            <button
              className="btn-refresh"
              onClick={() => setSyncRefreshToken(t => t + 1)}
            >
              ↻ Refresh
            </button>
          </div>
          <SyncLogTable refreshToken={syncRefreshToken} />
        </div>
      </main>
    </>
  )
}
