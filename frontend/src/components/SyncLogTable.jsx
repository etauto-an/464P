/**
 * Presentation layer -- SyncLogTable.jsx
 *
 * Renders a paginated table of sync log entries returned by GET /sync/logs.
 * Each row shows the SKU, operation, outcome badge, and timestamp.
 * Most recent entries are listed first (the API returns them in that order).
 *
 * Props:
 *   logs    {Array} - array of SyncLogResponse objects
 *   loading {bool}  - true while the initial fetch is in flight
 */

// How many log rows to show before pagination kicks in
const PAGE_SIZE = 50

export default function SyncLogTable({ logs, loading }) {
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

  // Show only the most recent PAGE_SIZE entries to keep the table manageable
  const visible = logs.slice(0, PAGE_SIZE)

  return (
    <>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>SKU</th>
              <th>Operation</th>
              <th>Outcome</th>
              <th>Timestamp</th>
            </tr>
          </thead>
          <tbody>
            {visible.map(log => (
              <tr key={log.id}>
                <td className="sku-cell">{log.id}</td>
                <td className="sku-cell">{log.sku}</td>
                <td>{log.operation}</td>
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
      {logs.length > PAGE_SIZE && (
        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
          Showing {PAGE_SIZE} of {logs.length} entries.
        </p>
      )}
    </>
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
