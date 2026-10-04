import { AlertCircle, ArrowDown, ArrowUp, ChevronsUpDown, Inbox, Loader2, X } from 'lucide-react'
import { useEffect } from 'react'

export function Card({ className = '', children, ...rest }) {
  // Tailwind utilities of equal specificity resolve by stylesheet order, not by
  // the order they appear here, so a caller passing `bg-slate-700` would lose to
  // the default. Drop the default whenever the caller supplies its own.
  const hasCustomBackground = /(^|\s)bg-/.test(className)
  return (
    <div
      className={`rounded-xl border border-edge shadow-card ${
        hasCustomBackground ? '' : 'bg-surface'
      } ${className}`}
      {...rest}
    >
      {children}
    </div>
  )
}

export function CardHeader({ title, subtitle, action, className = '' }) {
  return (
    <div className={`flex items-start justify-between gap-4 px-5 pt-5 ${className}`}>
      <div>
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-sm text-ink-muted">{subtitle}</p> : null}
      </div>
      {action}
    </div>
  )
}

const BUTTON_VARIANTS = {
  primary: 'bg-brand-500 text-white hover:bg-brand-600 focus-visible:ring-brand-500/40',
  secondary:
    'bg-surface text-ink border border-edge-strong hover:bg-surface-muted focus-visible:ring-slate-400/40',
  success: 'bg-emerald-600 text-white hover:bg-emerald-700 focus-visible:ring-emerald-500/40',
  danger: 'bg-rose-600 text-white hover:bg-rose-700 focus-visible:ring-rose-500/40',
  ghost: 'bg-transparent text-ink-muted hover:bg-surface-muted focus-visible:ring-slate-400/40',
}

export function Button({
  variant = 'primary',
  size = 'md',
  className = '',
  loading = false,
  disabled,
  children,
  ...rest
}) {
  const sizing = size === 'sm' ? 'px-3 py-1.5 text-sm' : size === 'lg' ? 'px-5 py-3 text-base' : 'px-4 py-2 text-sm'
  return (
    <button
      type="button"
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium transition
        focus:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-60
        ${BUTTON_VARIANTS[variant]} ${sizing} ${className}`}
      {...rest}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
      {children}
    </button>
  )
}

// Status colours keep their meaning in both themes: a soft tint in light, a
// translucent wash of the same hue in dark, where a pale 50-shade would glare.
const BADGE_TONES = {
  green:
    'bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-400/30',
  amber:
    'bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-400/30',
  red: 'bg-rose-50 text-rose-700 ring-rose-600/20 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-400/30',
  slate: 'bg-surface-muted text-ink-muted ring-edge-strong',
  blue: 'bg-brand-50 text-brand-700 ring-brand-600/20 dark:bg-brand-500/15 dark:text-brand-100 dark:ring-brand-400/30',
}

export function Badge({ tone = 'slate', children, className = '' }) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-1 text-xs font-medium ring-1 ring-inset
        ${BADGE_TONES[tone]} ${className}`}
    >
      {children}
    </span>
  )
}

const STATUS_TONES = {
  IN_STOCK: { tone: 'green', label: 'In Stock' },
  LOW_STOCK: { tone: 'amber', label: 'Low Stock' },
  OUT_OF_STOCK: { tone: 'red', label: 'Out of Stock' },
}

export function StockBadge({ status }) {
  const config = STATUS_TONES[status] ?? STATUS_TONES.IN_STOCK
  return <Badge tone={config.tone}>{config.label}</Badge>
}

export function Field({ label, hint, error, children, className = '' }) {
  return (
    <label className={`block ${className}`}>
      <span className="field-label">{label}</span>
      {children}
      {error ? (
        <span className="mt-1 block text-xs text-rose-600">{error}</span>
      ) : hint ? (
        <span className="mt-1 block text-xs text-ink-faint">{hint}</span>
      ) : null}
    </label>
  )
}

export function Spinner({ label = 'Loading…', className = '' }) {
  return (
    <div className={`flex items-center justify-center gap-2 py-10 text-sm text-ink-muted ${className}`}>
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      {label}
    </div>
  )
}

export function ErrorState({ error, onRetry, className = '' }) {
  return (
    <div className={`flex flex-col items-center gap-3 px-6 py-10 text-center ${className}`}>
      <AlertCircle className="h-8 w-8 text-rose-500" aria-hidden="true" />
      <p className="text-sm font-medium text-ink">Something went wrong</p>
      <p className="max-w-md text-sm text-ink-muted">{error?.message || 'Unexpected error'}</p>
      {onRetry ? (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  )
}

export function EmptyState({ title, description, icon: Icon = Inbox, action, className = '' }) {
  return (
    <div className={`flex flex-col items-center gap-2 px-6 py-12 text-center ${className}`}>
      <Icon className="h-8 w-8 text-ink-faint" aria-hidden="true" />
      <p className="text-sm font-medium text-ink">{title}</p>
      {description ? <p className="max-w-md text-sm text-ink-muted">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  )
}

export function SortableHeader({ field, label, sortBy, sortDir, onSort, align = 'left' }) {
  const active = sortBy === field
  const Icon = !active ? ChevronsUpDown : sortDir === 'asc' ? ArrowUp : ArrowDown
  return (
    <th className={`table-header ${align === 'right' ? 'text-right' : ''}`} scope="col">
      <button
        type="button"
        onClick={() => onSort(field)}
        className={`inline-flex items-center gap-1 uppercase tracking-wide transition hover:text-ink
          ${active ? 'text-ink' : ''}`}
      >
        {label}
        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </th>
  )
}

export function Modal({ open, title, onClose, children, footer, width = 'max-w-lg' }) {
  useEffect(() => {
    if (!open) return undefined
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose?.()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-slate-900/40 dark:bg-black/60"
        onClick={onClose}
        role="presentation"
      />
      <div className={`relative w-full ${width} rounded-xl border border-edge bg-surface shadow-xl`} role="dialog" aria-modal="true">
        <div className="flex items-center justify-between border-b border-edge px-5 py-4">
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-ink-faint transition hover:bg-surface-muted hover:text-ink-muted"
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto scroll-slim px-5 py-4">{children}</div>
        {footer ? (
          <div className="flex justify-end gap-2 border-t border-edge px-5 py-4">{footer}</div>
        ) : null}
      </div>
    </div>
  )
}

export function Pagination({ page, pageSize, total, onPageChange }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (total === 0) return null
  const first = (page - 1) * pageSize + 1
  const last = Math.min(total, page * pageSize)
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-edge px-5 py-3">
      <p className="text-sm text-ink-muted">
        Showing <span className="font-medium text-ink">{first}</span>–
        <span className="font-medium text-ink">{last}</span> of{' '}
        <span className="font-medium text-ink">{total}</span>
      </p>
      <div className="flex items-center gap-2">
        <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          Previous
        </Button>
        <span className="text-sm text-ink-muted">
          Page {page} of {pages}
        </span>
        <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => onPageChange(page + 1)}>
          Next
        </Button>
      </div>
    </div>
  )
}

export function Toast({ toast, onDismiss }) {
  useEffect(() => {
    if (!toast) return undefined
    const timer = setTimeout(() => onDismiss(), toast.tone === 'error' ? 6000 : 3500)
    return () => clearTimeout(timer)
  }, [toast, onDismiss])

  if (!toast) return null
  const tone =
    toast.tone === 'error'
      ? 'border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-500/30 dark:bg-rose-500/15 dark:text-rose-200'
      : 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/15 dark:text-emerald-200'
  return (
    <div className="fixed bottom-6 right-6 z-50 max-w-sm" role="status" aria-live="polite">
      <div className={`flex items-start gap-3 rounded-lg border px-4 py-3 shadow-lg ${tone}`}>
        <p className="text-sm font-medium">{toast.message}</p>
        <button type="button" onClick={onDismiss} className="ml-auto opacity-60 hover:opacity-100">
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
