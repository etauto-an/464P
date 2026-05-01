/**
 * Presentation layer -- InventoryTable.jsx
 *
 * Renders the full inventory table showing Physical, Reserved, and Available
 * counts for every SKU. Highlights the most recently-updated row with a
 * brief green flash to give immediate visual feedback after a pick or damage event.
 *
 * Props:
 *   inventory  {Array}  - array of InventoryResponse objects from GET /inventory
 *   loading    {bool}   - true while the initial fetch is in flight
 *   updatedSku {string|null} - SKU to highlight; cleared by parent after 1.6s
 */

export default function InventoryTable({ inventory, loading, updatedSku }) {
  if (loading && inventory.length === 0) {
    return <p className="state-message">Loading inventory…</p>
  }

  if (!loading && inventory.length === 0) {
    return (
      <p className="state-message">
        No inventory data found. Run <code>python db/seed.py</code> to seed the database.
      </p>
    )
  }

  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>SKU</th>
            <th>Product Name</th>
            <th>Bin</th>
            <th style={{ textAlign: 'right' }}>Physical</th>
            <th style={{ textAlign: 'right' }}>Reserved</th>
            <th style={{ textAlign: 'right' }}>Available</th>
          </tr>
        </thead>
        <tbody>
          {inventory.map(item => (
            <tr
              key={item.sku}
              className={item.sku === updatedSku ? 'row-updated' : ''}
            >
              <td className="sku-cell">{item.sku}</td>
              <td>{item.name ?? '—'}</td>
              <td className="sku-cell">{item.bin_location ?? '—'}</td>
              <td className={`count-cell`}>{item.physical}</td>
              <td className={`count-cell`}>{item.reserved}</td>
              <td className={`count-cell ${availableClass(item.available)}`}>
                {item.available}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * Choose a CSS class for the available count based on its value.
 *
 * @param {number} n
 * @returns {string} CSS class name
 */
function availableClass(n) {
  if (n === 0) return 'danger'
  if (n <= 5)  return 'warning'
  return 'available'
}
