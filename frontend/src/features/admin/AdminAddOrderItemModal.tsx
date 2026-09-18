import { useState } from "react";
import { ApiError } from "../../api/client";
import { adminAddOrderLine, adminRemoveOrderLine } from "../../api/orders";
import { useToast } from "../shared/ui/Toast";

export default function AdminAddOrderItemModal({
  branchId,
  branchName,
  productId,
  productDescription,
  unitCode,
  deliveryDate,
  currentQuantity,
  hasExistingOrderForDate,
  onClose,
  onSaved,
}: {
  branchId: number;
  branchName: string;
  productId: number;
  productDescription: string;
  unitCode: string;
  deliveryDate: string;
  currentQuantity: number | null;
  // Whether this branch already has ANY item ordered for this delivery
  // date (not just this product) — i.e. saving will append to a real,
  // existing order. False means there's nothing at all for this branch on
  // this date yet, so saving creates a brand-new order containing only
  // this one item — easy to do by mistake if the wrong date is selected,
  // so that path needs an explicit confirmation, not a silent success.
  hasExistingOrderForDate: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { show } = useToast();
  const [quantity, setQuantity] = useState(currentQuantity !== null ? String(currentQuantity) : "");
  const [confirmNewOrder, setConfirmNewOrder] = useState(false);
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRemove() {
    setError(null);
    setRemoving(true);
    try {
      await adminRemoveOrderLine({ branch_id: branchId, product_id: productId, delivery_date: deliveryDate });
      onSaved();
      onClose();
      show("success", `${productDescription} removed from ${branchName}'s order for delivery ${deliveryDate}.`);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not remove this item — it may have been submitted by the branch itself."
      );
    } finally {
      setRemoving(false);
    }
  }

  async function handleSave() {
    const parsed = parseFloat(quantity);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setError("Enter a quantity greater than zero.");
      return;
    }
    if (!hasExistingOrderForDate && !confirmNewOrder) {
      setError("Please confirm above before creating a new order for this branch.");
      return;
    }
    setError(null);
    setSaving(true);
    try {
      await adminAddOrderLine({ branch_id: branchId, product_id: productId, delivery_date: deliveryDate, quantity: parsed });
      onSaved();
      onClose();
      show("success", `${productDescription} added to ${branchName}'s order for delivery ${deliveryDate}.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add this item.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-crate-950/40 backdrop-blur-sm flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div
        className="bg-white rounded-[1.75rem] shadow-[0_30px_60px_-15px_rgba(21,56,38,0.35)] w-full max-w-sm"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-5 border-b border-sage-100 flex items-start justify-between">
          <div>
            <p className="text-xs text-crate-800/40">{branchName}</p>
            <h3 className="text-base font-display font-bold text-crate-950">{productDescription}</h3>
            <p className="text-sm text-crate-800/60 mt-1">for delivery {deliveryDate}</p>
          </div>
          <button
            onClick={onClose}
            className="text-crate-800/40 hover:text-crate-800 text-sm rounded-full w-7 h-7 flex items-center justify-center hover:bg-sage-100 transition-colors duration-150 shrink-0"
          >
            ✕
          </button>
        </div>

        <div className="p-5 space-y-3">
          {!hasExistingOrderForDate ? (
            <div className="rounded-xl bg-tomato-500/10 border border-tomato-500/25 p-3 space-y-2">
              <p className="text-xs text-tomato-600 font-medium">
                {branchName} has no order at all for delivery {deliveryDate} yet. Saving will create a brand-new
                order for them containing only this item — if you meant to add this to an order they've already
                submitted, cancel and switch to that delivery date first.
              </p>
              <label className="flex items-center gap-2 text-xs text-crate-800/70">
                <input
                  type="checkbox"
                  checked={confirmNewOrder}
                  onChange={(e) => setConfirmNewOrder(e.target.checked)}
                  className="accent-crate-700"
                />
                Yes, create a new order for {branchName} on {deliveryDate}.
              </label>
            </div>
          ) : (
            <p className="text-xs text-crate-800/50">
              {currentQuantity !== null
                ? "This branch already has a quantity for this item — saving here will replace it."
                : "This branch hasn't ordered this item — this adds it to their existing order for this date."}
            </p>
          )}
          <div className="flex items-center gap-2">
            <input
              type="number"
              min="0"
              step="0.01"
              autoFocus
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              placeholder="Quantity"
              className="flex-1 border border-sage-300 bg-sage-50/60 rounded-xl px-3 py-2 text-right focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
            />
            <span className="text-sm text-crate-800/50 w-10">{unitCode}</span>
          </div>
          {error && <p className="text-tomato-600 text-sm">{error}</p>}
        </div>

        <div className="p-5 border-t border-sage-100 flex items-center justify-between gap-3">
          {currentQuantity !== null ? (
            <button
              onClick={handleRemove}
              disabled={removing || saving}
              className="text-sm text-tomato-600 hover:text-tomato-700 font-medium disabled:opacity-50 transition-colors duration-150"
              title="Only removable if Admin added this line — a branch's own item can't be removed here."
            >
              {removing ? "Removing…" : "Remove item"}
            </button>
          ) : (
            <span />
          )}
          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="text-sm text-crate-700 border border-sage-300 rounded-full px-4 py-2 hover:bg-sage-50 transition-colors duration-150"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving || removing || (!hasExistingOrderForDate && !confirmNewOrder)}
              className="text-sm bg-gradient-to-b from-crate-700 to-crate-800 text-white rounded-full px-4 py-2 font-semibold hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100 shadow-md shadow-crate-800/20 transition-all duration-150"
            >
              {saving ? "Saving…" : hasExistingOrderForDate ? "Save" : "Create New Order"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
