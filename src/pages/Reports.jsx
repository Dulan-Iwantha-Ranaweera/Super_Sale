import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { CalendarRange } from 'lucide-react'
import { Badge, Card, CardHeader, EmptyState, ErrorState, Spinner } from '../components/ui'
import { useChartTheme } from '../context/ThemeContext'
import { useCurrency } from '../hooks/useStoreSettings'
import { api, buildQuery } from '../lib/api'
import { formatMoney, formatNumber, formatPercent } from '../lib/format'

const RANGE_PRESETS = [
  { value: 7, label: 'Last 7 days' },
  { value: 30, label: 'Last 30 days' },
  { value: 90, label: 'Last 90 days' },
  { value: 365, label: 'Last 12 months' },
]

const SLICE_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4', '#ec4899', '#84cc16', '#64748b']

function KpiTile({ label, value, tone = 'slate', caption }) {
  const toneClass =
    tone === 'green' ? 'text-emerald-600' : tone === 'red' ? 'text-rose-600' : 'text-ink'
  return (
    <Card className="p-5">
      <p className="text-sm font-medium text-ink-muted">{label}</p>
      <p className={`mt-2 text-2xl font-semibold ${toneClass}`}>{value}</p>
      {caption ? <p className="mt-1 text-sm text-ink-muted">{caption}</p> : null}
    </Card>
  )
}

export default function Reports() {
  const currency = useCurrency()
  const chart = useChartTheme()
  const currentYear = new Date().getFullYear()
  const [days, setDays] = useState(30)
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [year, setYear] = useState(currentYear)

  const usingCustomRange = Boolean(start && end)
  const rangeQuery = useMemo(
    () => buildQuery(usingCustomRange ? { start, end } : { days }),
    [usingCustomRange, start, end, days],
  )

  const summaryQuery = useQuery({
    queryKey: ['reports', 'summary', rangeQuery],
    queryFn: () => api(`/api/reports/summary${rangeQuery}`),
  })
  const monthlyQuery = useQuery({
    queryKey: ['reports', 'monthly', year],
    queryFn: () => api(`/api/reports/monthly?year=${year}`),
  })
  const categoryQuery = useQuery({
    queryKey: ['reports', 'by-category', rangeQuery],
    queryFn: () => api(`/api/reports/by-category${rangeQuery}`),
  })
  const topQuery = useQuery({
    queryKey: ['reports', 'top-products', days],
    queryFn: () => api(`/api/reports/top-products?days=${days}&limit=8`),
  })

  const summary = summaryQuery.data
  const categories = categoryQuery.data ?? []
  const hasCategoryData = categories.some((row) => row.revenue > 0)

  return (
    <div className="space-y-5">
      <Card className="flex flex-wrap items-end gap-4 p-5">
        <label className="flex flex-col text-sm">
          <span className="field-label">Range</span>
          <select
            className="field-input w-auto min-w-[160px]"
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
          <input type="date" className="field-input w-auto" value={start} onChange={(event) => setStart(event.target.value)} />
        </label>
        <label className="flex flex-col text-sm">
          <span className="field-label">To</span>
          <input type="date" className="field-input w-auto" value={end} onChange={(event) => setEnd(event.target.value)} />
        </label>

        {usingCustomRange ? (
          <button
            type="button"
            className="pb-2 text-sm font-medium text-brand-600 hover:text-brand-700"
            onClick={() => {
              setStart('')
              setEnd('')
            }}
          >
            Clear custom range
          </button>
        ) : null}

        <label className="ml-auto flex flex-col text-sm">
          <span className="field-label">Monthly chart year</span>
          <select
            className="field-input w-auto min-w-[120px]"
            value={year}
            onChange={(event) => setYear(Number(event.target.value))}
          >
            {[currentYear, currentYear - 1, currentYear - 2].map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </Card>

      {summaryQuery.isLoading ? (
        <Card>
          <Spinner label="Crunching the numbers…" />
        </Card>
      ) : summaryQuery.isError ? (
        <Card>
          <ErrorState error={summaryQuery.error} onRetry={summaryQuery.refetch} />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
          <KpiTile
            label="Net Revenue"
            value={formatMoney(summary.net_revenue, currency)}
            caption={
              summary.refunds > 0
                ? `${formatNumber(summary.transactions)} sales less ${formatMoney(summary.refunds, currency)} in ${formatNumber(summary.returns)} refunds`
                : `${formatNumber(summary.transactions)} transactions`
            }
          />
          <KpiTile
            label="Cost of Goods"
            value={formatMoney(summary.cost_of_goods, currency)}
            caption={`${formatNumber(summary.items_sold)} units sold`}
          />
          <KpiTile
            label="Net Profit"
            value={`${summary.net_profit >= 0 ? '+' : ''}${formatMoney(summary.net_profit, currency)}`}
            tone={summary.net_profit >= 0 ? 'green' : 'red'}
          />
          <KpiTile
            label="Profit Margin (%)"
            value={formatPercent(summary.profit_margin)}
            tone={summary.profit_margin >= 0 ? 'green' : 'red'}
          />
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card className="p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-ink">Monthly Sales</h2>
            <Badge tone="slate">
              <CalendarRange className="mr-1 inline h-3.5 w-3.5" />
              {year}
            </Badge>
          </div>
          {monthlyQuery.isLoading ? (
            <Spinner label="" />
          ) : monthlyQuery.isError ? (
            <ErrorState error={monthlyQuery.error} onRetry={monthlyQuery.refetch} />
          ) : (
            <div className="mt-4 h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={monthlyQuery.data} margin={{ top: 5, right: 8, bottom: 0, left: -12 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} vertical={false} />
                  <XAxis dataKey="month" tick={{ fontSize: 12, fill: chart.axis }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 12, fill: chart.axis }} tickLine={false} axisLine={false} width={56} />
                  <Tooltip
                    formatter={(value, name) => [formatMoney(value, currency), name === 'profit' ? 'Profit' : 'Revenue']}
                    contentStyle={chart.tooltip}
                    cursor={{ fill: chart.cursor }}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="revenue" name="Revenue" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="profit" name="Profit" fill="#10b981" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card className="p-5">
          <h2 className="text-base font-semibold text-ink">Profit by Category</h2>
          {categoryQuery.isLoading ? (
            <Spinner label="" />
          ) : categoryQuery.isError ? (
            <ErrorState error={categoryQuery.error} onRetry={categoryQuery.refetch} />
          ) : !hasCategoryData ? (
            <EmptyState title="No sales in this range" description="Pick a wider date range to see the breakdown." />
          ) : (
            <div className="mt-4 h-72">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={categories}
                    dataKey="profit"
                    nameKey="category"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={2}
                  >
                    {categories.map((entry, index) => (
                      <Cell key={entry.category} fill={SLICE_COLORS[index % SLICE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value, name) => [formatMoney(value, currency), name]}
                    contentStyle={chart.tooltip}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      <Card>
        <CardHeader title="Top Performing Products" subtitle={`By revenue over the last ${days} days`} />
        <div className="mt-4 overflow-x-auto scroll-slim">
          {topQuery.isLoading ? (
            <Spinner label="" />
          ) : topQuery.isError ? (
            <ErrorState error={topQuery.error} onRetry={topQuery.refetch} />
          ) : topQuery.data.length === 0 ? (
            <EmptyState title="No sales recorded yet" description="Complete a sale in the POS to populate this table." />
          ) : (
            <table className="min-w-full">
              <thead className="border-y border-edge bg-surface-muted">
                <tr>
                  <th className="table-header">Product</th>
                  <th className="table-header text-right">Units Sold</th>
                  <th className="table-header text-right">Revenue</th>
                  <th className="table-header text-right">Profit</th>
                  <th className="table-header text-right">Margin</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge">
                {topQuery.data.map((row) => (
                  <tr key={row.name} className="hover:bg-surface-muted">
                    <td className="table-cell font-medium text-ink">{row.name}</td>
                    <td className="table-cell text-right">{formatNumber(row.units)}</td>
                    <td className="table-cell text-right">{formatMoney(row.revenue, currency)}</td>
                    <td className="table-cell text-right font-semibold text-emerald-600">
                      {formatMoney(row.profit, currency)}
                    </td>
                    <td className="table-cell text-right text-ink-muted">
                      {formatPercent(row.revenue > 0 ? (row.profit / row.revenue) * 100 : 0)}
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
