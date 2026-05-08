/**
 * Presentation layer -- SyncLogTable.jsx
 *
 * Fetches and renders a table of sync log entries from GET /sync/logs.
 *
 * Props:
 *   refreshToken {number} - increment this value to re-fetch
 *                           (called by App after a sync completes)
 */

import { useState, useEffect } from 'react'

export default function SyncLogTable({ refreshToken }) {
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)

    fetch('/sync/logs')
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then(data => {
        if (!cancelled) setLogs(data)
      })
      .catch(() => {
        if (!cancelled) setLogs([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [refreshToken])

  if (loading && logs.length === 0) {
    return <p className="state-message">Loading sync logs…</p>
  }

  if (!loading && logs.length === 0) {
    return (
      <p className="state-message">
        No sync logs yet. Trigger a sync to populate this table.
      </p>
    )
  }

  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Operation</th>
            <th>Details</th>
            <th>Outcome</th>
            <th>Timestamp</th>
          </tr>
        </thead>
        <tbody>
          {logs.map(log => (
            <tr key={log.id}>
              <td>{log.operation}</td>
              <td>{log.details || '—'}</td>
              <td>
                <span className={`badge badge-${log.outcome === 'success' ? 'success' : 'error'}`}>
                  {log.outcome}
                </span>
              </td>
              <td style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                {formatTimestamp(log.timestamp)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * Format an ISO timestamp string into a readable local datetime.
 *
 * @param {string|null} ts - ISO 8601 timestamp from the API
 * @returns {string} formatted date/time or '—' if null
 */
function formatTimestamp(ts) {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleString()
  } catch {
    return ts
  }
}
