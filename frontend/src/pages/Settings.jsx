import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Lock, Monitor, Moon, Sun } from 'lucide-react'
import ProfilePanel from '../components/ProfilePanel'
import { Button, Card, ErrorState, Field, Spinner } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import { useToast } from '../context/ToastContext'
import { useStoreSettings } from '../hooks/useStoreSettings'
import { api } from '../lib/api'

const CURRENCIES = ['LKR', 'USD', 'EUR', 'GBP', 'INR', 'AUD', 'CAD', 'JPY']

const TABS = [
  { id: 'general', label: 'General' },
  { id: 'store', label: 'Store' },
  { id: 'preferences', label: 'System Preferences' },
  { id: 'account', label: 'My Profile' },
]

function toFormState(store) {
  return {
    name: store?.name ?? '',
    address: store?.address ?? '',
    tax_id: store?.tax_id ?? '',
    currency: store?.currency ?? 'LKR',
    tax_rate: String(store?.tax_rate ?? 0),
    default_discount: String(store?.default_discount ?? 0),
    shelf_capacity_max: String(store?.shelf_capacity_max ?? 0),
    warehouse_capacity_max: String(store?.warehouse_capacity_max ?? 0),
    loyalty_spend_per_point: String(store?.loyalty_spend_per_point ?? 10),
  }
}

export default function Settings() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const { user, isOwner } = useAuth()
  const storeQuery = useStoreSettings()
  const { preference, resolved, choose } = useTheme()

  const [tab, setTab] = useState('general')
  const [form, setForm] = useState(() => toFormState(storeQuery.data))
  const [error, setError] = useState(null)

  useEffect(() => {
    if (storeQuery.data) setForm(toFormState(storeQuery.data))
  }, [storeQuery.data])

  const saveMutation = useMutation({
    mutationFn: (payload) => api('/api/store', { method: 'PUT', body: payload }),
    onSuccess: (store) => {
      queryClient.setQueryData(['store'], store)
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      toast.success('Settings saved')
      setError(null)
    },
    onError: (saveError) => setError(saveError.message),
  })

  const setValue = (key) => (event) => setForm((previous) => ({ ...previous, [key]: event.target.value }))

  const reset = () => {
    setForm(toFormState(storeQuery.data))
    setError(null)
  }

  const saveSection = (section) => {
    setError(null)
    const numeric = (value) => Number(value)

    if (section === 'store') {
      if (!form.name.trim()) {
        setError('Store name is required')
        return
      }
      saveMutation.mutate({
        name: form.name.trim(),
        address: form.address.trim(),
        tax_id: form.tax_id.trim(),
      })
      return
    }

    if (section === 'preferences') {
      const taxRate = numeric(form.tax_rate)
      const defaultDiscount = numeric(form.default_discount)
      const loyalty = numeric(form.loyalty_spend_per_point)
      if (!Number.isFinite(taxRate) || taxRate < 0 || taxRate > 100) {
        setError('Tax rate must be between 0 and 100')
        return
      }
      if (!Number.isFinite(defaultDiscount) || defaultDiscount < 0 || defaultDiscount > 100) {
        setError('Default discount must be between 0 and 100')
        return
      }
      if (!Number.isFinite(loyalty) || loyalty <= 0) {
        setError('Loyalty spend per point must be greater than zero')
        return
      }
      saveMutation.mutate({
        currency: form.currency,
        tax_rate: taxRate,
        default_discount: defaultDiscount,
        loyalty_spend_per_point: loyalty,
      })
      return
    }

    if (section === 'capacity') {
      const shelf = numeric(form.shelf_capacity_max)
      const warehouse = numeric(form.warehouse_capacity_max)
      if (!Number.isInteger(shelf) || shelf <= 0 || !Number.isInteger(warehouse) || warehouse <= 0) {
        setError('Capacities must be whole numbers greater than zero')
        return
      }
      saveMutation.mutate({ shelf_capacity_max: shelf, warehouse_capacity_max: warehouse })
    }
  }

  if (storeQuery.isLoading) {
    return (
      <Card>
        <Spinner label="Loading settings…" />
      </Card>
    )
  }

  if (storeQuery.isError) {
    return (
      <Card>
        <ErrorState error={storeQuery.error} onRetry={storeQuery.refetch} />
      </Card>
    )
  }

  const readOnly = !isOwner

  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-wrap gap-1 border-b border-edge px-4 pt-3">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              className={`rounded-t-lg px-4 py-2.5 text-sm font-medium transition
                ${
                  tab === item.id
                    ? 'border-b-2 border-brand-500 text-brand-600'
                    : 'text-ink-muted hover:text-ink'
                }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        {readOnly ? (
          <p className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-5 py-3 text-sm text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
            <Lock className="h-4 w-4" />
            Signed in as a cashier — settings are read-only.
          </p>
        ) : null}

        {error ? (
          <p className="border-b border-rose-200 bg-rose-50 px-5 py-3 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300" role="alert">
            {error}
          </p>
        ) : null}

        <div className="p-5">
          {tab === 'general' ? (
            <div className="space-y-6">
              <section>
                <h2 className="text-base font-semibold text-ink">Appearance</h2>
                <p className="mt-1 text-sm text-ink-muted">
                  Applies to this device only — it is your preference, not a store setting, so a
                  cashier on the till can choose differently.
                </p>
                <div className="mt-4 inline-flex rounded-lg border border-edge-strong p-1">
                  {[
                    { value: 'light', label: 'Light', icon: Sun },
                    { value: 'dark', label: 'Dark', icon: Moon },
                    { value: 'system', label: 'System', icon: Monitor },
                  ].map(({ value, label, icon: Icon }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => choose(value)}
                      aria-pressed={preference === value}
                      className={`inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition
                        ${
                          preference === value
                            ? 'bg-brand-500 text-white'
                            : 'text-ink-muted hover:bg-surface-muted hover:text-ink'
                        }`}
                    >
                      <Icon className="h-4 w-4" />
                      {label}
                    </button>
                  ))}
                </div>
                {preference === 'system' ? (
                  <p className="mt-2 text-xs text-ink-faint">
                    Following your system setting — currently {resolved}.
                  </p>
                ) : null}
              </section>

              <section className="border-t border-edge pt-6">
                <h2 className="text-base font-semibold text-ink">Store Information</h2>
                <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <Field label="Name">
                    <input className="field-input" value={form.name} onChange={setValue('name')} disabled={readOnly} />
                  </Field>
                  <Field label="Tax ID">
                    <input className="field-input" value={form.tax_id} onChange={setValue('tax_id')} disabled={readOnly} />
                  </Field>
                  <Field label="Address" className="sm:col-span-2">
                    <input className="field-input" value={form.address} onChange={setValue('address')} disabled={readOnly} />
                  </Field>
                </div>
                {!readOnly ? (
                  <div className="mt-4 flex gap-2">
                    <Button loading={saveMutation.isPending} onClick={() => saveSection('store')}>
                      Save
                    </Button>
                    <Button variant="secondary" onClick={reset}>
                      Reset
                    </Button>
                  </div>
                ) : null}
              </section>

              <section className="border-t border-edge pt-6">
                <h2 className="text-base font-semibold text-ink">System Preferences</h2>
                <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
                  <Field label="Currency">
                    <select className="field-input" value={form.currency} onChange={setValue('currency')} disabled={readOnly}>
                      {CURRENCIES.map((code) => (
                        <option key={code} value={code}>
                          {code}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Tax rate (%)" hint="Applied to every sale at checkout">
                    <input
                      className="field-input"
                      type="number"
                      min="0"
                      max="100"
                      step="0.01"
                      value={form.tax_rate}
                      onChange={setValue('tax_rate')}
                      disabled={readOnly}
                    />
                  </Field>
                  <Field label="Default discount (%)" hint="Suggested discount for new products">
                    <input
                      className="field-input"
                      type="number"
                      min="0"
                      max="100"
                      step="0.01"
                      value={form.default_discount}
                      onChange={setValue('default_discount')}
                      disabled={readOnly}
                    />
                  </Field>
                  <Field label="Loyalty: spend per point" hint="Currency spent to earn one loyalty point">
                    <input
                      className="field-input"
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={form.loyalty_spend_per_point}
                      onChange={setValue('loyalty_spend_per_point')}
                      disabled={readOnly}
                    />
                  </Field>
                </div>
                {!readOnly ? (
                  <div className="mt-4 flex gap-2">
                    <Button loading={saveMutation.isPending} onClick={() => saveSection('preferences')}>
                      Save
                    </Button>
                    <Button variant="secondary" onClick={reset}>
                      Reset
                    </Button>
                  </div>
                ) : null}
              </section>
            </div>
          ) : null}

          {tab === 'store' ? (
            <section>
              <h2 className="text-base font-semibold text-ink">Storage Capacity</h2>
              <p className="mt-1 text-sm text-ink-muted">
                These maximums drive the capacity gauges on the dashboard.
              </p>
              <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="Shelf capacity (units)">
                  <input
                    className="field-input"
                    type="number"
                    min="1"
                    step="1"
                    value={form.shelf_capacity_max}
                    onChange={setValue('shelf_capacity_max')}
                    disabled={readOnly}
                  />
                </Field>
                <Field label="Warehouse capacity (units)">
                  <input
                    className="field-input"
                    type="number"
                    min="1"
                    step="1"
                    value={form.warehouse_capacity_max}
                    onChange={setValue('warehouse_capacity_max')}
                    disabled={readOnly}
                  />
                </Field>
              </div>
              {!readOnly ? (
                <div className="mt-4 flex gap-2">
                  <Button loading={saveMutation.isPending} onClick={() => saveSection('capacity')}>
                    Save
                  </Button>
                  <Button variant="secondary" onClick={reset}>
                    Reset
                  </Button>
                </div>
              ) : null}
            </section>
          ) : null}

          {tab === 'preferences' ? (
            <section>
              <h2 className="text-base font-semibold text-ink">User Roles</h2>
              <p className="mt-1 text-sm text-ink-muted">
                Two roles ship with the system. Owners manage the catalogue, settings and reports; cashiers run the POS.
              </p>
              <div className="mt-4 overflow-hidden rounded-lg border border-edge">
                <table className="min-w-full">
                  <thead className="bg-surface-muted">
                    <tr>
                      <th className="table-header">Capability</th>
                      <th className="table-header text-center">Owner</th>
                      <th className="table-header text-center">Cashier</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-edge">
                    {[
                      ['View dashboard', true, true],
                      ['Run the POS and complete sales', true, true],
                      ['View inventory', true, true],
                      ['Add / edit products and stock', true, false],
                      ['Reports & analytics', true, false],
                      ['Change store settings', true, false],
                    ].map(([capability, owner, cashier]) => (
                      <tr key={capability}>
                        <td className="table-cell">{capability}</td>
                        <td className="table-cell text-center">{owner ? '✓' : '—'}</td>
                        <td className="table-cell text-center">{cashier ? '✓' : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          {tab === 'account' ? <ProfilePanel /> : null}
        </div>
      </Card>
    </div>
  )
}
