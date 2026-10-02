import { describe, expect, it } from 'vitest'
import { computeTotals, previewProfit, round2, toNumber } from './money'

/**
 * These cases mirror `backend/tests/test_money.py` and `test_checkout.py`.
 * If one side changes, the other must change with it — the POS ticket and the
 * saved receipt are not allowed to disagree.
 */

describe('round2', () => {
  it('absorbs binary float drift', () => {
    expect(round2(0.1 + 0.2)).toBe(0.3)
    expect(round2(1.005)).toBe(1.01)
  })

  it('falls back to 0 for values that are not numbers', () => {
    expect(round2(undefined)).toBe(0)
    expect(round2(Number.NaN)).toBe(0)
    expect(round2('abc')).toBe(0)
  })
})

describe('toNumber', () => {
  it('parses numeric strings and defaults everything else to 0', () => {
    expect(toNumber('12.5')).toBe(12.5)
    expect(toNumber('')).toBe(0)
    expect(toNumber(null)).toBe(0)
  })
})

describe('previewProfit', () => {
  it('matches the backend formula', () => {
    // selling 15.00, cost 10.00, 10% off -> effective 13.50, profit 3.50, margin 25.93%
    expect(previewProfit(15, 10, 10)).toEqual({ effective: 13.5, profit: 3.5, margin: 25.93 })
  })

  it('reports a loss rather than hiding it', () => {
    expect(previewProfit(5, 20, 0)).toEqual({ effective: 5, profit: -15, margin: -300 })
  })

  it('returns a zero margin instead of dividing by zero at 100% off', () => {
    expect(previewProfit(15, 10, 100)).toEqual({ effective: 0, profit: -10, margin: 0 })
  })

  it('clamps the discount to the 0–100 range', () => {
    expect(previewProfit(10, 5, 150).effective).toBe(0)
    expect(previewProfit(10, 5, -20).effective).toBe(10)
  })

  it('treats blank inputs as zero while the form is being filled in', () => {
    expect(previewProfit('', '', '')).toEqual({ effective: 0, profit: 0, margin: 0 })
  })
})

describe('computeTotals', () => {
  const line = (selling, quantity, discount = 0) => ({
    product: { selling_price: selling },
    quantity,
    discount,
  })

  it('returns zeros for an empty cart', () => {
    expect(computeTotals([], 5)).toEqual({ subtotal: 0, discountTotal: 0, tax: 0, grandTotal: 0 })
  })

  it('reproduces the checkout test case exactly', () => {
    // 4 x 15.00 at 10% off with 5% tax -> the figures asserted server-side
    expect(computeTotals([line(15, 4, 10)], 5)).toEqual({
      subtotal: 60,
      discountTotal: 6,
      tax: 2.7,
      grandTotal: 56.7,
    })
  })

  it('applies tax after discounts, never before', () => {
    const { tax, grandTotal } = computeTotals([line(100, 1, 50)], 10)
    expect(tax).toBe(5) // 10% of 50, not of 100
    expect(grandTotal).toBe(55)
  })

  it('sums mixed lines and per-line discounts', () => {
    const totals = computeTotals([line(2.5, 3), line(1.99, 2, 25)], 0)
    expect(totals.subtotal).toBe(11.48)
    expect(totals.discountTotal).toBe(1)
    expect(totals.grandTotal).toBe(10.48)
  })

  it('stays exact across many small lines', () => {
    const lines = Array.from({ length: 10 }, () => line(0.1, 1))
    expect(computeTotals(lines, 0).grandTotal).toBe(1)
  })

  it('handles a zero tax rate and a missing one identically', () => {
    expect(computeTotals([line(10, 1)], 0)).toEqual(computeTotals([line(10, 1)]))
  })

  it('ignores negative quantities rather than crediting the basket', () => {
    expect(computeTotals([line(10, -5)], 0).grandTotal).toBe(0)
  })
})
