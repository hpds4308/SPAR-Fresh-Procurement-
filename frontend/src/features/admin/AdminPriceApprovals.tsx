import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import {
  PriceSheet,
  PriceSheetSummary,
  SheetStatus,
  fetchAdminSheet,
  fetchAdminSheets,
  withdrawSheet,
} from "../../api/priceApprovals";
import { Supplier, fetchSuppliers } from "../../api/suppliers";
import EmptyState from "../shared/EmptyState";
import { IconShield } from "../shared/Icons";
import {
  PriceSheetDocument,
  SheetStatusBadge,
  formatDateTime,
  formatLongDate,
  formatSignDeadline,
} from "../shared/PriceSheetParts";
import Button from "../shared/ui/Button";
import { ConfirmDialog } from "../shared/ui/Modal";
import { SkeletonTable } from "../shared/ui/Skeleton";

const card = "bg-white rounded-2xl shadow-card border border-sage-100";
const select =
  "border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150";

const STATUS_FILTERS: { value: SheetStatus | ""; label: string }[] = [
  { value: "", label: "All" },
  { value: "PENDING", label: "Awaiting signature" },
  { value: "APPROVED", label: "Approved" },
  { value: "REJECTED", label: "Rejected" },
  { value: "EXPIRED", label: "Expired" },
  { value: "VOIDED", label: "Cancelled" },
  { value: "WITHDRAWN", label: "Withdrawn" },
];

export default function AdminPriceApprovals({ onChanged }: { onChanged?: () => void }) {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [supplierId, setSupplierId] = useState<number | "">("");
  const [status, setStatus] = useState<SheetStatus | "">("");
  const [sheets, setSheets] = useState<PriceSheetSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    fetchSuppliers().then(setSuppliers).catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchAdminSheets({ supplierId: supplierId || undefined, status: status || undefined })
      .then((data) => {
        if (cancelled) return;
        setSheets(data);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load price sheets.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [supplierId, status, reloadKey]);

  if (openId !== null) {
    return (
      <AdminSheetDetail
        id={openId}
        onBack={() => {
          setOpenId(null);
          setReloadKey((k) => k + 1);
        }}
        onChanged={onChanged}
      />
    );
  }

  return (
    <div className="space-y-5">
      <div className={`${card} p-5`}>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-xs font-semibold text-crate-800/50 uppercase tracking-wide mb-1.5">Status</label>
            <select value={status} onChange={(e) => setStatus(e.target.value as SheetStatus | "")} className={select}>
              {STATUS_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-crate-800/50 uppercase tracking-wide mb-1.5">Supplier</label>
            <select
              value={supplierId}
              onChange={(e) => setSupplierId(e.target.value ? Number(e.target.value) : "")}
              className={`${select} min-w-[12rem]`}
            >
              <option value="">All suppliers</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.supplier_name}
                </option>
              ))}
            </select>
          </div>
        </div>
        <p className="text-xs text-crate-800/40 mt-3">
          Every price sheet sent to a supplier from Supplier Prices, with their signed approval or rejection.
        </p>
      </div>

      <div className={`${card} overflow-x-auto`}>
        {loading ? (
          <SkeletonTable rows={6} columns={6} />
        ) : error ? (
          <div className="p-6 text-tomato-600 text-sm">{error}</div>
        ) : sheets.length === 0 ? (
          <EmptyState
            icon={<IconShield width={20} height={20} />}
            title="No price sheets"
            description="Send adjusted prices for approval from the Supplier Prices page."
          />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-crate-800/40 text-left text-xs uppercase tracking-wide border-b border-sage-100">
                <th className="px-4 py-2.5 font-medium">Supplier</th>
                <th className="px-4 py-2.5 font-medium">Delivery</th>
                <th className="px-4 py-2.5 font-medium text-right">Items</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">Sent</th>
                <th className="px-4 py-2.5 font-medium">Response</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-sage-100">
              {sheets.map((s) => (
                <tr key={s.id}>
                  <td className="px-4 py-2.5 text-crate-950">{s.supplier_name}</td>
                  <td className="px-4 py-2.5 text-crate-800/80 whitespace-nowrap">{formatLongDate(s.delivery_date)}</td>
                  <td className="px-4 py-2.5 text-right text-crate-800/70">{s.item_count}</td>
                  <td className="px-4 py-2.5">
                    <SheetStatusBadge status={s.status} />
                  </td>
                  <td className="px-4 py-2.5 text-crate-800/60 whitespace-nowrap">{formatDateTime(s.sent_at)}</td>
                  <td className="px-4 py-2.5 text-crate-800/70 min-w-[10rem] max-w-[18rem]">
                    {s.status === "APPROVED" ? (
                      <>Signed by {s.signer_name}</>
                    ) : s.status === "REJECTED" ? (
                      <span className="text-tomato-600 line-clamp-2" title={s.rejection_reason ?? undefined}>
                        {s.rejection_reason}
                      </span>
                    ) : s.status === "VOIDED" || s.status === "WITHDRAWN" ? (
                      <span className="text-crate-800/40 line-clamp-2">{s.closed_reason}</span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <button onClick={() => setOpenId(s.id)} className="text-xs font-semibold text-crate-700 hover:underline">
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function AdminSheetDetail({ id, onBack, onChanged }: { id: number; onBack: () => void; onChanged?: () => void }) {
  const [sheet, setSheet] = useState<PriceSheet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmWithdraw, setConfirmWithdraw] = useState(false);
  const [withdrawing, setWithdrawing] = useState(false);

  useEffect(() => {
    fetchAdminSheet(id)
      .then(setSheet)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load this price sheet."));
  }, [id]);

  async function withdraw() {
    setWithdrawing(true);
    try {
      setSheet(await withdrawSheet(id));
      onChanged?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not withdraw this sheet.");
    } finally {
      setWithdrawing(false);
      setConfirmWithdraw(false);
    }
  }

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="no-print text-sm font-semibold text-crate-700 hover:underline">
        ← All price sheets
      </button>
      {error && <div className="rounded-2xl bg-tomato-500/10 border border-tomato-500/25 p-4 text-tomato-600 text-sm">{error}</div>}
      {!sheet && !error && (
        <div className={`${card} overflow-hidden`}>
          <SkeletonTable rows={5} columns={5} />
        </div>
      )}
      {sheet && (
        <div className={`${card} p-5 sm:p-6 space-y-4`}>
          <div className="no-print flex flex-wrap items-center gap-3 justify-between">
            <SheetStatusBadge status={sheet.status} />
            <div className="flex gap-2">
              {sheet.status === "PENDING" && (
                <Button variant="danger" size="sm" onClick={() => setConfirmWithdraw(true)}>
                  Withdraw
                </Button>
              )}
              {sheet.status === "APPROVED" && (
                <Button variant="secondary" size="sm" onClick={() => window.print()}>
                  Print / Save as PDF
                </Button>
              )}
            </div>
          </div>
          <PriceSheetDocument sheet={sheet} priceLabel="Supplier price" />
          {sheet.status === "REJECTED" && (
            <p className="text-sm bg-tomato-500/10 text-tomato-600 rounded-xl px-4 py-3">
              Rejected by {sheet.responded_by_name ?? "the supplier"}
              {sheet.responded_at ? ` on ${formatDateTime(sheet.responded_at)}` : ""}: “{sheet.rejection_reason}”. Adjust
              the prices on Supplier Prices and send again, or send as-is after agreeing by phone.
            </p>
          )}
          {sheet.status === "PENDING" && (
            <p className="text-sm text-crate-800/70 bg-sage-50 rounded-xl px-4 py-3">
              Waiting for the supplier. If they don't respond by {formatSignDeadline(sheet.delivery_date)}, their own
              quoted prices apply.
            </p>
          )}
          {sheet.status === "EXPIRED" && (
            <p className="text-sm text-crate-800/70 bg-sage-50 rounded-xl px-4 py-3">
              The supplier didn't respond before delivery, so their own quoted prices applied.
            </p>
          )}
          {(sheet.status === "VOIDED" || sheet.status === "WITHDRAWN") && sheet.closed_reason && (
            <p className="text-sm text-crate-800/70 bg-sage-50 rounded-xl px-4 py-3">{sheet.closed_reason}</p>
          )}
        </div>
      )}
      <ConfirmDialog
        open={confirmWithdraw}
        onClose={() => setConfirmWithdraw(false)}
        onConfirm={withdraw}
        loading={withdrawing}
        title="Withdraw this price sheet?"
        description="The supplier will no longer be able to sign it, and its prices go back to draft on Supplier Prices."
        confirmLabel="Withdraw"
        danger
      />
    </div>
  );
}
