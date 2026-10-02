import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Banknote, CreditCard, Printer, Receipt, Search, Split, Undo2 } from 'lucide-react'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  Modal,
  Pagination,
  Spinner,
} from '../components/ui'
import ReturnDialog from '../components/ReturnDialog'
import { useAuth } from '../context/AuthContext'
import { useStoreSettings } from '../hooks/useStoreSettings'
import { api, buildQuery } from '../lib/api'
import { formatDateTime, formatMoney, formatNumber, formatPercent } from '../lib/format'

const PAGE_SIZE = 15

const RANGE_PRESETS = [
  { value: 1, label: 'Today' },
  { value: 7, label: 'Last 7 days' },
  { value: 30, label: 'Last 30 days' },
  { value: 90, label: 'Last 90 days' },
  { value: 365, label: 'Last 12 months' },
]

const PAYMENT_ICONS = { CASH: Banknote, CARD: CreditCard, SPLIT: Split }

function PaymentBadge({ method }) {
  const Icon = PAYMENT_ICONS[method] ?? Banknote
  const tone = method === 'CASH' ? 'green' : method === 'CARD' ? 'blue' : 'amber'
  return (
    <Badge tone={tone}>
      <Icon className="mr-1 inline h-3.5 w-3.5" aria-hidden="true" />
      {method}
    </Badge>
  )
}

export default function SalesHistory() {
  const { isOwner } = useAuth()
  const { data: store } = useStoreSettings()
  const currency = store?.currency ?? 'LKR'

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [days, setDays] = useState(30)
  const [paymentMethod, setPaymentMethod] = useState('ALL')
  const [ledgerType, setLedgerType] = useState('ALL')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState(null)
  const [refunding, setRefunding] = useState(null)

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    setPage(1)
  }, [debouncedSearch, days, paymentMethod, ledgerType, start, end])

  const usingCustomRange = Boolean(start && end)
  const filters = useMemo(
    () => ({
      search: debouncedSearch || undefined,
      payment_method: paymentMethod === 'ALL' ? undefined : paymentMethod,
      ledger_type: ledgerType === 'ALL' ? undefined : ledgerType,
      ...(usingCustomRange ? { start, end } : { days }),
    }),
    [debouncedSearch, paymentMethod, ledgerType, usingCustomRange, start, end, days],
  )

  const listQuery = useQuery({
    queryKey: ['sales', 'history', filters, page],
    queryFn: () => api(`/api/sales${buildQuery({ ...filters, page, page_size: PAGE_SIZE })}`),
    placeholderData: (previous) => previous,
  })

  const statsQuery = useQuery({
    queryKey: ['sales', 'stats', filters],
    queryFn: () => api(`/api/sales/stats${buildQuery(filters)}`),
  })

  const data = listQuery.data
  const sales = data?.items ?? []
  const stats = statsQuery.data

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-5 xl:grid-cols-4">
        <Card className="p-5">
          <p className="text-sm font-medium text-ink-muted">Net Revenue</p>
          <p className="mt-2 text-2xl font-semibold text-ink">
            {stats ? formatMoney(stats.net_revenue, currency) : '—'}
          </p>
          <p className="mt-1 text-sm text-ink-muted">
            {stats
              ? stats.refunds > 0
                ? `${formatMoney(stats.revenue, currency)} less ${formatMoney(stats.refunds, currency)} refunded`
                : 'No refunds in this period'
              : ''}
          </p>
        </Card>
        <Card className="p-5">
          <p className="text-sm font-medium text-ink-muted">Transactions</p>
          <p className="mt-2 text-2xl font-semibold text-ink">
            {stats ? formatNumber(stats.transactions) : '—'}
          </p>
          <p className="mt-1 text-sm text-ink-muted">
            {stats
              ? `${formatNumber(stats.items_sold)} units${stats.returns ? ` · ${formatNumber(stats.returns)} returns` : ''}`
              : ''}
          </p>
        </Card>
        <Card className="p-5">
          <p className="text-sm font-medium text-ink-muted">Average Basket</p>
          <p className="mt-2 text-2xl font-semibold text-ink">
            {stats ? formatMoney(stats.average_basket, currency) : '—'}
          </p>
        </Card>
        {isOwner ? (
          <Card className="p-5">
            <p className="text-sm font-medium text-ink-muted">Profit</p>
            <p
              className={`mt-2 text-2xl font-semibold ${
                (stats?.profit ?? 0) >= 0 ? 'text-emerald-600' : 'text-rose-600'
              }`}
            >
              {stats ? formatMoney(stats.profit, currency) : '—'}
            </p>
            <p className="mt-1 text-sm text-ink-muted">
              {stats && stats.revenue > 0 ? `Margin ${formatPercent((stats.profit / stats.revenue) * 100)}` : ''}
            </p>
          </Card>
        ) : (
          <Card className="p-5">
            <p className="text-sm font-medium text-ink-muted">Units Sold</p>
            <p className="mt-2 text-2xl font-semibold text-ink">
              {stats ? formatNumber(stats.items_sold) : '—'}
            </p>
          </Card>
        )}
      </div>

      <Card>
        <CardHeader title="Sales History" subtitle="Every completed receipt, newest first" />

        <div className="flex flex-wrap items-end gap-3 px-5 pb-4 pt-4">
          <label className="flex flex-col text-sm">
            <span className="field-label">Range</span>
            <select
              className="field-input w-auto min-w-[150px]"
              value={usingCustomRange ? 'custom' : String(days)}
              onChange={(event) => {
                if (event.target.value === 'custom') return
                setStart('')
                setEnd('')
                setDays(Number(event.target.value))
              }}
            >
              {RANGE_PRESETS.map((preset) => (
                <option key={preset.value} value={String(preset.value)}>
                  {preset.label}
                </option>
              ))}
              {usingCustomRange ? <option value="custom">Custom range</option> : null}
            </select>
          </label>

          <label className="flex flex-col text-sm">
            <span className="field-label">From</span>
            <input
              type="date"
              className="field-input w-auto"
              value={start}
              onChange={(event) => setStart(event.target.value)}
            />
          </label>
          <label className="flex flex-col text-sm">
            <span className="field-label">To</span>
            <input
              type="date"
              className="field-input w-auto"
              value={end}
              onChange={(event) => setEnd(event.target.value)}
            />
          </label>

          <label className="flex flex-col text-sm">
            <span className="field-label">Type</span>
            <select
              className="field-input w-auto min-w-[130px]"
              value={ledgerType}
              onChange={(event) => setLedgerType(event.target.value)}
            >
              <option value="ALL">Sales &amp; returns</option>
              <option value="SALE">Sales only</option>
              <option value="RETURN">Returns only</option>
            </select>
          </label>

          <label className="flex flex-col text-sm">
            <span className="field-label">Payment</span>
            <select
              className="field-input w-auto min-w-[130px]"
              value={paymentMethod}
              onChange={(event) => setPaymentMethod(event.target.value)}
            >
              <option value="ALL">All methods</option>
              <option value="CASH">Cash</option>
              <option value="CARD">Card</option>
              <option value="SPLIT">Split</option>
            </select>
          </label>

          <div className="relative ml-auto min-w-[240px]">
            <span className="field-label">Search</span>
            <Search className="pointer-events-none absolute bottom-2.5 left-3 h-4 w-4 text-ink-faint" />
            <input
              className="field-input pl-9"
              placeholder="Receipt no, customer or item…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              aria-label="Search sales"
            />
          </div>
        </div>

        <div className="overflow-x-auto scroll-slim">
          {listQuery.isLoading ? (
            <Spinner label="Loading sales…" />
          ) : listQuery.isError ? (
            <ErrorState error={listQuery.error} onRetry={listQuery.refetch} />
          ) : sales.length === 0 ? (
            <EmptyState
              icon={Receipt}
              title="No sales match these filters"
              description="Try a wider date range or clear the search box."
            />
          ) : (
            <table className="min-w-full">
              <thead className="border-y border-edge bg-surface-muted">
                <tr>
                  <th className="table-header">Receipt</th>
                  <th className="table-header">Date &amp; Time</th>
                  <th className="table-header">Customer</th>
                  <th className="table-header">Cashier</th>
                  <th className="table-header text-right">Items</th>
                  <th className="table-header">Payment</th>
                  <th className="table-header text-right">Total</th>
                  {isOwner ? <th className="table-header text-right">Profit</th> : null}
                  <th className="table-header text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge">
                {sales.map((sale) => {
                  const units = sale.items.reduce((sum, item) => sum + item.quantity, 0)
                  const isReturn = sale.type === 'RETURN'
                  return (
                    <tr key={sale.id} className={isReturn ? 'bg-rose-50/40 hover:bg-rose-50 dark:bg-rose-500/5 dark:hover:bg-rose-500/10' : 'hover:bg-surface-muted'}>
                      <td className="table-cell font-mono text-xs font-medium">
                        <span className={isReturn ? 'text-rose-700' : 'text-ink'}>
                          {sale.receipt_number}
                        </span>
                        {isReturn ? (
                          <span className="ml-2 inline-flex">
                            <Badge tone="red">Refund</Badge>
                          </span>
                        ) : null}
                        {isReturn && sale.original_receipt_number ? (
                          <span className="mt-0.5 block text-[11px] font-normal text-ink-muted">
                            against {sale.original_receipt_number}
                          </span>
                        ) : null}
                      </td>
                      <td className="table-cell text-ink-muted">{formatDateTime(sale.timestamp)}</td>
                      <td className="table-cell">{sale.customer_name || <span className="text-ink-faint">Walk-in</span>}</td>
                      <td className="table-cell text-ink-muted">{sale.cashier_id}</td>
                      <td className="table-cell text-right">{formatNumber(units)}</td>
                      <td className="table-cell">
                        <PaymentBadge method={sale.payment_method} />
                      </td>
                      <td
                        className={`table-cell text-right font-semibold ${isReturn ? 'text-rose-700' : ''}`}
                      >
                        {formatMoney(sale.grand_total, currency)}
                      </td>
                      {isOwner ? (
                        <td
                          className={`table-cell text-right font-medium ${
                            sale.net_profit >= 0 ? 'text-emerald-600' : 'text-rose-600'
                          }`}
                        >
                          {formatMoney(sale.net_profit, currency)}
                        </td>
                      ) : null}
                      <td className="table-cell text-right">
                        <span className="inline-flex gap-1">
                          {!isReturn ? (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setRefunding(sale)}
                              title="Refund items from this sale"
                            >
                              <Undo2 className="h-4 w-4" />
                            </Button>
                          ) : null}
                          <Button variant="ghost" size="sm" onClick={() => setSelected(sale)} title="View receipt">
                            <Receipt className="h-4 w-4" />
                          </Button>
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {data ? (
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
        ) : null}
      </Card>

      <Modal
        open={Boolean(selected)}
        title={`Receipt ${selected?.receipt_number ?? ''}`}
        onClose={() => setSelected(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => window.print()}>
              <Printer className="h-4 w-4" />
              Reprint
            </Button>
            <Button onClick={() => setSelected(null)}>Close</Button>
          </>
        }
      >
        {selected ? (
          <div className="space-y-4 text-sm">
            <div className="text-center">
              <p className="text-base font-semibold uppercase tracking-wide text-ink">
                {store?.name ?? 'Super Sale'}
              </p>
              {store?.address ? <p className="text-xs text-ink-muted">{store.address}</p> : null}
              {store?.tax_id ? <p className="text-xs text-ink-muted">Tax ID {store.tax_id}</p> : null}
              <p className="mt-1 text-xs text-ink-muted">{formatDateTime(selected.timestamp)}</p>
              {selected.type === 'RETURN' ? (
                <p className="mt-2 inline-flex flex-col items-center gap-1">
                  <Badge tone="red">Refund against {selected.original_receipt_number}</Badge>
                  <span className="text-xs text-ink-muted">
                    {selected.reason}
                    {selected.restocked === false ? ' · not restocked' : ''}
                  </span>
                </p>
              ) : null}
            </div>

            <table className="w-full">
              <thead>
                <tr className="border-b border-edge text-xs uppercase tracking-wide text-ink-muted">
                  <th className="py-1.5 text-left">Item</th>
                  <th className="py-1.5 text-right">Qty</th>
                  <th className="py-1.5 text-right">Unit</th>
                  <th className="py-1.5 text-right">Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge">
                {selected.items.map((item) => (
                  <tr key={item.product_id}>
                    <td className="py-1.5">
                      {item.name}
                      {item.discount_percentage > 0 ? (
                        <span className="ml-1 text-xs text-amber-600">
                          -{formatPercent(item.discount_percentage, { digits: 0 })}
                        </span>
                      ) : null}
                    </td>
                    <td className="py-1.5 text-right">{item.quantity}</td>
                    <td className="py-1.5 text-right text-ink-muted">
                      {formatMoney(item.unit_selling_price, currency)}
                    </td>
                    <td className="py-1.5 text-right">{formatMoney(item.line_total, currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <dl className="space-y-1 border-t border-edge pt-3">
              <div className="flex justify-between text-ink-muted">
                <dt>Subtotal</dt>
                <dd>{formatMoney(selected.subtotal, currency)}</dd>
              </div>
              <div className="flex justify-between text-amber-600">
                <dt>Discounts</dt>
                <dd>-{formatMoney(selected.discount_total, currency)}</dd>
              </div>
              <div className="flex justify-between text-ink-muted">
                <dt>Tax</dt>
                <dd>{formatMoney(selected.tax_amount, currency)}</dd>
              </div>
              <div className="flex justify-between text-base font-semibold text-ink">
                <dt>Grand total</dt>
                <dd>{formatMoney(selected.grand_total, currency)}</dd>
              </div>
              {selected.amount_tendered != null ? (
                <div className="flex justify-between text-ink-muted">
                  <dt>Cash tendered</dt>
                  <dd>{formatMoney(selected.amount_tendered, currency)}</dd>
                </div>
              ) : null}
              {selected.change_due != null ? (
                <div className="flex justify-between text-emerald-700">
                  <dt>Change due</dt>
                  <dd>{formatMoney(selected.change_due, currency)}</dd>
                </div>
              ) : null}
              {selected.payment_breakdown ? (
                <div className="flex justify-between text-ink-muted">
                  <dt>Split</dt>
                  <dd>
                    {formatMoney(selected.payment_breakdown.cash, currency)} cash +{' '}
                    {formatMoney(selected.payment_breakdown.card, currency)} card
                  </dd>
                </div>
              ) : null}
              {isOwner ? (
                <div className="flex justify-between border-t border-edge pt-2 text-emerald-700">
                  <dt>Net profit</dt>
                  <dd>{formatMoney(selected.net_profit, currency)}</dd>
                </div>
              ) : null}
            </dl>

            <div className="flex flex-wrap items-center gap-2 border-t border-edge pt-3 text-xs text-ink-muted">
              <PaymentBadge method={selected.payment_method} />
              {selected.customer_name ? <Badge tone="blue">{selected.customer_name}</Badge> : null}
              {selected.loyalty_points_earned > 0 ? (
                <Badge tone="green">+{selected.loyalty_points_earned} loyalty points</Badge>
              ) : null}
              <span className="ml-auto">Served by {selected.cashier_id}</span>
            </div>
          </div>
        ) : null}
      </Modal>

      <ReturnDialog
        sale={refunding}
        open={Boolean(refunding)}
        currency={currency}
        onClose={() => setRefunding(null)}
      />
    </div>
  )
}
