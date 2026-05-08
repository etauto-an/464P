/**
 * Presentation layer -- EventForm.jsx
 *
 * Reusable form for submitting an order, pick, or damage event.
 * The caller controls the API endpoint, button label, and CSS class,
 * allowing this component to serve all event types without duplication.
 *
 * On success the API returns the updated InventoryResponse for the affected
 * SKU. The parent (App.jsx) handles the state update via onSuccess().
 *
 * Props:
 *   title       {string}   - card heading
 *   endpoint    {string}   - API path, e.g. '/events/pick'
 *   submitLabel {string}   - button text
 *   btnClass    {string}   - CSS class for the submit button
 *   description {string}   - brief description shown below the heading
 *   onSuccess   {function} - called with the updated InventoryResponse on success
 */

import { useState } from 'react'

export default function EventForm({
  title,
  endpoint,
  submitLabel,
  btnClass,
  description,
  onSuccess,
}) {
  const [sku, setSku] = useState('')
  const [quantity, setQuantity] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [successMsg, setSuccessMsg] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setSuccessMsg(null)

    const qty = parseInt(quantity, 10)
    if (!sku.trim()) {
      setError('SKU is required.')
      return
    }
    if (!Number.isInteger(qty) || qty <= 0) {
      setError('Quantity must be a positive integer.')
      return
    }

    setSubmitting(true)
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sku: sku.trim().toUpperCase(), quantity: qty }),
      })

      const data = await res.json()

      if (!res.ok) {
        // The API returns {"detail": "..."} on 400/404
        setError(data.detail ?? `Request failed (HTTP ${res.status}).`)
        return
      }

      // Notify parent so it can update the inventory table row
      onSuccess(data)
      setSuccessMsg(
        `Done. ${data.sku}: physical=${data.physical}, reserved=${data.reserved}, available=${data.available}`
      )
      // Reset form fields
      setSku('')
      setQuantity('')
    } catch (err) {
      setError('Network error — is the backend running?')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <h2>{title}</h2>
      </div>
      <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
        {description}
      </p>

      <form onSubmit={handleSubmit} noValidate>
        <div className="form-group">
          <label htmlFor={`sku-${endpoint}`}>SKU</label>
          <input
            id={`sku-${endpoint}`}
            type="text"
            placeholder="e.g. SKU-1000"
            value={sku}
            onChange={e => setSku(e.target.value)}
          />
        </div>

        <div className="form-group">
          <label htmlFor={`qty-${endpoint}`}>Quantity</label>
          <input
            id={`qty-${endpoint}`}
            type="number"
            min="1"
            placeholder="1"
            value={quantity}
            onChange={e => setQuantity(e.target.value)}
          />
        </div>

        <button type="submit" className={btnClass} disabled={submitting}>
          {submitting ? 'Submitting…' : submitLabel}
        </button>
      </form>

      {error && <div className="alert alert-error">{error}</div>}
      {successMsg && <div className="alert alert-success">{successMsg}</div>}
    </div>
  )
}
