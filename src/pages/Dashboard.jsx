import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { AlertTriangle, TrendingDown, TrendingUp } from 'lucide-react'
import Gauge from '../components/Gauge'
import { Badge, Card, CardHeader, EmptyState, ErrorState, Spinner, StockBadge } from '../components/ui'
import { useChartTheme } from '../context/ThemeContext'
import { useCurrency } from '../hooks/useStoreSettings'
import { api } from '../lib/api'
import { formatMoney, formatNumber, formatPercent, productEmoji } from '../lib/format'

function Sparkline({ data, dataKey, color }) {
  if (!data?.length) return <div className="h-12 w-28" />
  return (
    <div className="h-12 w-28">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 2, bottom: 4, left: 2 }}>
          <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function KpiCard({ label, value, caption, tone = 'slate', sparkline, badge = 'KPI' }) {
  const valueTone =
    tone === 'green' ? 'text-emerald-600' : tone === 'red' ? 'text-rose-600' : 'text-ink'
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-ink-muted">{label}</p>
        <Badge tone="blue">{badge}</Badge>
      </div>
      <div className="mt-3 flex items-end justify-between gap-3">
        <div className="min-w-0">
          <p className={`truncate text-3xl font-semibold ${valueTone}`}>{value}</p>
          {caption ? <p className="mt-1 text-sm text-ink-muted">{caption}</p> : null}
        </div>
        {sparkline}
      </div>
    </Card>
  )
}

export default function Dashboard() {
  const currency = useCurrency()
  const chart = useChartTheme()

  const metricsQuery = useQuery({ queryKey: ['dashboard', 'metrics'], queryFn: () => api('/api/dashboard/metrics') })
  const capacityQuery = useQuery({ queryKey: ['dashboard', 'capacity'], queryFn: () => api('/api/dashboard/capacity') })
  const seriesQuery = useQuery({
    queryKey: ['dashboard', 'profit-series', 7],
    queryFn: () => api('/api/dashboard/profit-series?days=7'),
  })
  const forecastQuery = useQuery({
    queryKey: ['dashboard', 'forecast', 7],
    queryFn: () => api('/api/dashboard/forecast?days=7&limit=6'),
  })
  const productsQuery = useQuery({
    queryKey: ['dashboard', 'products'],
    queryFn: () => api('/api/products?page_size=8&sort_by=selling_price&sort_dir=desc'),
  })

  const metrics = metricsQuery.data
  const series = seriesQuery.data ?? []
  const restockAlerts = (metrics?.low_stock_count ?? 0) + (metrics?.out_of_stock_count ?? 0)
  const profitPositive = (metrics?.net_profit_today ?? 0) >= 0

  return (
    <div className="space-y-5">
      {/* KPI row */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {metricsQuery.isLoading ? (
          <Card className="lg:col-span-3">
            <Spinner label="Loading today's figures…" />
          </Card>
        ) : metricsQuery.isError ? (
          <Card className="lg:col-span-3">
            <ErrorState error={metricsQuery.error} onRetry={metricsQuery.refetch} />
          </Card>
        ) : (
          <>
            <KpiCard
              label="Total Inventory Value"
              value={formatMoney(metrics.inventory_value_cost, currency)}
              caption={`Retail ${formatMoney(metrics.inventory_value_retail, currency)}`}
              sparkline={<Sparkline data={series} dataKey="revenue" color="#3b82f6" />}
            />
            <KpiCard
              label="Today's Profit/Loss"
              value={`${profitPositive ? '+' : ''}${formatMoney(metrics.net_profit_today, currency)}`}
              tone={profitPositive ? 'green' : 'red'}
              caption={`Margin ${formatPercent(metrics.profit_margin_today)} · ${metrics.transactions_today} sales${
                metrics.refunds_today > 0
                  ? ` · ${formatMoney(metrics.refunds_today, currency)} refunded`
                  : ''
              }`}
              sparkline={<Sparkline data={series} dataKey="profit" color={profitPositive ? '#10b981' : '#f43f5e'} />}
            />
            <KpiCard
              label="Restock Alerts"
              value={formatNumber(restockAlerts)}
              tone={restockAlerts > 0 ? 'red' : 'slate'}
              caption={`${metrics.low_stock_count} low · ${metrics.out_of_stock_count} out of stock`}
              sparkline={
                <span className="flex h-12 w-28 items-end justify-end">
                  {restockAlerts > 0 ? (
                    <AlertTriangle className="h-8 w-8 text-amber-500" aria-hidden="true" />
                  ) : null}
                </span>
              }
            />
          </>
        )}
      </div>

      {/* Capacity + chart + forecast */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <Card className="bg-slate-700 p-5 dark:bg-slate-800">
          <h2 className="text-base font-semibold text-white">Current Store Capacity</h2>
          {capacityQuery.isLoading ? (
            <Spinner label="" className="text-ink-faint" />
          ) : capacityQuery.isError ? (
            <p className="py-8 text-center text-sm text-ink-faint">{capacityQuery.error.message}</p>
          ) : (
            <div className="mt-4 flex items-start justify-around gap-4">
              <Gauge
                percent={capacityQuery.data.shelf.percent}
                tone="amber"
                label="Shelf Load"
                caption={`${formatNumber(capacityQuery.data.shelf.used)} / ${formatNumber(capacityQuery.data.shelf.maximum)} units`}
              />
              <Gauge
                percent={capacityQuery.data.warehouse.percent}
                tone="green"
                label="Warehouse Storage"
                caption={`${formatNumber(capacityQuery.data.warehouse.used)} / ${formatNumber(capacityQuery.data.warehouse.maximum)} units`}
              />
            </div>
          )}
        </Card>

        <Card className="p-5">
          <div className="flex items-start justify-between">
            <h2 className="text-base font-semibold text-ink">Financial Summary (Profit/Loss)</h2>
            <span className="text-sm text-ink-muted">Past 7 days</span>
          </div>
          {seriesQuery.isLoading ? (
            <Spinner label="" />
          ) : seriesQuery.isError ? (
            <ErrorState error={seriesQuery.error} onRetry={seriesQuery.refetch} />
          ) : (
            <div className="mt-4 h-52">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={series} margin={{ top: 5, right: 8, bottom: 0, left: -12 }}>
                  <defs>
                    <linearGradient id="profitFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 12, fill: chart.axis }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 12, fill: chart.axis }} tickLine={false} axisLine={false} width={56} />
                  <Tooltip
                    formatter={(value, name) => [formatMoney(value, currency), name === 'profit' ? 'Profit' : 'Revenue']}
                    labelFormatter={(label, payload) => payload?.[0]?.payload?.date ?? label}
                    contentStyle={chart.tooltip}
                  />
                  <Area type="monotone" dataKey="profit" stroke="#3b82f6" strokeWidth={2} fill="url(#profitFill)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card className="flex flex-col">
          <CardHeader
            title="Demand Forecast & Next Duration Need"
            subtitle="Products predicted to be in high demand"
          />
          <div className="mt-3 flex-1 overflow-x-auto scroll-slim">
            {forecastQuery.isLoading ? (
              <Spinner label="" />
            ) : forecastQuery.isError ? (
              <ErrorState error={forecastQuery.error} onRetry={forecastQuery.refetch} />
            ) : forecastQuery.data.length === 0 ? (
              <EmptyState
                title="No restock needed"
                description="Every product has enough cover for the next 7 days."
              />
            ) : (
              <table className="min-w-full">
                <thead className="border-b border-edge">
                  <tr>
                    <th className="table-header">Product</th>
                    <th className="table-header text-right">Current Stock</th>
                    <th className="table-header text-right">Recommended Next Order</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-edge">
                  {forecastQuery.data.map((row) => (
                    <tr key={row.product_id}>
                      <td className="table-cell">
                        <span className="flex items-center gap-2">
                          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-surface-muted text-base">
                            {productEmoji(row)}
                          </span>
                          <span className="truncate font-medium text-ink">{row.name}</span>
                        </span>
                      </td>
                      <td className="table-cell text-right">{formatNumber(row.current_stock)}</td>
                      <td className="table-cell text-right font-semibold text-brand-600">
                        {formatNumber(row.recommended_order)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Card>
      </div>

      {/* Inventory overview */}
      <Card>
        <CardHeader
          title="Inventory Overview"
          subtitle="Highest priced items in the catalogue"
          action={
            <Link to="/inventory" className="text-sm font-medium text-brand-600 hover:text-brand-700">
              View all
            </Link>
          }
        />
        <div className="mt-4 overflow-x-auto scroll-slim">
          {productsQuery.isLoading ? (
            <Spinner />
          ) : productsQuery.isError ? (
            <ErrorState error={productsQuery.error} onRetry={productsQuery.refetch} />
          ) : (
            <table className="min-w-full">
              <thead className="border-y border-edge bg-surface-muted">
                <tr>
                  <th className="table-header">Item Name</th>
                  <th className="table-header">Barcode</th>
                  <th className="table-header">Category</th>
                  <th className="table-header">Stock Level</th>
                  <th className="table-header text-right">Stock</th>
                  <th className="table-header text-right">Buying Price</th>
                  <th className="table-header text-right">Selling Price</th>
                  <th className="table-header text-right">Market Price</th>
                  <th className="table-header text-right">Discount (%)</th>
                  <th className="table-header text-right">Unit Profit</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge">
                {productsQuery.data.items.map((product) => (
                  <tr key={product.id} className="hover:bg-surface-muted">
                    <td className="table-cell">
                      <span className="flex items-center gap-2">
                        <span className="flex h-8 w-8 items-center justify-center rounded-md bg-surface-muted text-base">
                          {productEmoji(product)}
                        </span>
                        <span>
                          <span className="block font-medium text-ink">{product.name}</span>
                          {product.brand ? (
                            <span className="block text-xs text-ink-muted">{product.brand}</span>
                          ) : null}
                        </span>
                      </span>
                    </td>
                    <td className="table-cell font-mono text-xs text-ink-muted">{product.barcode}</td>
                    <td className="table-cell">{product.category}</td>
                    <td className="table-cell">
                      <StockBadge status={product.status} />
                    </td>
                    <td className="table-cell text-right">{formatNumber(product.stock_total)}</td>
                    <td className="table-cell text-right">{formatMoney(product.buying_price, currency)}</td>
                    <td className="table-cell bg-brand-50/60 dark:bg-brand-500/10 text-right font-medium">
                      {formatMoney(product.selling_price, currency)}
                    </td>
                    <td className="table-cell text-right text-ink-muted">
                      {formatMoney(product.market_price, currency)}
                    </td>
                    <td className="table-cell text-right">{formatPercent(product.discount_percentage, { digits: 0 })}</td>
                    <td
                      className={`table-cell text-right font-semibold ${
                        product.unit_profit >= 0 ? 'text-emerald-600' : 'text-rose-600'
                      }`}
                    >
                      <span className="inline-flex items-center gap-1">
                        {product.unit_profit >= 0 ? (
                          <TrendingUp className="h-3.5 w-3.5" aria-hidden="true" />
                        ) : (
                          <TrendingDown className="h-3.5 w-3.5" aria-hidden="true" />
                        )}
                        {formatMoney(product.unit_profit, currency)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Card>
    </div>
  )
}
