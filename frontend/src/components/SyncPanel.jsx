/**
 * Presentation layer -- SyncPanel.jsx
 *
 * Renders the Sync card: a single button that POSTs to /sync to push all
 * current Available counts to the storefront adapter.
 *
 * After a successful sync the parent (App.jsx) refreshes both the inventory
 * table and the sync log table via the onSyncComplete callback.
 *
 * Props:
 *   onSyncComplete {function} - called after a successful sync to trigger
 *                               a data refresh in the parent
 */

import { useState } from 'react'

export default function SyncPanel({ onSyncComplete }) {
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState(null)

  async function handleSync() {
    setSyncing(true)
    setError(null)

    try {
      const res = await fetch('/sync', { method: 'POST' })
      if (!res.ok) {
        const data = await res.json()
        setError(data.detail ?? `Sync failed (HTTP ${res.status}).`)
        return
      }
      onSyncComplete()
    } catch {
      setError('Network error — is the backend running?')
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <h2>Storefront Sync</h2>
      </div>
      <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
        Push all Available counts to the Shopify adapter and record results in the sync log.
      </p>

      <button
        className="btn-secondary"
        onClick={handleSync}
        disabled={syncing}
      >
        {syncing ? 'Syncing…' : '⟳ Trigger Sync'}
      </button>

      {error && <div className="alert alert-error">{error}</div>}
    </div>
  )
}
