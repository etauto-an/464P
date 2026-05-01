/**
 * Presentation layer -- SyncPanel.jsx
 *
 * Renders the Sync card: a single button that POSTs to /sync to push all
 * current Available counts to the storefront adapter, then displays a
 * summary of successes and errors from the sync run.
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
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  async function handleSync() {
    setSyncing(true)
    setResult(null)
    setError(null)

    try {
      const res = await fetch('/sync', { method: 'POST' })
      if (!res.ok) {
        const data = await res.json()
        setError(data.detail ?? `Sync failed (HTTP ${res.status}).`)
        return
      }
      const data = await res.json()
      setResult(data)
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
        style={{ marginBottom: result || error ? '0' : '0' }}
      >
        {syncing ? 'Syncing…' : '⟳ Trigger Sync'}
      </button>

      {error && <div className="alert alert-error">{error}</div>}

      {result && (
        <div className="sync-result">
          <div className="sync-stats">
            <div className="stat success">
              <span className="stat-value">{result.synced}</span>
              <span className="stat-label">Synced</span>
            </div>
            <div className="stat error">
              <span className="stat-value">{result.errors}</span>
              <span className="stat-label">Errors</span>
            </div>
            <div className="stat">
              <span className="stat-value">{result.synced + result.errors}</span>
              <span className="stat-label">Total SKUs</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
