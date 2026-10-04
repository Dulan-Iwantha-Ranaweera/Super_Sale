import { describe, expect, it } from 'vitest'
import {
  currencySymbol,
  formatDate,
  formatMoney,
  formatNumber,
  formatPercent,
  productEmoji,
} from './format'

describe('formatMoney', () => {
  it('always shows two decimals', () => {
    expect(formatMoney(5, 'USD')).toBe('$5.00')
    expect(formatMoney(1234.5, 'USD')).toBe('$1,234.50')
  })

  it('puts the minus sign before the symbol', () => {
    expect(formatMoney(-12.5, 'USD')).toBe('-$12.50')
  })

  it('honours the store currency', () => {
    expect(formatMoney(10, 'EUR')).toBe('€10.00')
    expect(formatMoney(10, 'LKR')).toBe('Rs 10.00')
  })

  it('falls back to the code for an unknown currency', () => {
    expect(formatMoney(10, 'XYZ')).toBe('XYZ 10.00')
    expect(currencySymbol('XYZ')).toBe('XYZ ')
  })

  it('defaults to rupees, the store currency for Sri Lanka', () => {
    expect(formatMoney(2500)).toBe('Rs 2,500.00')
    expect(currencySymbol()).toBe('Rs ')
  })

  it('renders missing values as zero rather than NaN', () => {
    expect(formatMoney(undefined, 'LKR')).toBe('Rs 0.00')
    expect(formatMoney(null, 'LKR')).toBe('Rs 0.00')
  })
})

describe('formatPercent', () => {
  it('formats with two decimals by default', () => {
    expect(formatPercent(25.926)).toBe('25.93%')
    expect(formatPercent(0)).toBe('0.00%')
  })

  it('adds a plus sign only when asked and only when positive', () => {
    expect(formatPercent(3.5, { withSign: true })).toBe('+3.50%')
    expect(formatPercent(-3.5, { withSign: true })).toBe('-3.50%')
  })

  it('supports whole-number display for table cells', () => {
    expect(formatPercent(10, { digits: 0 })).toBe('10%')
  })
})

describe('formatNumber', () => {
  it('groups thousands and tolerates bad input', () => {
    expect(formatNumber(1500)).toBe((1500).toLocaleString())
    expect(formatNumber(undefined)).toBe('0')
  })
})

describe('formatDate', () => {
  it('renders an em dash for missing or unparseable dates', () => {
    expect(formatDate(null)).toBe('—')
    expect(formatDate('not a date')).toBe('—')
  })

  it('formats a real timestamp', () => {
    expect(formatDate('2026-10-02T10:00:00Z')).toContain('2026')
  })
})

describe('productEmoji', () => {
  it('uses the stored emoji key when present', () => {
    expect(productEmoji({ image_url: 'emoji:rice' })).toBe('\u{1F35A}')
  })

  it('falls back to the category, then to a generic box', () => {
    expect(productEmoji({ category: 'Dairy' })).toBe('\u{1F95B}')
    expect(productEmoji({ category: 'Unmapped' })).toBe('\u{1F4E6}')
    expect(productEmoji(null)).toBe('\u{1F4E6}')
  })
})
