import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDownUp, PackagePlus, Pencil, Plus, Search } from 'lucide-react'
import ProductForm from '../components/ProductForm'
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Modal,
  Pagination,
  SortableHeader,
  Spinner,
  StockBadge,
} from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { useCurrency } from '../hooks/useStoreSettings'
import { api, buildQuery } from '../lib/api'
import { formatMoney, formatNumber, formatPercent, productEmoji } from '../lib/format'

const PAGE_SIZE = 12

const STATUS_OPTIONS = [
  { value: 'ALL', label: 'All stock levels' },
  { value: 'IN_STOCK', label: 'In stock' },
  { value: 'LOW_STOCK', label: 'Low stock' },
  { value: 'OUT_OF_STOCK', label: 'Out of stock' },
]

function useDebounced(value, delay = 300) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

export default function Inventory() {
  const currency = useCurrency()
  const toast = useToast()
  const queryClient = useQueryClient()
  const { isOwner } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()

  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounced(search)
  const [category, setCategory] = useState('ALL')
  const [brand, setBrand] = useState('ALL')
  const [status, setStatus] = useState(searchParams.get('status') ?? 'ALL')
  const [sortBy, setSortBy] = useState('name')
  const [sortDir, setSortDir] = useState('asc')
  const [page, setPage] = useState(1)

  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [restocking, setRestocking] = useState(null)
  const [restockQuantity, setRestockQuantity] = useState('')

  // Keep the deep-link (?status=LOW_STOCK from the bell icon) in sync.
  useEffect(() => {
    const next = searchParams.get('status')
    if (next && next !== status) setStatus(next)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  useEffect(() => {
    setPage(1)
  }, [debouncedSearch, category, brand, status, sortBy, sortDir])

  const categoriesQuery = useQuery({ queryKey: ['categories'], queryFn: () => api('/api/products/categories') })
  const brandsQuery = useQuery({ queryKey: ['brands'], queryFn: () => api('/api/products/brands') })

  const queryString = useMemo(
    () =>
      buildQuery({
        search: debouncedSearch,
        category: category === 'ALL' ? undefined : category,
        brand: brand === 'ALL' ? undefined : brand,
        stock_status: status,
        sort_by: sortBy,
        sort_dir: sortDir,
        page,
        page_size: PAGE_SIZE,
      }),
    [debouncedSearch, category, brand, status, sortBy, sortDir, page],
  )

  const productsQuery = useQuery({
    queryKey: ['products', queryString],
    queryFn: () => api(`/api/products${queryString}`),
    placeholderData: (previous) => previous,
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['products'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    queryClient.invalidateQueries({ queryKey: ['categories'] })
  }

  const createMutation = useMutation({
    mutationFn: (payload) => api('/api/products', { method: 'POST', body: payload }),
    onSuccess: (product) => {
      invalidate()
      setCreateOpen(false)
      toast.success(`${product.name} added to the catalogue`)
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }) => api(`/api/products/${id}`, { method: 'PUT', body: payload }),
    onSuccess: (product) => {
      invalidate()
      setEditing(null)
      toast.success(`${product.name} updated`)
    },
  })

  const transferMutation = useMutation({
    mutationFn: ({ id, quantity }) =>
      api(`/api/products/${id}/transfer`, { method: 'POST', body: { quantity } }),
    onSuccess: (product) => {
      invalidate()
      setRestocking(null)
      setRestockQuantity('')
      toast.success(`Moved stock to the shelf — ${product.stock_shelf} now on display`)
    },
    onError: (error) => toast.error(error.message),
  })

  const onSort = (field) => {
    if (sortBy === field) setSortDir((previous) => (previous === 'asc' ? 'desc' : 'asc'))
    else {
      setSortBy(field)
      setSortDir('asc')
    }
  }

  const onStatusChange = (value) => {
    setStatus(value)
    setSearchParams(value === 'ALL' ? {} : { status: value }, { replace: true })
  }

  const data = productsQuery.data
  const items = data?.items ?? []

  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-wrap items-center gap-3 p-5">
          <div className="relative min-w-[200px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
            <input
              className="field-input pl-9"
              placeholder="Search by name or barcode…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              aria-label="Search products"
            />
          </div>

          <select
            className="field-input w-auto min-w-[160px]"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            aria-label="Filter by category"
          >
            <option value="ALL">All categories</option>
            {(categoriesQuery.data ?? []).map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>

          <select
            className="field-input w-auto min-w-[150px]"
            value={brand}
            onChange={(event) => setBrand(event.target.value)}
            aria-label="Filter by brand"
          >
            <option value="ALL">All brands</option>
            {(brandsQuery.data ?? []).map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>

          <select
            className="field-input w-auto min-w-[160px]"
            value={status}
            onChange={(event) => onStatusChange(event.target.value)}
            aria-label="Filter by stock status"
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          <span className="hidden items-center gap-1.5 text-sm text-ink-faint sm:inline-flex">
            <ArrowDownUp className="h-4 w-4" />
            Click a column to sort
          </span>

          {isOwner ? (
            <Button className="ml-auto" onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" />
              Add Product
            </Button>
          ) : null}
        </div>

        <div className="overflow-x-auto scroll-slim">
          {productsQuery.isLoading ? (
            <Spinner label="Loading inventory…" />
          ) : productsQuery.isError ? (
            <ErrorState error={productsQuery.error} onRetry={productsQuery.refetch} />
          ) : items.length === 0 ? (
            <EmptyState
              title="No products match these filters"
              description="Try clearing the search box or switching the category filter."
            />
          ) : (
            <table className="min-w-full">
              <thead className="border-y border-edge bg-surface-muted">
                <tr>
                  <SortableHeader field="name" label="Product Name" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                  <SortableHeader field="barcode" label="Barcode" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                  <SortableHeader field="category" label="Category" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                  <th className="table-header text-right">Stock (Shelf / Warehouse)</th>
                  <SortableHeader
                    field="buying_price"
                    label="Buy Price"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                  />
                  <SortableHeader
                    field="selling_price"
                    label="Sell Price"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                  />
                  <th className="table-header text-right">Discount</th>
                  <th className="table-header text-right">Unit Profit</th>
                  <th className="table-header">Status</th>
                  {isOwner ? <th className="table-header text-right">Actions</th> : null}
                </tr>
              </thead>
              <tbody className="divide-y divide-edge">
                {items.map((product) => (
                  <tr key={product.id} className="hover:bg-surface-muted">
                    <td className="table-cell">
                      <span className="flex items-center gap-2">
                        <span className="flex h-8 w-8 items-center justify-center rounded-md bg-surface-muted text-base">
                          {productEmoji(product)}
                        </span>
                        <span className="min-w-0">
                          <span className="block truncate font-medium text-ink">{product.name}</span>
                          {product.brand ? (
                            <span className="block text-xs text-ink-muted">{product.brand}</span>
                          ) : null}
                        </span>
                      </span>
                    </td>
                    <td className="table-cell font-mono text-xs text-ink-muted">{product.barcode}</td>
                    <td className="table-cell">{product.category}</td>
                    <td className="table-cell text-right">
                      <span className="font-medium text-ink">{formatNumber(product.stock_shelf)}</span>
                      <span className="text-ink-faint"> / {formatNumber(product.stock_warehouse)}</span>
                    </td>
                    <td className="table-cell text-right">{formatMoney(product.buying_price, currency)}</td>
                    <td className="table-cell text-right font-medium">{formatMoney(product.selling_price, currency)}</td>
                    <td className="table-cell text-right">{formatPercent(product.discount_percentage, { digits: 0 })}</td>
                    <td
                      className={`table-cell text-right font-semibold ${
                        product.unit_profit >= 0 ? 'text-emerald-600' : 'text-rose-600'
                      }`}
                    >
                      {formatMoney(product.unit_profit, currency)}
                    </td>
                    <td className="table-cell">
                      <StockBadge status={product.status} />
                    </td>
                    {isOwner ? (
                      <td className="table-cell text-right">
                        <span className="inline-flex gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setRestocking(product)}
                            title="Move warehouse stock to the shelf"
                          >
                            <PackagePlus className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => setEditing(product)} title="Edit product">
                            <Pencil className="h-4 w-4" />
                          </Button>
                        </span>
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {data ? (
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
        ) : null}
      </Card>

      <Modal open={createOpen} title="Add Product" onClose={() => setCreateOpen(false)} width="max-w-3xl">
        <ProductForm
          compact
          submitLabel="Create product"
          submitting={createMutation.isPending}
          onCancel={() => setCreateOpen(false)}
          onSubmit={(payload) => createMutation.mutateAsync(payload)}
        />
      </Modal>

      <Modal open={Boolean(editing)} title={`Edit ${editing?.name ?? ''}`} onClose={() => setEditing(null)} width="max-w-3xl">
        {editing ? (
          <ProductForm
            compact
            submitLabel="Save changes"
            submitting={updateMutation.isPending}
            onCancel={() => setEditing(null)}
            initialValues={{
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
            }}
            onSubmit={(payload) => updateMutation.mutateAsync({ id: editing.id, payload })}
          />
        ) : null}
      </Modal>

      <Modal
        open={Boolean(restocking)}
        title={`Replenish shelf — ${restocking?.name ?? ''}`}
        onClose={() => {
          setRestocking(null)
          setRestockQuantity('')
        }}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setRestocking(null)
                setRestockQuantity('')
              }}
            >
              Cancel
            </Button>
            <Button
              loading={transferMutation.isPending}
              disabled={!restockQuantity || Number(restockQuantity) <= 0}
              onClick={() =>
                transferMutation.mutate({ id: restocking.id, quantity: Math.trunc(Number(restockQuantity)) })
              }
            >
              Move to shelf
            </Button>
          </>
        }
      >
        {restocking ? (
          <div className="space-y-4">
            <p className="text-sm text-ink-muted">
              Shelf holds <strong>{formatNumber(restocking.stock_shelf)}</strong> units, warehouse holds{' '}
              <strong>{formatNumber(restocking.stock_warehouse)}</strong>.
            </p>
            <Field label="Units to move from warehouse to shelf">
              <input
                className="field-input"
                type="number"
                min="1"
                max={restocking.stock_warehouse}
                step="1"
                value={restockQuantity}
                onChange={(event) => setRestockQuantity(event.target.value)}
                autoFocus
              />
            </Field>
          </div>
        ) : null}
      </Modal>
    </div>
  )
}
