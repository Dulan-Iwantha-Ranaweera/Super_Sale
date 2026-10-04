import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import ProductForm from '../components/ProductForm'
import { Button, Card, CardHeader, EmptyState, ErrorState, Spinner, StockBadge } from '../components/ui'
import { useToast } from '../context/ToastContext'
import { useCurrency } from '../hooks/useStoreSettings'
import { api, buildQuery } from '../lib/api'
import { formatMoney, formatNumber, productEmoji } from '../lib/format'

/**
 * Owner-only data entry. The same form creates a new item or adjusts an
 * existing one — searching by barcode loads the product into the form so the
 * owner never has to retype a catalogue entry to fix one price.
 */
export default function DetailsInput() {
  const currency = useCurrency()
  const toast = useToast()
  const queryClient = useQueryClient()

  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState(null)
  const [formKey, setFormKey] = useState(0)

  const resultsQuery = useQuery({
    queryKey: ['details-input', 'search', search],
    queryFn: () => api(`/api/products${buildQuery({ search, page_size: 6, sort_by: 'name' })}`),
    enabled: search.trim().length >= 2,
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['products'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    queryClient.invalidateQueries({ queryKey: ['categories'] })
    queryClient.invalidateQueries({ queryKey: ['details-input'] })
  }

  const saveMutation = useMutation({
    mutationFn: (payload) =>
      editing
        ? api(`/api/products/${editing.id}`, { method: 'PUT', body: payload })
        : api('/api/products', { method: 'POST', body: payload }),
    onSuccess: (product) => {
      invalidate()
      toast.success(editing ? `${product.name} updated` : `${product.name} added to the catalogue`)
      setEditing(null)
      setSearch('')
      setFormKey((key) => key + 1)
    },
  })

  const startNew = () => {
    setEditing(null)
    setSearch('')
    setFormKey((key) => key + 1)
  }

  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1fr_340px]">
      <Card className="p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-2xl font-semibold text-ink">Input New Item / Adjust Details</h2>
            <p className="mt-1 text-sm text-ink-muted">
              {editing
                ? `Editing ${editing.name} — saving overwrites its pricing and stock.`
                : 'Fill in the product details. Profit and margin update live as you type.'}
            </p>
          </div>
          {editing ? (
            <Button variant="secondary" onClick={startNew}>
              Switch to new item
            </Button>
          ) : null}
        </div>

        <div className="mt-6">
          <ProductForm
            key={`${editing?.id ?? 'new'}-${formKey}`}
            submitLabel={editing ? 'SAVE CHANGES' : 'SAVE DETAILS'}
            submitting={saveMutation.isPending}
            initialValues={
              editing
                ? {
                    barcode: editing.barcode,
                    name: editing.name,
                    category: editing.category,
                    buying_price: String(editing.buying_price),
                    market_price: String(editing.market_price),
                    selling_price: String(editing.selling_price),
                    stock_shelf: String(editing.stock_shelf),
                    stock_warehouse: String(editing.stock_warehouse),
                    reorder_threshold: String(editing.reorder_threshold),
                    discount_percentage: String(editing.discount_percentage),
                  }
                : undefined
            }
            onSubmit={(payload) => saveMutation.mutateAsync(payload)}
          />
        </div>
      </Card>

      <Card className="h-fit">
        <CardHeader title="Adjust an existing item" subtitle="Search by name or barcode to load it into the form" />
        <div className="px-5 pb-5 pt-4">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
            <input
              className="field-input pl-9"
              placeholder="e.g. Milk or 01233456…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              aria-label="Search existing products"
            />
          </div>

          <div className="mt-4">
            {search.trim().length < 2 ? (
              <p className="text-sm text-ink-faint">Type at least two characters to search.</p>
            ) : resultsQuery.isLoading ? (
              <Spinner label="" />
            ) : resultsQuery.isError ? (
              <ErrorState error={resultsQuery.error} onRetry={resultsQuery.refetch} />
            ) : (resultsQuery.data?.items ?? []).length === 0 ? (
              <EmptyState title="No match" description="Nothing in the catalogue matches that search." />
            ) : (
              <ul className="divide-y divide-edge">
                {(resultsQuery.data?.items ?? []).map((product) => (
                  <li key={product.id}>
                    <button
                      type="button"
                      onClick={() => setEditing(product)}
                      className={`flex w-full items-center gap-3 px-1 py-3 text-left transition hover:bg-surface-muted
                        ${editing?.id === product.id ? 'bg-brand-50/60 dark:bg-brand-500/10' : ''}`}
                    >
                      <span className="flex h-9 w-9 items-center justify-center rounded-md bg-surface-muted text-base">
                        {productEmoji(product)}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-ink">{product.name}</span>
                        <span className="block text-xs text-ink-muted">
                          {formatMoney(product.selling_price, currency)} ·{' '}
                          {formatNumber(product.stock_total)} in stock
                        </span>
                      </span>
                      <StockBadge status={product.status} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </Card>
    </div>
  )
}
