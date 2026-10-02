import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Banknote,
  CreditCard,
  Delete,
  Minus,
  Plus,
  Receipt,
  ScanLine,
  Search,
  Split,
  Trash2,
  UserPlus,
  X,
} from 'lucide-react'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Modal,
  Spinner,
} from '../components/ui'
import { useToast } from '../context/ToastContext'
import { useStoreSettings } from '../hooks/useStoreSettings'
import { api, buildQuery } from '../lib/api'
import { computeTotals, round2 } from '../lib/money'
import { formatMoney, formatNumber, formatPercent, productEmoji } from '../lib/format'

function PaymentButton({ active, icon: Icon, label, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex flex-col items-center gap-1 rounded-lg border px-3 py-3 text-xs font-medium transition
        ${
          active
            ? 'border-emerald-600 bg-emerald-600 text-white shadow-sm'
            : 'border-edge-strong bg-surface text-ink-muted hover:bg-surface-muted'
        }`}
    >
      <Icon className="h-5 w-5" aria-hidden="true" />
      {label}
    </button>
  )
}

export default function POS() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const { data: store } = useStoreSettings()
  const currency = store?.currency ?? 'LKR'
  const taxRate = store?.tax_rate ?? 0

  const scanRef = useRef(null)
  const [scanValue, setScanValue] = useState('')
  const [scanError, setScanError] = useState(null)
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('ALL')
  const [lines, setLines] = useState([])
  const [paymentMethod, setPaymentMethod] = useState('CASH')
  const [tendered, setTendered] = useState('')
  const [splitCard, setSplitCard] = useState('')
  const [customer, setCustomer] = useState(null)
  const [customerOpen, setCustomerOpen] = useState(false)
  const [receipt, setReceipt] = useState(null)

  const categoriesQuery = useQuery({ queryKey: ['categories'], queryFn: () => api('/api/products/categories') })
  const productsQuery = useQuery({
    queryKey: ['pos-products', search, category],
    queryFn: () =>
      api(
        `/api/products${buildQuery({
          search,
          category: category === 'ALL' ? undefined : category,
          page_size: 60,
          sort_by: 'name',
        })}`,
      ),
  })

  const totals = useMemo(() => computeTotals(lines, taxRate), [lines, taxRate])

  // The scanner is a keyboard device: keep focus on the field whenever possible.
  useEffect(() => {
    scanRef.current?.focus()
  }, [])

  const addProduct = (product) => {
    setScanError(null)
    if (product.stock_shelf <= 0) {
      toast.error(`${product.name} has no shelf stock left`)
      return
    }
    setLines((previous) => {
      const existing = previous.find((line) => line.product.id === product.id)
      if (existing) {
        if (existing.quantity >= product.stock_shelf) {
          toast.error(`Only ${product.stock_shelf} units of ${product.name} on the shelf`)
          return previous
        }
        return previous.map((line) =>
          line.product.id === product.id ? { ...line, quantity: line.quantity + 1 } : line,
        )
      }
      return [...previous, { product, quantity: 1, discount: product.discount_percentage ?? 0 }]
    })
  }

  const scanMutation = useMutation({
    mutationFn: (barcode) => api(`/api/products/barcode/${encodeURIComponent(barcode)}`),
    onSuccess: (product) => {
      addProduct(product)
      setScanValue('')
    },
    onError: (error) => {
      setScanError(error.message)
      setScanValue('')
    },
  })

  const updateQuantity = (productId, delta) => {
    setLines((previous) =>
      previous.flatMap((line) => {
        if (line.product.id !== productId) return [line]
        const next = line.quantity + delta
        if (next <= 0) return []
        if (next > line.product.stock_shelf) {
          toast.error(`Only ${line.product.stock_shelf} units on the shelf`)
          return [line]
        }
        return [{ ...line, quantity: next }]
      }),
    )
  }

  const setDiscount = (productId, value) => {
    const parsed = Math.min(100, Math.max(0, Number(value) || 0))
    setLines((previous) =>
      previous.map((line) => (line.product.id === productId ? { ...line, discount: parsed } : line)),
    )
  }

  const removeLine = (productId) =>
    setLines((previous) => previous.filter((line) => line.product.id !== productId))

  const resetSale = () => {
    setLines([])
    setTendered('')
    setSplitCard('')
    setCustomer(null)
    setPaymentMethod('CASH')
    setScanError(null)
    scanRef.current?.focus()
  }

  const checkoutMutation = useMutation({
    mutationFn: (payload) => api('/api/sales/checkout', { method: 'POST', body: payload }),
    onSuccess: (sale) => {
      setReceipt(sale)
      resetSale()
      queryClient.invalidateQueries({ queryKey: ['products'] })
      queryClient.invalidateQueries({ queryKey: ['pos-products'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['customers'] })
      toast.success(`Sale ${sale.receipt_number} completed`)
    },
    onError: (error) => toast.error(error.message),
  })

  const tenderedAmount = Number(tendered) || 0
  const splitCardAmount = Number(splitCard) || 0
  const splitCashAmount = round2(Math.max(0, totals.grandTotal - splitCardAmount))
  const changeDue = round2(Math.max(0, tenderedAmount - totals.grandTotal))

  const canComplete =
    lines.length > 0 &&
    !checkoutMutation.isPending &&
    (paymentMethod !== 'CASH' || tendered === '' || tenderedAmount + 0.009 >= totals.grandTotal) &&
    (paymentMethod !== 'SPLIT' || (splitCardAmount > 0 && splitCardAmount <= totals.grandTotal))

  const completeOrder = () => {
    if (!canComplete) return
    const payload = {
      items: lines.map((line) => ({
        product_id: line.product.id,
        quantity: line.quantity,
        discount_percentage: line.discount,
      })),
      payment_method: paymentMethod,
      customer_id: customer?.id ?? null,
    }
    if (paymentMethod === 'CASH' && tendered !== '') payload.amount_tendered = round2(tenderedAmount)
    if (paymentMethod === 'SPLIT') {
      payload.payment_breakdown = { cash: splitCashAmount, card: round2(splitCardAmount) }
    }
    checkoutMutation.mutate(payload)
  }

  const keypadPress = (key) => {
    const target = paymentMethod === 'SPLIT' ? splitCard : tendered
    const setTarget = paymentMethod === 'SPLIT' ? setSplitCard : setTendered
    if (key === 'back') {
      setTarget(target.slice(0, -1))
      return
    }
    if (key === '.' && target.includes('.')) return
    if (target.includes('.') && target.split('.')[1]?.length >= 2) return
    setTarget(`${target}${key}`)
  }

  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1.9fr_1fr]">
      {/* ---------------------------------------------------------- catalogue */}
      <div className="space-y-4">
        <Card className="p-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative min-w-[240px] flex-1">
              <ScanLine className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-brand-500" />
              <input
                ref={scanRef}
                className="field-input py-3 pl-10 text-base"
                placeholder="Scan or type a barcode, then press Enter"
                value={scanValue}
                onChange={(event) => {
                  setScanValue(event.target.value)
                  setScanError(null)
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && scanValue.trim()) {
                    event.preventDefault()
                    scanMutation.mutate(scanValue.trim())
                  }
                }}
                aria-label="Barcode"
              />
            </div>
            <div className="relative min-w-[180px]">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
              <input
                className="field-input pl-9"
                placeholder="Search products…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                aria-label="Search products"
              />
            </div>
          </div>
          {scanError ? (
            <p className="mt-2 text-sm text-rose-600" role="alert">
              {scanError}
            </p>
          ) : null}

          <div className="mt-3 flex flex-wrap gap-2">
            {['ALL', ...(categoriesQuery.data ?? [])].map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setCategory(option)}
                className={`rounded-full px-3 py-1.5 text-sm font-medium transition
                  ${
                    category === option
                      ? 'bg-slate-800 text-white dark:bg-brand-600'
                      : 'bg-surface-muted text-ink-muted hover:bg-surface-muted'
                  }`}
              >
                {option === 'ALL' ? 'All' : option}
              </button>
            ))}
          </div>
        </Card>

        <Card className="p-4">
          {productsQuery.isLoading ? (
            <Spinner label="Loading catalogue…" />
          ) : productsQuery.isError ? (
            <ErrorState error={productsQuery.error} onRetry={productsQuery.refetch} />
          ) : (productsQuery.data?.items ?? []).length === 0 ? (
            <EmptyState title="No products found" description="Try another search term or category." />
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 2xl:grid-cols-4">
              {(productsQuery.data?.items ?? []).map((product) => {
                const soldOut = product.stock_shelf <= 0
                return (
                  <button
                    key={product.id}
                    type="button"
                    disabled={soldOut}
                    onClick={() => addProduct(product)}
                    className={`flex flex-col items-start gap-1 rounded-lg border p-3 text-left transition
                      ${
                        soldOut
                          ? 'cursor-not-allowed border-edge bg-surface-muted opacity-60'
                          : 'border-edge bg-surface hover:border-brand-500 hover:shadow-sm'
                      }`}
                  >
                    <span className="flex w-full items-start justify-between gap-2">
                      <span className="flex h-9 w-9 items-center justify-center rounded-md bg-surface-muted text-lg">
                        {productEmoji(product)}
                      </span>
                      {product.discount_percentage > 0 ? (
                        <Badge tone="amber">-{formatPercent(product.discount_percentage, { digits: 0 })}</Badge>
                      ) : null}
                    </span>
                    {product.brand ? (
                      <span className="text-[11px] font-medium uppercase tracking-wide text-ink-faint">
                        {product.brand}
                      </span>
                    ) : null}
                    <span className="line-clamp-2 text-sm font-medium text-ink">{product.name}</span>
                    <span className="text-sm font-semibold text-ink">
                      {formatMoney(product.effective_selling_price, currency)}
                    </span>
                    <span className={`text-xs ${soldOut ? 'text-rose-600' : 'text-ink-faint'}`}>
                      {soldOut ? 'Out of shelf stock' : `${formatNumber(product.stock_shelf)} on shelf`}
                    </span>
                  </button>
                )
              })}
            </div>
          )}
        </Card>
      </div>

      {/* ------------------------------------------------------------- ticket */}
      <Card className="flex max-h-[calc(100vh-7rem)] flex-col xl:sticky xl:top-6">
        <div className="flex items-center justify-between border-b border-edge px-5 py-4">
          <h2 className="text-base font-semibold text-ink">Current Sale</h2>
          {lines.length > 0 ? (
            <Button variant="ghost" size="sm" onClick={resetSale}>
              <Trash2 className="h-4 w-4" />
              Clear
            </Button>
          ) : null}
        </div>

        <div className="min-h-[120px] flex-1 overflow-y-auto scroll-slim px-3 py-2">
          {lines.length === 0 ? (
            <EmptyState
              icon={Receipt}
              title="No items yet"
              description="Scan a barcode or tap a product to start the sale."
            />
          ) : (
            <ul className="divide-y divide-edge">
              {lines.map((line) => {
                const effective = round2(line.product.selling_price * (1 - line.discount / 100))
                return (
                  <li key={line.product.id} className="py-3">
                    <div className="flex items-start gap-2">
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-surface-muted text-base">
                        {productEmoji(line.product)}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-ink">
                          {line.product.brand ? (
                            <span className="text-ink-muted">{line.product.brand} </span>
                          ) : null}
                          {line.product.name}
                        </p>
                        <p className="text-xs text-ink-muted">
                          {formatMoney(effective, currency)} each
                          {line.discount > 0 ? (
                            <span className="ml-1 text-amber-600">
                              (was {formatMoney(line.product.selling_price, currency)})
                            </span>
                          ) : null}
                        </p>
                      </div>
                      <span className="text-sm font-semibold text-ink">
                        {formatMoney(round2(effective * line.quantity), currency)}
                      </span>
                      <button
                        type="button"
                        onClick={() => removeLine(line.product.id)}
                        className="rounded p-1 text-ink-faint hover:bg-surface-muted hover:text-rose-600"
                        aria-label={`Remove ${line.product.name}`}
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>

                    <div className="mt-2 flex items-center gap-2 pl-10">
                      <span className="inline-flex items-center rounded-md border border-edge-strong">
                        <button
                          type="button"
                          className="px-2 py-1 text-ink-muted hover:bg-surface-muted"
                          onClick={() => updateQuantity(line.product.id, -1)}
                          aria-label="Decrease quantity"
                        >
                          <Minus className="h-3.5 w-3.5" />
                        </button>
                        <span className="min-w-8 px-2 text-center text-sm font-medium">{line.quantity}</span>
                        <button
                          type="button"
                          className="px-2 py-1 text-ink-muted hover:bg-surface-muted"
                          onClick={() => updateQuantity(line.product.id, 1)}
                          aria-label="Increase quantity"
                        >
                          <Plus className="h-3.5 w-3.5" />
                        </button>
                      </span>
                      <label className="flex items-center gap-1 text-xs text-ink-muted">
                        Disc %
                        <input
                          type="number"
                          min="0"
                          max="100"
                          step="1"
                          value={line.discount}
                          onChange={(event) => setDiscount(line.product.id, event.target.value)}
                          className="w-16 rounded border border-edge-strong px-2 py-1 text-sm"
                        />
                      </label>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        <div className="border-t border-edge px-5 py-4">
          <button
            type="button"
            onClick={() => setCustomerOpen(true)}
            className="mb-3 flex w-full items-center justify-between rounded-lg border border-edge-strong px-3 py-2 text-sm hover:bg-surface-muted"
          >
            <span className="flex items-center gap-2 text-ink-muted">
              <UserPlus className="h-4 w-4" />
              {customer ? customer.name : 'Add customer (optional)'}
            </span>
            {customer ? (
              <Badge tone="blue">{formatNumber(customer.loyalty_points)} pts</Badge>
            ) : (
              <span className="text-xs text-ink-faint">Loyalty</span>
            )}
          </button>

          <dl className="space-y-1 text-sm">
            <div className="flex justify-between text-ink-muted">
              <dt>Subtotal</dt>
              <dd>{formatMoney(totals.subtotal, currency)}</dd>
            </div>
            <div className="flex justify-between text-amber-600">
              <dt>Discounts</dt>
              <dd>-{formatMoney(totals.discountTotal, currency)}</dd>
            </div>
            <div className="flex justify-between text-ink-muted">
              <dt>Tax ({formatPercent(taxRate, { digits: 0 })})</dt>
              <dd>{formatMoney(totals.tax, currency)}</dd>
            </div>
            <div className="flex justify-between border-t border-edge pt-2 text-base font-semibold text-ink">
              <dt>Total</dt>
              <dd>{formatMoney(totals.grandTotal, currency)}</dd>
            </div>
          </dl>

          <div className="mt-4 grid grid-cols-3 gap-2">
            <PaymentButton
              active={paymentMethod === 'CASH'}
              icon={Banknote}
              label="Cash"
              onClick={() => setPaymentMethod('CASH')}
            />
            <PaymentButton
              active={paymentMethod === 'CARD'}
              icon={CreditCard}
              label="Card"
              onClick={() => setPaymentMethod('CARD')}
            />
            <PaymentButton
              active={paymentMethod === 'SPLIT'}
              icon={Split}
              label="Split"
              onClick={() => setPaymentMethod('SPLIT')}
            />
          </div>

          {paymentMethod !== 'CARD' ? (
            <div className="mt-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-ink-muted">
                  {paymentMethod === 'SPLIT' ? 'Card portion' : 'Cash tendered'}
                </span>
                <span className="font-mono text-base font-semibold text-ink">
                  {formatMoney(paymentMethod === 'SPLIT' ? splitCardAmount : tenderedAmount, currency)}
                </span>
              </div>
              {paymentMethod === 'SPLIT' ? (
                <p className="mt-1 text-right text-xs text-ink-muted">
                  Cash portion {formatMoney(splitCashAmount, currency)}
                </p>
              ) : tendered !== '' ? (
                <p
                  className={`mt-1 text-right text-xs ${
                    tenderedAmount + 0.009 >= totals.grandTotal ? 'text-emerald-600' : 'text-rose-600'
                  }`}
                >
                  {tenderedAmount + 0.009 >= totals.grandTotal
                    ? `Change due ${formatMoney(changeDue, currency)}`
                    : 'Tendered amount is below the total'}
                </p>
              ) : null}

              <div className="mt-2 grid grid-cols-3 gap-1.5">
                {['1', '2', '3', '4', '5', '6', '7', '8', '9', '.', '0'].map((key) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => keypadPress(key)}
                    className="rounded-lg border border-edge bg-surface py-2.5 text-base font-medium text-ink hover:bg-surface-muted"
                  >
                    {key}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => keypadPress('back')}
                  className="flex items-center justify-center rounded-lg border border-edge bg-surface py-2.5 text-ink-muted hover:bg-surface-muted"
                  aria-label="Backspace"
                >
                  <Delete className="h-4 w-4" />
                </button>
              </div>
            </div>
          ) : null}

          <Button
            variant="success"
            size="lg"
            className="mt-4 w-full"
            disabled={!canComplete}
            loading={checkoutMutation.isPending}
            onClick={completeOrder}
          >
            COMPLETE ORDER · {formatMoney(totals.grandTotal, currency)}
          </Button>
        </div>
      </Card>

      <CustomerPicker
        open={customerOpen}
        onClose={() => setCustomerOpen(false)}
        onSelect={(selected) => {
          setCustomer(selected)
          setCustomerOpen(false)
        }}
        onClear={() => {
          setCustomer(null)
          setCustomerOpen(false)
        }}
        selected={customer}
      />

      <ReceiptModal receipt={receipt} currency={currency} store={store} onClose={() => setReceipt(null)} />
    </div>
  )
}

function CustomerPicker({ open, onClose, onSelect, onClear, selected }) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newPhone, setNewPhone] = useState('')

  const customersQuery = useQuery({
    queryKey: ['customers', 'picker', search],
    queryFn: () => api(`/api/customers${buildQuery({ search, page_size: 8, sort_by: 'name', sort_dir: 'asc' })}`),
    enabled: open,
  })

  const createMutation = useMutation({
    mutationFn: (payload) => api('/api/customers', { method: 'POST', body: payload }),
    onSuccess: (customer) => {
      queryClient.invalidateQueries({ queryKey: ['customers'] })
      toast.success(`${customer.name} added`)
      setCreating(false)
      setNewName('')
      setNewPhone('')
      onSelect(customer)
    },
    onError: (error) => toast.error(error.message),
  })

  // The query is disabled until the dialog opens, so `data` is undefined while
  // idle: derive the list defensively rather than reading `data.items`.
  const results = customersQuery.data?.items ?? []
  const loadingResults = customersQuery.isFetching && !customersQuery.data

  return (
    <Modal open={open} title="Attach a customer" onClose={onClose}>
      {creating ? (
        <div className="space-y-4">
          <Field label="Full name">
            <input className="field-input" value={newName} onChange={(event) => setNewName(event.target.value)} autoFocus />
          </Field>
          <Field label="Mobile number">
            <input className="field-input" value={newPhone} onChange={(event) => setNewPhone(event.target.value)} />
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setCreating(false)}>
              Back
            </Button>
            <Button
              loading={createMutation.isPending}
              disabled={!newName.trim() || newPhone.trim().length < 3}
              onClick={() => createMutation.mutate({ name: newName.trim(), phone: newPhone.trim() })}
            >
              Create & attach
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <input
            className="field-input"
            placeholder="Search by name or mobile…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            autoFocus
          />
          {loadingResults ? (
            <Spinner label="" />
          ) : customersQuery.isError ? (
            <ErrorState error={customersQuery.error} onRetry={customersQuery.refetch} />
          ) : results.length === 0 ? (
            <EmptyState title="No matching customer" description="Create a new one to start their loyalty record." />
          ) : (
            <ul className="divide-y divide-edge">
              {results.map((customer) => (
                <li key={customer.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(customer)}
                    className="flex w-full items-center justify-between gap-3 px-1 py-2.5 text-left hover:bg-surface-muted"
                  >
                    <span>
                      <span className="block text-sm font-medium text-ink">{customer.name}</span>
                      <span className="block text-xs text-ink-muted">{customer.phone}</span>
                    </span>
                    <Badge tone="blue">{formatNumber(customer.loyalty_points)} pts</Badge>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex justify-between gap-2 pt-2">
            {selected ? (
              <Button variant="secondary" onClick={onClear}>
                Remove customer
              </Button>
            ) : (
              <span />
            )}
            <Button onClick={() => setCreating(true)}>
              <UserPlus className="h-4 w-4" />
              New customer
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}

function ReceiptModal({ receipt, currency, store, onClose }) {
  if (!receipt) return null
  return (
    <Modal
      open={Boolean(receipt)}
      title={`Receipt ${receipt.receipt_number}`}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={() => window.print()}>
            Print
          </Button>
          <Button onClick={onClose}>New sale</Button>
        </>
      }
    >
      <div className="space-y-4 text-sm">
        <div className="text-center">
          <p className="text-base font-semibold uppercase tracking-wide text-ink">{store?.name ?? 'Super Sale'}</p>
          {store?.address ? <p className="text-xs text-ink-muted">{store.address}</p> : null}
          {store?.tax_id ? <p className="text-xs text-ink-muted">Tax ID {store.tax_id}</p> : null}
        </div>

        <table className="w-full">
          <thead>
            <tr className="border-b border-edge text-xs uppercase tracking-wide text-ink-muted">
              <th className="py-1.5 text-left">Item</th>
              <th className="py-1.5 text-right">Qty</th>
              <th className="py-1.5 text-right">Total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-edge">
            {receipt.items.map((item) => (
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
                <td className="py-1.5 text-right">{formatMoney(item.line_total, currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <dl className="space-y-1 border-t border-edge pt-3">
          <div className="flex justify-between text-ink-muted">
            <dt>Subtotal</dt>
            <dd>{formatMoney(receipt.subtotal, currency)}</dd>
          </div>
          <div className="flex justify-between text-amber-600">
            <dt>Discounts</dt>
            <dd>-{formatMoney(receipt.discount_total, currency)}</dd>
          </div>
          <div className="flex justify-between text-ink-muted">
            <dt>Tax</dt>
            <dd>{formatMoney(receipt.tax_amount, currency)}</dd>
          </div>
          <div className="flex justify-between text-base font-semibold text-ink">
            <dt>Grand total</dt>
            <dd>{formatMoney(receipt.grand_total, currency)}</dd>
          </div>
          {receipt.change_due !== null && receipt.change_due !== undefined ? (
            <div className="flex justify-between text-emerald-700">
              <dt>Change due</dt>
              <dd>{formatMoney(receipt.change_due, currency)}</dd>
            </div>
          ) : null}
        </dl>

        <div className="flex flex-wrap gap-2 border-t border-edge pt-3 text-xs text-ink-muted">
          <Badge tone="slate">{receipt.payment_method}</Badge>
          {receipt.customer_name ? <Badge tone="blue">{receipt.customer_name}</Badge> : null}
          {receipt.loyalty_points_earned > 0 ? (
            <Badge tone="green">+{receipt.loyalty_points_earned} loyalty points</Badge>
          ) : null}
          <span className="ml-auto">Served by {receipt.cashier_id}</span>
        </div>
      </div>
    </Modal>
  )
}
