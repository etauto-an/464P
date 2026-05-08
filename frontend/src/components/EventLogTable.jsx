/**
 * Presentation layer -- EventLogTable.jsx
 *
 * Fetches and renders a unified table of order, pick, and damage events
 * from GET /events/logs. Both successful and rejected attempts are shown,
 * with a status badge and rejection reason where applicable.
 *
 * Props:
 *   refreshToken {number} - increment this value to re-fetch
 *                           (called by App after any event is submitted)
 */

import { useState, useEffect } from 'react'

const EVENT_TYPE_LABEL = {
  order:  'Order',
  pick:   'Pick',
  damage: 'Damage',
}

export default function EventLogTable({ refreshToken }) {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)

    fetch('/events/logs?limit=500')
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then(data => {
        if (!cancelled) setEvents(data)
      })
      .catch(() => {
        if (!cancelled) setEvents([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [refreshToken])

  if (loading && events.length === 0) {
    return <p className="state-message">Loading event log…</p>
  }

  if (!loading && events.length === 0) {
    return (
      <p className="state-message">
        No events yet. Submit an order, pick, or damage report to populate this table.
      </p>
    )
  }

  return (
    <div className="table-wrapper table-wrapper--scrollable">
      <table>
        <thead>
          <tr>
            <th>Type</th>
            <th>SKU</th>
            <th>Quantity</th>
            <th>Status</th>
            <th>Reason</th>
            <th>Timestamp</th>
          </tr>
        </thead>
        <tbody>
          {events.map((ev, i) => (
            <tr key={`${ev.event_type}-${ev.id}-${i}`}>
              <td>
                <span className={`badge badge-event-${ev.event_type}`}>
                  {EVENT_TYPE_LABEL[ev.event_type] ?? ev.event_type}
                </span>
              </td>
              <td className="sku-cell">{ev.sku}</td>
              <td>{ev.quantity}</td>
              <td>
                <span className={`badge badge-${ev.status === 'success' ? 'success' : 'error'}`}>
                  {ev.status}
                </span>
              </td>
              <td style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                {ev.rejection_reason || '—'}
              </td>
              <td style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                {formatTimestamp(ev.timestamp)}
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
