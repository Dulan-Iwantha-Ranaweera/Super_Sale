const CURRENCY_SYMBOLS = {
  EUR: '€',
  GBP: '£',
  LKR: 'Rs ',
  USD: '$',
  INR: '₹',
  AUD: 'A$',
  CAD: 'C$',
  JPY: '¥',
}

export function currencySymbol(currency = 'LKR') {
  return CURRENCY_SYMBOLS[currency] ?? `${currency} `
}

export function formatMoney(value, currency = 'LKR') {
  const amount = Number.isFinite(Number(value)) ? Number(value) : 0
  const sign = amount < 0 ? '-' : ''
  const body = Math.abs(amount).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return `${sign}${currencySymbol(currency)}${body}`
}

export function formatPercent(value, { withSign = false, digits = 2 } = {}) {
  const amount = Number.isFinite(Number(value)) ? Number(value) : 0
  const sign = withSign && amount > 0 ? '+' : ''
  return `${sign}${amount.toFixed(digits)}%`
}

export function formatNumber(value) {
  const amount = Number.isFinite(Number(value)) ? Number(value) : 0
  return amount.toLocaleString()
}

export function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export function formatDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Emoji stand-ins for product photography, keyed by the seeded `emoji:*` value. */
const PRODUCT_EMOJI = {
  milk: '\u{1F95B}',
  cheese: '\u{1F9C0}',
  rice: '\u{1F35A}',
  soap: '\u{1F9F4}',
  flour: '\u{1F33E}',
  oil: '\u{1F9F4}',
  sugar: '\u{1F36C}',
  tea: '\u{1F375}',
  coffee: '☕',
  meat: '\u{1F357}',
  eggs: '\u{1F95A}',
  fruit: '\u{1F34C}',
  veg: '\u{1F345}',
  snack: '\u{1F36B}',
  drink: '\u{1F964}',
  care: '\u{1F9F4}',
  home: '\u{1F9FB}',
}

const CATEGORY_EMOJI = {
  Dairy: '\u{1F95B}',
  Rice: '\u{1F35A}',
  Detergent: '\u{1F9F4}',
  Food: '\u{1F35E}',
  Fresh: '\u{1F957}',
  Snacks: '\u{1F36B}',
  Beverages: '\u{1F964}',
  'Personal Care': '\u{1F9F4}',
  Household: '\u{1F9FB}',
}

export function productEmoji(product) {
  const image = product?.image_url || ''
  if (image.startsWith('emoji:')) {
    const key = image.slice('emoji:'.length)
    if (PRODUCT_EMOJI[key]) return PRODUCT_EMOJI[key]
  }
  return CATEGORY_EMOJI[product?.category] || '\u{1F4E6}'
}
