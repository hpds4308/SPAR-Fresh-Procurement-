import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { PurchaseOrder, PurchaseOrderSummary, fetchMyPurchaseOrder, fetchMyPurchaseOrders } from "../../api/purchaseOrders";
import EmptyState from "../shared/EmptyState";
import { IconReceipt } from "../shared/Icons";
import { PoStatusBadge, PurchaseOrderViewer } from "../shared/PurchaseOrderDocument";
import { formatDateTime, formatLongDate } from "../shared/PriceSheetParts";
import { SkeletonTable } from "../shared/ui/Skeleton";

const card = "bg-white rounded-2xl shadow-card border border-sage-100";

export default function PurchaseOrders() {
  const [list, setList] = useState<PurchaseOrderSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);

  useEffect(() => {
    fetchMyPurchaseOrders()
      .then(setList)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load your purchase orders."));
  }, []);

  if (openId !== null) return <PurchaseOrderDetail id={openId} onBack={() => setOpenId(null)} />;

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
        description="When SPAR issues you a purchase order, it appears here to view and print."
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
                  Delivery {formatLongDate(po.delivery_date)} · {po.branch_count} branch
                  {po.branch_count === 1 ? "" : "es"} · issued {formatDateTime(po.issued_at)}
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

function PurchaseOrderDetail({ id, onBack }: { id: number; onBack: () => void }) {
  const [po, setPo] = useState<PurchaseOrder | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMyPurchaseOrder(id)
      .then(setPo)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load this purchase order."));
  }, [id]);

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
          <PurchaseOrderViewer po={po} />
        </div>
      )}
    </div>
  );
}
