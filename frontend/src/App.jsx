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

export default function App() {
  const [inventory, setInventory] = useState([])
  const [syncLogs, setSyncLogs] = useState([])
  const [loadingInventory, setLoadingInventory] = useState(true)
  const [loadingLogs, setLoadingLogs] = useState(true)

  // SKU of the most recently-updated row, used to flash a highlight
  const [updatedSku, setUpdatedSku] = useState(null)

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

  const fetchSyncLogs = useCallback(async () => {
    setLoadingLogs(true)
    try {
      const res = await fetch('/sync/logs')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setSyncLogs(await res.json())
    } finally {
      setLoadingLogs(false)
    }
  }, [])

  // Load both tables on mount
  useEffect(() => {
    fetchInventory()
    fetchSyncLogs()
  }, [fetchInventory, fetchSyncLogs])

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
  }

  /**
   * After a sync completes, refresh both the inventory table (Available
   * counts are unchanged but good to confirm) and the sync log table.
   */
  function handleSyncComplete() {
    fetchInventory()
    fetchSyncLogs()
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

        {/* Event forms and sync panel -- one row of three cards */}
        <div className="panels-row">
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

        {/* Sync log table */}
        <div className="card">
          <div className="card-header">
            <h2>Sync Log</h2>
            <button
              className="btn-refresh"
              onClick={fetchSyncLogs}
              disabled={loadingLogs}
            >
              {loadingLogs ? 'Loading…' : '↻ Refresh'}
            </button>
          </div>
          <SyncLogTable logs={syncLogs} loading={loadingLogs} />
        </div>
      </main>
    </>
  )
}
