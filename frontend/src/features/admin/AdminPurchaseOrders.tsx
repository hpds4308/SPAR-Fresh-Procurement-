import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import {
  PurchaseOrder,
  PurchaseOrderAdminRow,
  cancelPurchaseOrder,
  fetchAdminPurchaseOrder,
  fetchAdminPurchaseOrders,
  fetchPurchaseOrderDates,
  issuePurchaseOrder,
} from "../../api/purchaseOrders";
import EmptyState from "../shared/EmptyState";
import { IconChevronLeft, IconChevronRight, IconReceipt } from "../shared/Icons";
import { PoStatusBadge, PurchaseOrderViewer } from "../shared/PurchaseOrderDocument";
import { formatLongDate } from "../shared/PriceSheetParts";
import { StatusBadge } from "../shared/ui/Badge";
import Button from "../shared/ui/Button";
import { ConfirmDialog } from "../shared/ui/Modal";
import { SkeletonTable } from "../shared/ui/Skeleton";

const card = "bg-white rounded-2xl shadow-card border border-sage-100";

/** Set by the Supplier Orders builder after issuing a PO, to open it here. */
export type PoFocus = { deliveryDate: string; poId: number; nonce: number };

export default function AdminPurchaseOrders({ focus }: { focus?: PoFocus | null }) {
  const [dates, setDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [rows, setRows] = useState<PurchaseOrderAdminRow[]>([]);
  const [datesLoading, setDatesLoading] = useState(true);
  const [rowsLoading, setRowsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busySupplierId, setBusySupplierId] = useState<number | null>(null);
  const [openPoId, setOpenPoId] = useState<number | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    fetchPurchaseOrderDates()
      .then((d) => {
        setDates(d);
        setSelectedDate((cur) => cur ?? d[0] ?? null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load purchase order dates."))
      .finally(() => setDatesLoading(false));
  }, [reloadKey]);

  useEffect(() => {
    if (!focus) return;
    setDates((prev) => (prev.includes(focus.deliveryDate) ? prev : [...prev, focus.deliveryDate].sort().reverse()));
    setSelectedDate(focus.deliveryDate);
    setOpenPoId(focus.poId);
    setReloadKey((k) => k + 1);
  }, [focus]);

  useEffect(() => {
    if (!selectedDate) return;
    let cancelled = false;
    setRowsLoading(true);
    fetchAdminPurchaseOrders(selectedDate)
      .then((data) => {
        if (cancelled) return;
        setRows(data);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load purchase orders.");
      })
      .finally(() => {
        if (!cancelled) setRowsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedDate, reloadKey]);

  const dateIndex = useMemo(() => (selectedDate ? dates.indexOf(selectedDate) : -1), [dates, selectedDate]);
  const hasPrevDay = dateIndex >= 0 && dateIndex < dates.length - 1; // dates sorted desc
  const hasNextDay = dateIndex > 0;

  async function issue(row: PurchaseOrderAdminRow) {
    setBusySupplierId(row.supplier_id);
    setError(null);
    try {
      const po = await issuePurchaseOrder(row.supplier_id, row.delivery_date);
      setOpenPoId(po.id);
      setReloadKey((k) => k + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not issue the purchase order.");
    } finally {
      setBusySupplierId(null);
    }
  }

  if (openPoId !== null) {
    return (
      <PurchaseOrderDetail
        id={openPoId}
        onBack={() => {
          setOpenPoId(null);
          setReloadKey((k) => k + 1);
        }}
      />
    );
  }

  if (datesLoading) {
    return (
      <div className={`${card} overflow-hidden`}>
        <SkeletonTable rows={5} columns={4} />
      </div>
    );
  }

  if (dates.length === 0) {
    return (
      <EmptyState
        icon={<IconReceipt width={20} height={20} />}
        title="No supplier orders yet"
        description="Build and save an order for a supplier on Supplier Orders, then issue its purchase order here."
      />
    );
  }

  const issuedCount = rows.filter((r) => r.purchase_order?.status === "ISSUED").length;

  return (
    <div className="space-y-4">
      <div className={`${card} p-4 flex flex-wrap items-center gap-3`}>
        <button
          onClick={() => hasPrevDay && setSelectedDate(dates[dateIndex + 1])}
          disabled={!hasPrevDay}
          className="w-8 h-8 flex items-center justify-center rounded-full border border-sage-300 text-crate-800/60 hover:bg-sage-50 disabled:opacity-30 disabled:hover:bg-transparent transition-colors duration-150"
          aria-label="Previous delivery date"
        >
          <IconChevronLeft width={14} height={14} />
        </button>
        <button
          onClick={() => hasNextDay && setSelectedDate(dates[dateIndex - 1])}
          disabled={!hasNextDay}
          className="w-8 h-8 flex items-center justify-center rounded-full border border-sage-300 text-crate-800/60 hover:bg-sage-50 disabled:opacity-30 disabled:hover:bg-transparent transition-colors duration-150"
          aria-label="Next delivery date"
        >
          <IconChevronRight width={14} height={14} />
        </button>
        <select
          value={selectedDate ?? ""}
          onChange={(e) => setSelectedDate(e.target.value)}
          className="border border-sage-300 bg-sage-50/60 rounded-full px-4 py-1.5 text-sm text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
        >
          {dates.map((d) => (
            <option key={d} value={d}>
              Delivery {formatLongDate(d)}
            </option>
          ))}
        </select>
        <span className="text-xs text-crate-800/40 ml-auto">
          {issuedCount} of {rows.length} supplier{rows.length === 1 ? "" : "s"} issued
        </span>
      </div>

      {error && <div className="rounded-2xl bg-tomato-500/10 border border-tomato-500/25 p-4 text-tomato-600 text-sm">{error}</div>}

      <div className={`${card} overflow-hidden`}>
        {rowsLoading ? (
          <SkeletonTable rows={5} columns={4} />
        ) : rows.length === 0 ? (
          <p className="text-sm text-crate-800/40 text-center py-10">No supplier orders for this delivery date.</p>
        ) : (
          <ul className="divide-y divide-sage-100">
            {rows.map((row) => {
              const po = row.purchase_order;
              const busy = busySupplierId === row.supplier_id;
              const canIssue = row.line_count > 0 && row.unpriced_line_count === 0;
              return (
                <li key={row.supplier_id} className="px-5 py-3.5 flex flex-wrap items-center gap-x-4 gap-y-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-crate-950 truncate">{row.supplier_name}</p>
                    <p className="text-xs text-crate-800/45 mt-0.5">
                      {row.line_count > 0
                        ? `${row.line_count} line${row.line_count === 1 ? "" : "s"} · Rs. ${row.order_total.toFixed(2)}`
                        : "Order has been emptied since the PO was issued"}
                      {po && (
                        <>
                          {" · "}
                          <span className="font-mono">{po.po_number}</span> rev {po.revision}
                        </>
                      )}
                    </p>
                    {row.unpriced_line_count > 0 && (
                      <p className="text-xs text-mango-700 mt-0.5">
                        {row.unpriced_line_count} line{row.unpriced_line_count === 1 ? " has" : "s have"} no price — set an
                        agreed price on Supplier Orders first.
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    {!po ? (
                      <StatusBadge tone="neutral">Not issued</StatusBadge>
                    ) : row.is_outdated ? (
                      <StatusBadge tone="warning">Order changed since issued</StatusBadge>
                    ) : (
                      <PoStatusBadge status={po.status} />
                    )}
                    {po && (
                      <Button variant="secondary" size="sm" onClick={() => setOpenPoId(po.id)}>
                        View
                      </Button>
                    )}
                    {(!po || po.status === "CANCELLED" || row.is_outdated) && (
                      <Button size="sm" loading={busy} disabled={!canIssue || busy} onClick={() => issue(row)}>
                        {!po ? "Issue PO" : "Re-issue PO"}
                      </Button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

function PurchaseOrderDetail({ id, onBack }: { id: number; onBack: () => void }) {
  const [po, setPo] = useState<PurchaseOrder | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setPo(null);
    fetchAdminPurchaseOrder(id)
      .then(setPo)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load this purchase order."));
  }, [id]);

  async function reissue() {
    if (!po) return;
    setBusy(true);
    setError(null);
    try {
      setPo(await issuePurchaseOrder(po.supplier_id, po.delivery_date));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not re-issue the purchase order.");
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    setBusy(true);
    try {
      setPo(await cancelPurchaseOrder(id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not cancel the purchase order.");
    } finally {
      setBusy(false);
      setConfirmCancel(false);
    }
  }

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="no-print text-sm font-semibold text-crate-700 hover:underline">
        ← All purchase orders
      </button>
      {error && <div className="rounded-2xl bg-tomato-500/10 border border-tomato-500/25 p-4 text-tomato-600 text-sm">{error}</div>}
      {!po && !error && (
        <div className={`${card} overflow-hidden`}>
          <SkeletonTable rows={6} columns={5} />
        </div>
      )}
      {po && (
        <>
          {po.is_outdated && (
            <div className="no-print rounded-2xl bg-mango-500/15 border border-mango-500/30 px-4 py-3 text-sm text-[#8A5A0D] flex flex-wrap items-center gap-3">
              <span className="flex-1 min-w-[14rem]">
                This supplier's order was changed on Supplier Orders after this PO was issued. Re-issue it so the
                supplier gets the current quantities and prices.
              </span>
              <Button size="sm" loading={busy} onClick={reissue}>
                Re-issue as revision {po.revision + 1}
              </Button>
            </div>
          )}
          <div className={`${card} p-5 sm:p-6 space-y-4`}>
            <div className="no-print flex items-center gap-3">
              <PoStatusBadge status={po.status} />
              <span className="text-xs text-crate-800/45">
                {po.status === "ISSUED"
                  ? `${po.supplier_name} can see this on their Purchase Orders page.`
                  : "The supplier sees this PO marked as cancelled."}
              </span>
            </div>
            <PurchaseOrderViewer
              po={po}
              actions={
                po.status === "ISSUED" ? (
                  <Button variant="danger" size="sm" onClick={() => setConfirmCancel(true)}>
                    Cancel PO
                  </Button>
                ) : (
                  <Button size="sm" loading={busy} onClick={reissue}>
                    Re-issue PO
                  </Button>
                )
              }
            />
          </div>
        </>
      )}
      <ConfirmDialog
        open={confirmCancel}
        onClose={() => setConfirmCancel(false)}
        onConfirm={cancel}
        loading={busy}
        title="Cancel this purchase order?"
        description="The supplier will see it marked as cancelled. You can re-issue it later from the current order."
        confirmLabel="Cancel PO"
        danger
      />
    </div>
  );
}
