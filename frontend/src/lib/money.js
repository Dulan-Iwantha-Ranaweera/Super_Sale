/**
 * Client-side mirrors of the backend money formulas.
 *
 * These exist so the POS ticket and the owner-input preview show exactly what
 * the server will persist. They must stay in step with `backend/app/money.py`;
 * the unit tests in `src/lib/money.test.js` pin the shared cases.
 */

export function round2(value) {
  const amount = Number(value)
  if (!Number.isFinite(amount)) return 0
  return Math.round((amount + Number.EPSILON) * 100) / 100
}

export function toNumber(value) {
  const parsed = Number.parseFloat(value)
  return Number.isFinite(parsed) ? parsed : 0
}

/** effective = selling * (1 - discount/100), then profit and margin from it. */
export function previewProfit(sellingPrice, buyingPrice, discountPercentage) {
  const selling = toNumber(sellingPrice)
  const buying = toNumber(buyingPrice)
  const discount = Math.min(100, Math.max(0, toNumber(discountPercentage)))
  const effective = round2(selling * (1 - discount / 100))
  const profit = round2(effective - buying)
  const margin = effective > 0 ? round2((profit / effective) * 100) : 0
  return { effective, profit, margin }
}

/**
 * Cart totals for the POS ticket.
 * `lines` are `{ product: { selling_price }, quantity, discount }`.
 */
export function computeTotals(lines, taxRate = 0) {
  let subtotal = 0
  let discountTotal = 0

  lines.forEach((line) => {
    const price = toNumber(line.product?.selling_price)
    const quantity = Math.max(0, Math.trunc(toNumber(line.quantity)))
    const discount = Math.min(100, Math.max(0, toNumber(line.discount)))

    const gross = round2(price * quantity)
    const net = round2(round2(price * (1 - discount / 100)) * quantity)

    subtotal = round2(subtotal + gross)
    discountTotal = round2(discountTotal + (gross - net))
  })

  const taxable = round2(subtotal - discountTotal)
  const tax = round2((taxable * Math.max(0, toNumber(taxRate))) / 100)
  return { subtotal, discountTotal, tax, grandTotal: round2(taxable + tax) }
}
