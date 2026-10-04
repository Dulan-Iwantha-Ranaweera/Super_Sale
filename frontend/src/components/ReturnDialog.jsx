import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Undo2 } from 'lucide-react'
import { Badge, Button, ErrorState, Field, Modal, Spinner } from './ui'
import { useToast } from '../context/ToastContext'
import { api } from '../lib/api'
import { formatMoney } from '../lib/format'
import { round2 } from '../lib/money'

const REASONS = [
  'Damaged packaging',
  'Faulty product',
  'Wrong item picked',
  'Customer changed their mind',
  'Expired before use',
  'Duplicate purchase',
]

/**
 * Refund part or all of a sale.
 *
 * Quantities are capped at what is still returnable, and the refund preview
 * uses the tax rate the original sale was charged at — not the current store
 * setting — so the figure on screen matches what the server will pay back.
 */
export default function ReturnDialog({ sale, open, onClose, currency }) {
  const toast = useToast()
  const queryClient = useQueryClient()

  const [quantities, setQuantities] = useState({})
  const [reason, setReason] = useState(REASONS[0])
  const [restock, setRestock] = useState(true)
  const [refundMethod, setRefundMethod] = useState('CASH')
  const [error, setError] = useState(null)

  const returnableQuery = useQuery({
    queryKey: ['returnable', sale?.id],
    queryFn: () => api(`/api/sales/${sale.id}/returnable`),
    enabled: Boolean(open && sale?.id),
  })

  useEffect(() => {
    if (open) {
      setQuantities({})
      setReason(REASONS[0])
      setRestock(true)
      setRefundMethod('CASH')
      setError(null)
    }
  }, [open, sale?.id])

  // The sale's own tax rate, recovered from what it was charged.
  const taxRate = useMemo(() => {
    if (!sale) return 0
    const taxable = round2(sale.subtotal - sale.discount_total)
    return taxable > 0 ? (sale.tax_amount / taxable) * 100 : 0
  }, [sale])

  const lines = returnableQuery.data?.lines ?? []
  const preview = useMemo(() => {
    let net = 0
    lines.forEach((line) => {
      const quantity = Number(quantities[line.product_id]) || 0
      net = round2(net + line.refund_per_unit * quantity)
    })
    const tax = round2((net * taxRate) / 100)
    return { net, tax, total: round2(net + tax) }
  }, [lines, quantities, taxRate])

  const refundMutation = useMutation({
    mutationFn: (payload) => api(`/api/sales/${sale.id}/return`, { method: 'POST', body: payload }),
    onSuccess: (refund) => {
      queryClient.invalidateQueries({ queryKey: ['sales'] })
      queryClient.invalidateQueries({ queryKey: ['returnable'] })
      queryClient.invalidateQueries({ queryKey: ['products'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['reports'] })
      queryClient.invalidateQueries({ queryKey: ['customers'] })
      toast.success(`Refund ${refund.receipt_number} issued — ${formatMoney(Math.abs(refund.grand_total), currency)}`)
      onClose()
    },
    onError: (refundError) => setError(refundError.message),
  })

  const setQuantity = (line, value) => {
    const parsed = Math.max(0, Math.min(line.quantity_remaining, Math.trunc(Number(value) || 0)))
    setQuantities((previous) => ({ ...previous, [line.product_id]: parsed }))
    setError(null)
  }

  const selected = Object.entries(quantities).filter(([, quantity]) => quantity > 0)

  const submit = () => {
    setError(null)
    if (selected.length === 0) {
      setError('Choose at least one unit to refund')
      return
    }
    if (reason.trim().length < 3) {
      setError('Give a reason for the refund')
      return
    }
    refundMutation.mutate({
      items: selected.map(([product_id, quantity]) => ({ product_id, quantity })),
      reason: reason.trim(),
      restock,
      refund_method: refundMethod,
    })
  }

  return (
    <Modal
      open={open}
      title={`Refund against ${sale?.receipt_number ?? ''}`}
      onClose={onClose}
      width="max-w-2xl"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={refundMutation.isPending}
            disabled={selected.length === 0}
            onClick={submit}
          >
            <Undo2 className="h-4 w-4" />
            Refund {formatMoney(preview.total, currency)}
          </Button>
        </>
      }
    >
      {returnableQuery.isLoading ? (
        <Spinner label="Loading the original sale…" />
      ) : returnableQuery.isError ? (
        <ErrorState error={returnableQuery.error} onRetry={returnableQuery.refetch} />
      ) : (
        <div className="space-y-5">
          {returnableQuery.data?.fully_returned ? (
            <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
              Every item on this receipt has already been refunded.
            </p>
          ) : null}

          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-edge text-xs uppercase tracking-wide text-ink-muted">
                <th className="py-2 text-left">Item</th>
                <th className="py-2 text-right">Sold</th>
                <th className="py-2 text-right">Already back</th>
                <th className="py-2 text-right">Refund per unit</th>
                <th className="py-2 text-right">Return</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-edge">
              {lines.map((line) => (
                <tr key={line.product_id} className={line.quantity_remaining === 0 ? 'text-ink-faint' : ''}>
                  <td className="py-2">
                    {line.name}
                    {line.discount_percentage > 0 ? (
                      <span className="ml-1 text-xs text-amber-600">-{line.discount_percentage}%</span>
                    ) : null}
                  </td>
                  <td className="py-2 text-right">{line.quantity_sold}</td>
                  <td className="py-2 text-right">{line.quantity_returned || '—'}</td>
                  <td className="py-2 text-right">{formatMoney(line.refund_per_unit, currency)}</td>
                  <td className="py-2 text-right">
                    <input
                      type="number"
                      min="0"
                      max={line.quantity_remaining}
                      step="1"
                      disabled={line.quantity_remaining === 0}
                      value={quantities[line.product_id] ?? ''}
                      placeholder="0"
                      onChange={(event) => setQuantity(line, event.target.value)}
                      className="w-20 rounded border border-edge-strong px-2 py-1 text-right text-sm disabled:bg-surface-muted"
                      aria-label={`Units of ${line.name} to refund`}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Reason">
              <input
                className="field-input"
                list="refund-reasons"
                value={reason}
                onChange={(event) => {
                  setReason(event.target.value)
                  setError(null)
                }}
              />
              <datalist id="refund-reasons">
                {REASONS.map((option) => (
                  <option key={option} value={option} />
                ))}
              </datalist>
            </Field>
            <Field label="Refund method">
              <select
                className="field-input"
                value={refundMethod}
                onChange={(event) => setRefundMethod(event.target.value)}
              >
                <option value="CASH">Cash</option>
                <option value="CARD">Card</option>
              </select>
            </Field>
          </div>

          <label className="flex items-start gap-3 rounded-lg border border-edge p-3">
            <input
              type="checkbox"
              checked={restock}
              onChange={(event) => setRestock(event.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-edge-strong"
            />
            <span>
              <span className="block text-sm font-medium text-ink">Put the units back on the shelf</span>
              <span className="block text-xs text-ink-muted">
                Leave this off for damaged or spoiled goods — the refund still goes through, the stock does not
                come back.
              </span>
            </span>
          </label>

          <dl className="space-y-1 rounded-lg bg-surface-muted p-4 text-sm">
            <div className="flex justify-between text-ink-muted">
              <dt>Goods</dt>
              <dd>{formatMoney(preview.net, currency)}</dd>
            </div>
            <div className="flex justify-between text-ink-muted">
              <dt>Tax returned ({taxRate.toFixed(0)}%)</dt>
              <dd>{formatMoney(preview.tax, currency)}</dd>
            </div>
            <div className="flex justify-between border-t border-edge pt-1 text-base font-semibold text-rose-700">
              <dt>Total refund</dt>
              <dd>{formatMoney(preview.total, currency)}</dd>
            </div>
          </dl>

          {sale?.customer_name ? (
            <p className="text-xs text-ink-muted">
              <Badge tone="blue">{sale.customer_name}</Badge> — their spend and loyalty points are reduced by this
              refund.
            </p>
          ) : null}

          {error ? (
            <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300" role="alert">
              {error}
            </p>
          ) : null}
        </div>
      )}
    </Modal>
  )
}
