import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BrainCircuit,
  Info,
  TrendingUp,
} from 'lucide-react'
import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, Spinner } from '../components/ui'
import { useToast } from '../context/ToastContext'
import { useCurrency } from '../hooks/useStoreSettings'
import { api } from '../lib/api'
import { formatDateTime, formatMoney, formatNumber, formatPercent, productEmoji } from '../lib/format'

const CONFIDENCE_TONES = { HIGH: 'green', MEDIUM: 'amber', LOW: 'slate' }

function ModelCard({ model, onRetrain, retraining }) {
  if (!model?.trained) return null
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50 text-brand-600 dark:bg-brand-500/15 dark:text-brand-200">
            <BrainCircuit className="h-5 w-5" />
          </span>
          <div>
            <h2 className="text-base font-semibold text-ink">Demand model</h2>
            <p className="mt-0.5 text-sm text-ink-muted">
              {model.algorithm} · trained {formatDateTime(model.trained_at)} on{' '}
              {formatNumber(model.n_samples)} windows
            </p>
          </div>
        </div>
        <Button variant="secondary" loading={retraining} onClick={onRetrain}>
          Retrain on latest sales
        </Button>
      </div>

      <dl className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <dt className="text-xs text-ink-muted">Average error</dt>
          <dd className="mt-1 text-lg font-semibold text-ink">
            {model.mae?.toFixed(2)} units
          </dd>
          <dd className="text-xs text-ink-faint">over {model.horizon_days} days</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Naive baseline</dt>
          <dd className="mt-1 text-lg font-semibold text-ink-muted">
            {model.baseline_mae?.toFixed(2)} units
          </dd>
          <dd className="text-xs text-ink-faint">last fortnight repeated</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Improvement</dt>
          <dd
            className={`mt-1 text-lg font-semibold ${
              model.beats_baseline ? 'text-emerald-600' : 'text-rose-600'
            }`}
          >
            {formatPercent(model.improvement_percent, { withSign: true, digits: 1 })}
          </dd>
          <dd className="text-xs text-ink-faint">vs the baseline</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">R²</dt>
          <dd className="mt-1 text-lg font-semibold text-ink">{model.r2?.toFixed(2)}</dd>
          <dd className="text-xs text-ink-faint">on held-out weeks</dd>
        </div>
      </dl>

      {model.beats_baseline === false ? (
        <p className="mt-4 flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          This model is currently no better than simply repeating the last fortnight. Treat the
          suggestions below as weak evidence until there is more sales history.
        </p>
      ) : null}
    </Card>
  )
}

function ProductCell({ row }) {
  return (
    <span className="flex items-center gap-2">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-surface-muted text-base">
        {productEmoji(row)}
      </span>
      <span className="min-w-0">
        <span className="block truncate font-medium text-ink">{row.name}</span>
        <span className="block text-xs text-ink-muted">
          {row.brand ? `${row.brand} · ` : ''}
          {row.category}
        </span>
      </span>
    </span>
  )
}

function DemandCell({ value }) {
  const rising = value >= 0
  const Icon = rising ? ArrowUpRight : ArrowDownRight
  return (
    <span className={`inline-flex items-center gap-1 font-medium ${rising ? 'text-emerald-600' : 'text-rose-600'}`}>
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {formatPercent(value, { withSign: true, digits: 0 })}
    </span>
  )
}

export default function IPF() {
  const currency = useCurrency()
  const toast = useToast()
  const queryClient = useQueryClient()

  const modelQuery = useQuery({ queryKey: ['ipf', 'model'], queryFn: () => api('/api/ipf/model') })
  const forecastQuery = useQuery({
    queryKey: ['ipf', 'forecast'],
    queryFn: () => api('/api/ipf/forecast?limit=15'),
    enabled: Boolean(modelQuery.data?.trained),
    retry: false,
  })

  const trainMutation = useMutation({
    mutationFn: () => api('/api/ipf/train', { method: 'POST' }),
    onSuccess: (model) => {
      queryClient.setQueryData(['ipf', 'model'], model)
      queryClient.invalidateQueries({ queryKey: ['ipf', 'forecast'] })
      toast.success(
        model.beats_baseline
          ? `Model trained — ${formatPercent(model.improvement_percent, { digits: 1 })} better than the baseline`
          : 'Model trained, but it does not beat the naive baseline yet',
      )
    },
    onError: (error) => toast.error(error.message),
  })

  if (modelQuery.isLoading) {
    return (
      <Card>
        <Spinner label="Checking the forecasting model…" />
      </Card>
    )
  }

  if (modelQuery.isError) {
    return (
      <Card>
        <ErrorState error={modelQuery.error} onRetry={modelQuery.refetch} />
      </Card>
    )
  }

  if (!modelQuery.data?.trained) {
    return (
      <Card>
        <EmptyState
          icon={BrainCircuit}
          title="The forecasting model has not been trained yet"
          description="Training reads your whole sales history and learns how demand for each product moves. It takes a few seconds and can be repeated any time."
          action={
            <Button loading={trainMutation.isPending} onClick={() => trainMutation.mutate()}>
              Train the model
            </Button>
          }
        />
      </Card>
    )
  }

  const forecast = forecastQuery.data

  return (
    <div className="space-y-5">
      <ModelCard
        model={modelQuery.data}
        retraining={trainMutation.isPending}
        onRetrain={() => trainMutation.mutate()}
      />

      <Card className="flex items-start gap-3 border-brand-200 bg-brand-50/50 dark:bg-brand-500/10 p-4">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" aria-hidden="true" />
        <p className="text-sm text-ink-muted">
          <span className="font-medium text-ink">How to read this.</span> The model forecasts{' '}
          <strong>demand</strong> for the next {forecast?.horizon_days ?? 14} days from your own
          sales history. It does not predict supplier or market prices — your ledger has never
          recorded a price change, so there is nothing to learn that from. Each suggestion below
          combines the demand forecast with figures you already know: the margin, and the gap
          between your shelf price and the market price you recorded for the item.
        </p>
      </Card>

      {forecastQuery.isLoading ? (
        <Card>
          <Spinner label="Scoring the catalogue…" />
        </Card>
      ) : forecastQuery.isError ? (
        <Card>
          <ErrorState error={forecastQuery.error} onRetry={forecastQuery.refetch} />
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-5 xl:grid-cols-4">
            <Card className="p-5">
              <p className="text-sm font-medium text-ink-muted">Projected upside</p>
              <p className="mt-2 text-2xl font-semibold text-emerald-600">
                {formatMoney(forecast.projected_upside, currency)}
              </p>
              <p className="mt-1 text-sm text-ink-muted">if every raise is taken</p>
            </Card>
            <Card className="p-5">
              <p className="text-sm font-medium text-ink-muted">Can carry a higher price</p>
              <p className="mt-2 text-2xl font-semibold text-ink">
                {formatNumber(forecast.opportunities.length)}
              </p>
              <p className="mt-1 text-sm text-ink-muted">items</p>
            </Card>
            <Card className="p-5">
              <p className="text-sm font-medium text-ink-muted">Heading for a loss</p>
              <p className="mt-2 text-2xl font-semibold text-rose-600">
                {formatNumber(forecast.risks.length)}
              </p>
              <p className="mt-1 text-sm text-ink-muted">items need attention</p>
            </Card>
            <Card className="p-5">
              <p className="text-sm font-medium text-ink-muted">Loss exposure</p>
              <p className="mt-2 text-2xl font-semibold text-rose-600">
                {formatMoney(Math.abs(forecast.projected_exposure), currency)}
              </p>
              <p className="mt-1 text-sm text-ink-muted">
                over {forecast.horizon_days} days if nothing changes
              </p>
            </Card>
          </div>

          {/* ------------------------------------------------ opportunities */}
          <Card>
            <CardHeader
              title="Can be sold at a higher price"
              subtitle={`Demand is rising and you are still priced under the market — next ${forecast.horizon_days} days`}
              action={<Badge tone="green">{forecast.opportunities.length} items</Badge>}
            />
            <div className="mt-4 overflow-x-auto scroll-slim">
              {forecast.opportunities.length === 0 ? (
                <EmptyState
                  icon={TrendingUp}
                  title="No pricing headroom right now"
                  description="No product is both gaining demand and priced under its market reference."
                />
              ) : (
                <table className="min-w-full">
                  <thead className="border-y border-edge bg-surface-muted">
                    <tr>
                      <th className="table-header">Product</th>
                      <th className="table-header text-right">Current</th>
                      <th className="table-header text-right">Market</th>
                      <th className="table-header text-right">Suggested</th>
                      <th className="table-header text-right">Demand</th>
                      <th className="table-header text-right">Forecast units</th>
                      <th className="table-header text-right">Extra / unit</th>
                      <th className="table-header text-right">Projected gain</th>
                      <th className="table-header">Confidence</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-edge">
                    {forecast.opportunities.map((row) => (
                      <tr key={row.product_id} className="align-top hover:bg-surface-muted">
                        <td className="table-cell">
                          <ProductCell row={row} />
                          <p className="mt-1 max-w-sm whitespace-normal text-xs text-ink-muted">
                            {row.reason}
                          </p>
                        </td>
                        <td className="table-cell text-right">{formatMoney(row.current_price, currency)}</td>
                        <td className="table-cell text-right text-ink-muted">
                          {formatMoney(row.market_price, currency)}
                        </td>
                        <td className="table-cell text-right font-semibold text-emerald-700">
                          {formatMoney(row.suggested_price, currency)}
                          <span className="block text-xs font-normal text-emerald-600">
                            {formatPercent(row.price_change_percent, { withSign: true, digits: 1 })}
                          </span>
                        </td>
                        <td className="table-cell text-right">
                          <DemandCell value={row.demand_change_percent} />
                        </td>
                        <td className="table-cell text-right">
                          {formatNumber(Math.round(row.predicted_units))}
                          <span className="block text-xs text-ink-faint">
                            was {formatNumber(Math.round(row.recent_units))}
                          </span>
                        </td>
                        <td className="table-cell text-right">
                          {formatMoney(row.extra_profit_per_unit, currency)}
                        </td>
                        <td className="table-cell text-right font-semibold text-emerald-600">
                          {formatMoney(row.projected_profit_impact, currency)}
                        </td>
                        <td className="table-cell">
                          <Badge tone={CONFIDENCE_TONES[row.confidence]}>{row.confidence}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </Card>

          {/* -------------------------------------------------------- risks */}
          <Card>
            <CardHeader
              title="At risk of selling at a loss"
              subtitle="Already below cost, or slow-moving stock that will need a markdown to clear"
              action={<Badge tone="red">{forecast.risks.length} items</Badge>}
            />
            <div className="mt-4 overflow-x-auto scroll-slim">
              {forecast.risks.length === 0 ? (
                <EmptyState
                  title="Nothing is heading for a loss"
                  description="Every line is covering its cost with demand to match."
                />
              ) : (
                <table className="min-w-full">
                  <thead className="border-y border-edge bg-surface-muted">
                    <tr>
                      <th className="table-header">Product</th>
                      <th className="table-header text-right">Current</th>
                      <th className="table-header text-right">Cost</th>
                      <th className="table-header text-right">Unit profit</th>
                      <th className="table-header text-right">Margin</th>
                      <th className="table-header text-right">Demand</th>
                      <th className="table-header text-right">Days of cover</th>
                      <th className="table-header text-right">Suggested</th>
                      <th className="table-header">Confidence</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-edge">
                    {forecast.risks.map((row) => (
                      <tr key={row.product_id} className="align-top hover:bg-surface-muted">
                        <td className="table-cell">
                          <ProductCell row={row} />
                          <p className="mt-1 max-w-sm whitespace-normal text-xs text-ink-muted">
                            {row.reason}
                          </p>
                        </td>
                        <td className="table-cell text-right">{formatMoney(row.current_price, currency)}</td>
                        <td className="table-cell text-right text-ink-muted">
                          {formatMoney(row.buying_price, currency)}
                        </td>
                        <td
                          className={`table-cell text-right font-semibold ${
                            row.unit_profit >= 0 ? 'text-ink' : 'text-rose-600'
                          }`}
                        >
                          {formatMoney(row.unit_profit, currency)}
                        </td>
                        <td className="table-cell text-right">{formatPercent(row.margin_percent, { digits: 1 })}</td>
                        <td className="table-cell text-right">
                          <DemandCell value={row.demand_change_percent} />
                        </td>
                        <td className="table-cell text-right">{Math.round(row.days_of_cover)}</td>
                        <td className="table-cell text-right font-semibold text-ink">
                          {formatMoney(row.suggested_price, currency)}
                          <span className="block text-xs font-normal text-ink-muted">
                            {formatPercent(row.price_change_percent, { withSign: true, digits: 1 })}
                          </span>
                        </td>
                        <td className="table-cell">
                          <Badge tone={CONFIDENCE_TONES[row.confidence]}>{row.confidence}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </Card>

          <p className="px-1 text-xs text-ink-faint">
            {formatNumber(forecast.generated_rows)} products scored · {formatNumber(forecast.steady)}{' '}
            steady · suggestions are capped at the market price you recorded and never fall below cost.
          </p>
        </>
      )}
    </div>
  )
}
