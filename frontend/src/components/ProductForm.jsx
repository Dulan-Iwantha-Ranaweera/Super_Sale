import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Field } from './ui'
import { api } from '../lib/api'
import { formatMoney, formatPercent } from '../lib/format'
import { previewProfit, toNumber } from '../lib/money'
import { useCurrency } from '../hooks/useStoreSettings'

const EMPTY = {
  barcode: '',
  name: '',
  brand: '',
  category: '',
  buying_price: '',
  market_price: '',
  selling_price: '',
  stock_shelf: '',
  stock_warehouse: '',
  reorder_threshold: '10',
  discount_percentage: '0',
}

function validate(values) {
  const errors = {}
  if (!values.barcode.trim()) errors.barcode = 'Barcode is required'
  else if (/\s/.test(values.barcode.trim())) errors.barcode = 'Barcode cannot contain spaces'
  if (!values.name.trim()) errors.name = 'Product name is required'
  if (!values.category.trim()) errors.category = 'Choose or type a category'

  const numericFields = [
    ['buying_price', 'Buying price'],
    ['market_price', 'Market price'],
    ['selling_price', 'Selling price'],
  ]
  numericFields.forEach(([key, label]) => {
    if (values[key] === '' || values[key] === null) errors[key] = `${label} is required`
    else if (toNumber(values[key]) < 0) errors[key] = `${label} cannot be negative`
  })

  const integerFields = [
    ['stock_shelf', 'Shelf stock'],
    ['stock_warehouse', 'Warehouse stock'],
    ['reorder_threshold', 'Reorder threshold'],
  ]
  integerFields.forEach(([key, label]) => {
    const value = toNumber(values[key])
    if (values[key] === '' || value < 0) errors[key] = `${label} must be zero or more`
    else if (!Number.isInteger(value)) errors[key] = `${label} must be a whole number`
  })

  const discount = toNumber(values.discount_percentage)
  if (discount < 0 || discount > 100) errors.discount_percentage = 'Discount must be between 0 and 100'

  return errors
}

export default function ProductForm({
  initialValues,
  onSubmit,
  submitting = false,
  submitLabel = 'Save details',
  onCancel,
  compact = false,
}) {
  const currency = useCurrency()
  const [values, setValues] = useState(() => ({ ...EMPTY, ...(initialValues ?? {}) }))
  const [touched, setTouched] = useState({})
  const [serverError, setServerError] = useState(null)

  const categoriesQuery = useQuery({ queryKey: ['categories'], queryFn: () => api('/api/products/categories') })
  const brandsQuery = useQuery({ queryKey: ['brands'], queryFn: () => api('/api/products/brands') })
  const errors = useMemo(() => validate(values), [values])
  const preview = previewProfit(values.selling_price, values.buying_price, values.discount_percentage)
  const isValid = Object.keys(errors).length === 0

  const setValue = (key) => (event) => {
    setValues((previous) => ({ ...previous, [key]: event.target.value }))
    setServerError(null)
  }

  const markTouched = (key) => () => setTouched((previous) => ({ ...previous, [key]: true }))
  const errorFor = (key) => (touched[key] ? errors[key] : undefined)

  const handleSubmit = async (event) => {
    event.preventDefault()
    setTouched(Object.fromEntries(Object.keys(EMPTY).map((key) => [key, true])))
    if (!isValid) return
    setServerError(null)
    try {
      await onSubmit({
        barcode: values.barcode.trim(),
        name: values.name.trim(),
        brand: values.brand.trim() || null,
        category: values.category.trim(),
        buying_price: toNumber(values.buying_price),
        market_price: toNumber(values.market_price),
        selling_price: toNumber(values.selling_price),
        stock_shelf: Math.trunc(toNumber(values.stock_shelf)),
        stock_warehouse: Math.trunc(toNumber(values.stock_warehouse)),
        reorder_threshold: Math.trunc(toNumber(values.reorder_threshold)),
        discount_percentage: toNumber(values.discount_percentage),
      })
    } catch (error) {
      setServerError(error.message)
    }
  }

  const gridClass = compact ? 'grid grid-cols-1 gap-4 sm:grid-cols-2' : 'grid grid-cols-1 gap-5 sm:grid-cols-2'

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div className={gridClass}>
        <Field label="Barcode" error={errorFor('barcode')}>
          <input
            className="field-input font-mono"
            value={values.barcode}
            onChange={setValue('barcode')}
            onBlur={markTouched('barcode')}
            placeholder="0123345678901"
          />
        </Field>
        <Field label="Product Name" error={errorFor('name')}>
          <input
            className="field-input"
            value={values.name}
            onChange={setValue('name')}
            onBlur={markTouched('name')}
            placeholder="Whole Milk 1L"
          />
        </Field>

        <Field label="Brand" hint="Leave blank for loose or unbranded goods">
          <input
            className="field-input"
            list="product-brands"
            value={values.brand}
            onChange={setValue('brand')}
            placeholder="Anchor"
          />
          <datalist id="product-brands">
            {(brandsQuery.data ?? []).map((brand) => (
              <option key={brand} value={brand} />
            ))}
          </datalist>
        </Field>
        <Field label="Category" error={errorFor('category')} hint="Pick an existing category or type a new one">
          <input
            className="field-input"
            list="product-categories"
            value={values.category}
            onChange={setValue('category')}
            onBlur={markTouched('category')}
            placeholder="Dairy"
          />
          <datalist id="product-categories">
            {(categoriesQuery.data ?? []).map((category) => (
              <option key={category} value={category} />
            ))}
          </datalist>
        </Field>
        <Field label={`Discount (%)`} error={errorFor('discount_percentage')}>
          <input
            className="field-input"
            type="number"
            min="0"
            max="100"
            step="0.01"
            value={values.discount_percentage}
            onChange={setValue('discount_percentage')}
            onBlur={markTouched('discount_percentage')}
          />
        </Field>

        <Field label={`Buying Price (${currency})`} error={errorFor('buying_price')}>
          <input
            className="field-input"
            type="number"
            min="0"
            step="0.01"
            value={values.buying_price}
            onChange={setValue('buying_price')}
            onBlur={markTouched('buying_price')}
          />
        </Field>
        <Field label={`Market Price (${currency})`} error={errorFor('market_price')} hint="Competitor reference price">
          <input
            className="field-input"
            type="number"
            min="0"
            step="0.01"
            value={values.market_price}
            onChange={setValue('market_price')}
            onBlur={markTouched('market_price')}
          />
        </Field>
        <Field label={`Selling Price (${currency})`} error={errorFor('selling_price')}>
          <input
            className="field-input"
            type="number"
            min="0"
            step="0.01"
            value={values.selling_price}
            onChange={setValue('selling_price')}
            onBlur={markTouched('selling_price')}
          />
        </Field>
        <Field label="Reorder Threshold (safety stock)" error={errorFor('reorder_threshold')}>
          <input
            className="field-input"
            type="number"
            min="0"
            step="1"
            value={values.reorder_threshold}
            onChange={setValue('reorder_threshold')}
            onBlur={markTouched('reorder_threshold')}
          />
        </Field>

        <Field label="Initial Stock (Shelf)" error={errorFor('stock_shelf')}>
          <input
            className="field-input"
            type="number"
            min="0"
            step="1"
            value={values.stock_shelf}
            onChange={setValue('stock_shelf')}
            onBlur={markTouched('stock_shelf')}
          />
        </Field>
        <Field label="Warehouse Stock" error={errorFor('stock_warehouse')}>
          <input
            className="field-input"
            type="number"
            min="0"
            step="1"
            value={values.stock_warehouse}
            onChange={setValue('stock_warehouse')}
            onBlur={markTouched('stock_warehouse')}
          />
        </Field>
      </div>

      {/* Live preview — mirrors the server-side profit formula as the user types. */}
      <div className="rounded-lg border border-edge bg-surface-muted p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Live calculation</p>
        <div className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <p className="text-xs text-ink-muted">Effective price</p>
            <p className="text-lg font-semibold text-ink">{formatMoney(preview.effective, currency)}</p>
          </div>
          <div>
            <p className="text-xs text-ink-muted">Unit profit</p>
            <p className={`text-lg font-semibold ${preview.profit >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
              {formatMoney(preview.profit, currency)}
            </p>
          </div>
          <div>
            <p className="text-xs text-ink-muted">Net margin</p>
            <p className={`text-lg font-semibold ${preview.margin >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
              {formatPercent(preview.margin)}
            </p>
          </div>
          <div>
            <p className="text-xs text-ink-muted">Total stock</p>
            <p className="text-lg font-semibold text-ink">
              {Math.trunc(toNumber(values.stock_shelf)) + Math.trunc(toNumber(values.stock_warehouse))}
            </p>
          </div>
        </div>
        {preview.profit < 0 ? (
          <p className="mt-3 text-sm text-amber-700">
            Heads up: this product would sell at a loss after the discount is applied.
          </p>
        ) : null}
      </div>

      {serverError ? (
        <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300" role="alert">
          {serverError}
        </p>
      ) : null}

      <div className="flex justify-end gap-2">
        {onCancel ? (
          <Button variant="secondary" onClick={onCancel} type="button">
            Cancel
          </Button>
        ) : null}
        <Button type="submit" loading={submitting} size={compact ? 'md' : 'lg'} className={compact ? '' : 'w-full'}>
          {submitLabel}
        </Button>
      </div>
    </form>
  )
}
