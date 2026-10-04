import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Search, UserPlus, Users } from 'lucide-react'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  Field,
  Modal,
  Pagination,
  SortableHeader,
  Spinner,
} from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { useCurrency } from '../hooks/useStoreSettings'
import { api, buildQuery } from '../lib/api'
import { formatDate, formatMoney, formatNumber } from '../lib/format'

const PAGE_SIZE = 12

const SEGMENTS = [
  { value: 'ALL', label: 'All customers' },
  { value: 'HIGH_SPENDING', label: 'For high-spending customers' },
  { value: 'FREQUENT_VISITORS', label: 'Frequent visitors (10+ visits)' },
  { value: 'LOYALTY_REWARDS', label: 'Loyalty rewards ready (100+ pts)' },
  { value: 'CREDIT_DUE', label: 'With outstanding credit' },
]

const EMPTY_FORM = { name: '', phone: '', email: '', credit_due: '0' }

export default function Customers() {
  const currency = useCurrency()
  const toast = useToast()
  const queryClient = useQueryClient()
  const { isOwner } = useAuth()

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [segment, setSegment] = useState('ALL')
  const [sortBy, setSortBy] = useState('total_spend')
  const [sortDir, setSortDir] = useState('desc')
  const [page, setPage] = useState(1)
  const [dialog, setDialog] = useState(null) // { mode: 'create' | 'edit', customer }
  const [form, setForm] = useState(EMPTY_FORM)
  const [formError, setFormError] = useState(null)

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    setPage(1)
  }, [debouncedSearch, segment, sortBy, sortDir])

  const queryString = useMemo(
    () =>
      buildQuery({
        search: debouncedSearch,
        segment,
        sort_by: sortBy,
        sort_dir: sortDir,
        page,
        page_size: PAGE_SIZE,
      }),
    [debouncedSearch, segment, sortBy, sortDir, page],
  )

  const customersQuery = useQuery({
    queryKey: ['customers', queryString],
    queryFn: () => api(`/api/customers${queryString}`),
    placeholderData: (previous) => previous,
  })

  const saveMutation = useMutation({
    mutationFn: ({ mode, id, payload }) =>
      mode === 'create'
        ? api('/api/customers', { method: 'POST', body: payload })
        : api(`/api/customers/${id}`, { method: 'PUT', body: payload }),
    onSuccess: (customer, variables) => {
      queryClient.invalidateQueries({ queryKey: ['customers'] })
      toast.success(variables.mode === 'create' ? `${customer.name} added` : `${customer.name} updated`)
      setDialog(null)
    },
    onError: (error) => setFormError(error.message),
  })

  const onSort = (field) => {
    if (sortBy === field) setSortDir((previous) => (previous === 'asc' ? 'desc' : 'asc'))
    else {
      setSortBy(field)
      setSortDir('desc')
    }
  }

  const openCreate = () => {
    setForm(EMPTY_FORM)
    setFormError(null)
    setDialog({ mode: 'create' })
  }

  const openEdit = (customer) => {
    setForm({
      name: customer.name,
      phone: customer.phone,
      email: customer.email ?? '',
      credit_due: String(customer.credit_due ?? 0),
    })
    setFormError(null)
    setDialog({ mode: 'edit', customer })
  }

  const submitForm = () => {
    setFormError(null)
    if (!form.name.trim()) {
      setFormError('Name is required')
      return
    }
    if (form.phone.trim().length < 3) {
      setFormError('Enter a valid mobile number')
      return
    }
    const creditDue = Number(form.credit_due)
    if (!Number.isFinite(creditDue) || creditDue < 0) {
      setFormError('Credit due must be zero or more')
      return
    }
    const payload = {
      name: form.name.trim(),
      phone: form.phone.trim(),
      email: form.email.trim() || null,
      credit_due: creditDue,
    }
    saveMutation.mutate({ mode: dialog.mode, id: dialog.customer?.id, payload })
  }

  const data = customersQuery.data
  const items = data?.items ?? []

  return (
    <Card>
      <CardHeader
        title="CRM"
        subtitle="Registered shoppers, their spend and loyalty balance"
        action={
          <Button onClick={openCreate}>
            <UserPlus className="h-4 w-4" />
            Add customer
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-3 px-5 pb-4 pt-4">
        <select
          className="field-input w-auto min-w-[260px]"
          value={segment}
          onChange={(event) => setSegment(event.target.value)}
          aria-label="Customer segment"
        >
          {SEGMENTS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <div className="relative ml-auto min-w-[220px]">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
          <input
            className="field-input pl-9"
            placeholder="Search name or mobile…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            aria-label="Search customers"
          />
        </div>
      </div>

      <div className="overflow-x-auto scroll-slim">
        {customersQuery.isLoading ? (
          <Spinner label="Loading customers…" />
        ) : customersQuery.isError ? (
          <ErrorState error={customersQuery.error} onRetry={customersQuery.refetch} />
        ) : items.length === 0 ? (
          <EmptyState
            icon={Users}
            title="No customers in this segment"
            description="Switch the segment filter or add a new shopper."
            action={<Button onClick={openCreate}>Add customer</Button>}
          />
        ) : (
          <table className="min-w-full">
            <thead className="border-y border-edge bg-surface-muted">
              <tr>
                <SortableHeader field="name" label="Name" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                <SortableHeader field="phone" label="Mobile" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                <SortableHeader
                  field="total_visits"
                  label="Total Visits"
                  sortBy={sortBy}
                  sortDir={sortDir}
                  onSort={onSort}
                  align="right"
                />
                <SortableHeader
                  field="total_spend"
                  label="Total Spend"
                  sortBy={sortBy}
                  sortDir={sortDir}
                  onSort={onSort}
                  align="right"
                />
                <SortableHeader
                  field="loyalty_points"
                  label="Loyalty Points"
                  sortBy={sortBy}
                  sortDir={sortDir}
                  onSort={onSort}
                  align="right"
                />
                <SortableHeader
                  field="credit_due"
                  label="Credit Due"
                  sortBy={sortBy}
                  sortDir={sortDir}
                  onSort={onSort}
                  align="right"
                />
                <th className="table-header">Last Visit</th>
                {isOwner ? <th className="table-header text-right">Actions</th> : null}
              </tr>
            </thead>
            <tbody className="divide-y divide-edge">
              {items.map((customer) => (
                <tr key={customer.id} className="hover:bg-surface-muted">
                  <td className="table-cell">
                    <span className="flex items-center gap-2">
                      <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-50 text-xs font-semibold text-brand-700">
                        {customer.name
                          .split(' ')
                          .map((part) => part[0])
                          .slice(0, 2)
                          .join('')
                          .toUpperCase()}
                      </span>
                      <span className="font-medium text-ink">{customer.name}</span>
                    </span>
                  </td>
                  <td className="table-cell font-mono text-xs text-ink-muted">{customer.phone}</td>
                  <td className="table-cell text-right">{formatNumber(customer.total_visits)}</td>
                  <td className="table-cell text-right font-medium">{formatMoney(customer.total_spend, currency)}</td>
                  <td className="table-cell text-right">
                    <Badge tone={customer.loyalty_points >= 100 ? 'green' : 'slate'}>
                      {formatNumber(customer.loyalty_points)}
                    </Badge>
                  </td>
                  <td
                    className={`table-cell text-right ${customer.credit_due > 0 ? 'font-medium text-rose-600' : 'text-ink-faint'}`}
                  >
                    {formatMoney(customer.credit_due, currency)}
                  </td>
                  <td className="table-cell text-ink-muted">{formatDate(customer.last_visit)}</td>
                  {isOwner ? (
                    <td className="table-cell text-right">
                      <Button variant="ghost" size="sm" onClick={() => openEdit(customer)} title="Edit customer">
                        <Pencil className="h-4 w-4" />
                      </Button>
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

      <Modal
        open={Boolean(dialog)}
        title={dialog?.mode === 'edit' ? `Edit ${dialog.customer.name}` : 'Add customer'}
        onClose={() => setDialog(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button loading={saveMutation.isPending} onClick={submitForm}>
              {dialog?.mode === 'edit' ? 'Save changes' : 'Create customer'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Full name">
            <input
              className="field-input"
              value={form.name}
              onChange={(event) => setForm((previous) => ({ ...previous, name: event.target.value }))}
              autoFocus
            />
          </Field>
          <Field label="Mobile number">
            <input
              className="field-input"
              value={form.phone}
              onChange={(event) => setForm((previous) => ({ ...previous, phone: event.target.value }))}
            />
          </Field>
          <Field label="Email (optional)">
            <input
              className="field-input"
              type="email"
              value={form.email}
              onChange={(event) => setForm((previous) => ({ ...previous, email: event.target.value }))}
            />
          </Field>
          <Field label={`Credit due (${currency})`} hint="Outstanding balance carried by this customer">
            <input
              className="field-input"
              type="number"
              min="0"
              step="0.01"
              value={form.credit_due}
              onChange={(event) => setForm((previous) => ({ ...previous, credit_due: event.target.value }))}
            />
          </Field>
          {formError ? (
            <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300" role="alert">
              {formError}
            </p>
          ) : null}
        </div>
      </Modal>
    </Card>
  )
}
