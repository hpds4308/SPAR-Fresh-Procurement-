import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { PurchaseOrder, PurchaseOrderSummary } from "../../api/purchaseOrders";
import EmptyState from "./EmptyState";
import { IconReceipt } from "./Icons";
import { PoStatusBadge, PurchaseOrderViewer } from "./PurchaseOrderDocument";
import { formatDateTime, formatLongDate } from "./PriceSheetParts";
import { SkeletonTable } from "./ui/Skeleton";

const card = "bg-white rounded-2xl shadow-card border border-sage-100";

/**
 * A supplier's or a branch's list of purchase orders, click-through to the
 * printable PO. Branches get their own branch PO only (the API has already
 * cut each PO down to their lines), so the view picker is hidden for them.
 */
export default function PurchaseOrderList({
  fetchList,
  fetchOne,
  branchView = false,
}: {
  fetchList: () => Promise<PurchaseOrderSummary[]>;
  fetchOne: (id: number) => Promise<PurchaseOrder>;
  branchView?: boolean;
}) {
  const [list, setList] = useState<PurchaseOrderSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);

  useEffect(() => {
    fetchList()
      .then(setList)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load your purchase orders."));
  }, [fetchList]);

  if (openId !== null) {
    return <PurchaseOrderDetail id={openId} fetchOne={fetchOne} branchView={branchView} onBack={() => setOpenId(null)} />;
  }

  if (error) {
    return <div className="rounded-2xl bg-tomato-500/10 border border-tomato-500/25 p-4 text-tomato-600 text-sm">{error}</div>;
  }
  if (!list) {
    return (
      <div className={`${card} overflow-hidden`}>
        <SkeletonTable rows={5} columns={4} />
      </div>
    );
  }
  if (list.length === 0) {
    return (
      <EmptyState
        icon={<IconReceipt width={20} height={20} />}
        title="No purchase orders yet"
        description={
          branchView
            ? "When SPAR issues a purchase order to a supplier for your branch, it appears here to check deliveries against."
            : "When SPAR issues you a purchase order, it appears here to view and print."
        }
      />
    );
  }

  return (
    <div className={`${card} overflow-hidden`}>
      <ul className="divide-y divide-sage-100">
        {list.map((po) => (
          <li key={po.id}>
            <button
              onClick={() => setOpenId(po.id)}
              className="w-full text-left px-5 py-3.5 flex flex-wrap items-center gap-x-4 gap-y-1 hover:bg-sage-50/50 transition-colors duration-100"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-crate-950">
                  <span className="font-mono">{po.po_number}</span>
                  {po.revision > 1 && <span className="text-crate-800/45 font-normal"> · revision {po.revision}</span>}
                </p>
                <p className="text-xs text-crate-800/45 mt-0.5">
                  {branchView ? `${po.supplier_name} · ` : ""}Delivery {formatLongDate(po.delivery_date)}
                  {branchView ? "" : ` · ${po.branch_count} branch${po.branch_count === 1 ? "" : "es"}`} · issued{" "}
                  {formatDateTime(po.issued_at)}
                </p>
              </div>
              <span className="text-sm font-semibold text-crate-950 tabular-nums">Rs. {po.total_amount.toFixed(2)}</span>
              <PoStatusBadge status={po.status} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function PurchaseOrderDetail({
  id,
  fetchOne,
  branchView,
  onBack,
}: {
  id: number;
  fetchOne: (id: number) => Promise<PurchaseOrder>;
  branchView: boolean;
  onBack: () => void;
}) {
  const [po, setPo] = useState<PurchaseOrder | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchOne(id)
      .then(setPo)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load this purchase order."));
  }, [id, fetchOne]);

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
        <div className={`${card} p-5 sm:p-6`}>
          <PurchaseOrderViewer po={po} branchOnly={branchView} />
        </div>
      )}
    </div>
  );
}
