import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import { ProductComparison, fetchProductComparison, setProductAssignments } from "../../api/assignments";
import { useToast } from "../shared/ui/Toast";

type Row = { supplier_id: number; quantity: string; agreed_price: string };

export default function ProductAssignmentPanel({
  productId,
  deliveryDate,
  onClose,
  onSaved,
}: {
  productId: number;
  deliveryDate: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { show } = useToast();
  const [data, setData] = useState<ProductComparison | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchProductComparison(productId, deliveryDate)
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setRows(
          d.assignments.map((a) => ({
            supplier_id: a.supplier_id,
            quantity: String(a.quantity),
            agreed_price: String(a.agreed_price),
          }))
        );
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load price comparison.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [productId, deliveryDate]);

  const assignedTotal = useMemo(
    () => rows.reduce((sum, r) => sum + (parseFloat(r.quantity) || 0), 0),
    [rows]
  );
  const remaining = data ? data.total_demand - assignedTotal : 0;

  function addSupplier(supplierId: number) {
    if (rows.some((r) => r.supplier_id === supplierId)) return;
    const quote = data?.quotes.find((q) => q.supplier_id === supplierId);
    setRows((prev) => [
      ...prev,
      {
        supplier_id: supplierId,
        quantity: remaining > 0 ? String(Math.round(remaining * 100) / 100) : "",
        agreed_price: quote ? String(quote.price) : "",
      },
    ]);
  }

  function updateRow(supplierId: number, field: "quantity" | "agreed_price", value: string) {
    setRows((prev) => prev.map((r) => (r.supplier_id === supplierId ? { ...r, [field]: value } : r)));
  }

  function removeRow(supplierId: number) {
    setRows((prev) => prev.filter((r) => r.supplier_id !== supplierId));
  }

  async function handleSave() {
    setError(null);
    const parsed = rows.map((r) => ({
      supplier_id: r.supplier_id,
      quantity: parseFloat(r.quantity),
      agreed_price: parseFloat(r.agreed_price),
    }));
    if (parsed.some((r) => !r.quantity || r.quantity <= 0 || !r.agreed_price || r.agreed_price <= 0)) {
      setError("Every assigned supplier needs a quantity and agreed price greater than zero.");
      return;
    }
    setSaving(true);
    try {
      await setProductAssignments(productId, deliveryDate, parsed);
      onSaved();
      onClose();
      show("success", `Supplier assignments saved for ${data?.description ?? "this product"}.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save assignments.");
    } finally {
      setSaving(false);
    }
  }

  const unassignedQuotes = data?.quotes.filter((q) => !rows.some((r) => r.supplier_id === q.supplier_id)) ?? [];

  return (
    <div
      className="fixed inset-0 bg-crate-950/40 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-[1.75rem] shadow-[0_30px_60px_-15px_rgba(21,56,38,0.35)] w-full max-w-2xl max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {loading ? (
          <div className="p-8 text-crate-800/40 text-sm text-center">Loading price comparison…</div>
        ) : !data ? (
          <div className="p-6 text-tomato-600 text-sm">{error ?? "Could not load this product."}</div>
        ) : (
          <>
            <div className="p-5 border-b border-sage-100 flex items-start justify-between">
              <div>
                <p className="text-xs text-crate-800/40">{data.product_code}</p>
                <h3 className="text-base font-display font-bold text-crate-950">{data.description}</h3>
                <p className="text-sm text-crate-800/60 mt-1">
                  Total ordered: <span className="font-medium text-crate-800">{data.total_demand}</span>{" "}
                  {data.unit_code} for delivery {data.delivery_date}
                </p>
              </div>
              <button
                onClick={onClose}
                className="text-crate-800/40 hover:text-crate-800 text-sm rounded-full w-7 h-7 flex items-center justify-center hover:bg-sage-100 transition-colors duration-150 shrink-0"
              >
                ✕
              </button>
            </div>

            <div className="p-5 space-y-5">
              <div>
                <p className="text-xs font-semibold text-crate-800/50 uppercase tracking-wide mb-2">
                  Supplier quotes
                </p>
                {data.quotes.length === 0 ? (
                  <p className="text-sm text-crate-800/40">No suppliers have submitted a price for this product.</p>
                ) : (
                  <div className="space-y-1.5">
                    {data.quotes.map((q) => {
                      const isAssigned = rows.some((r) => r.supplier_id === q.supplier_id);
                      return (
                        <div
                          key={q.supplier_id}
                          className="flex items-center justify-between text-sm px-3.5 py-2.5 rounded-2xl bg-sage-50"
                        >
                          <span className="text-crate-800">{q.supplier_name}</span>
                          <div className="flex items-center gap-3">
                            <span className="text-crate-800/70">
                              Rs. {q.price.toFixed(2)} /{q.unit_code}
                            </span>
                            <button
                              onClick={() => addSupplier(q.supplier_id)}
                              disabled={isAssigned}
                              className="text-xs bg-crate-700 text-white rounded-full px-3 py-1.5 font-semibold hover:bg-crate-800 disabled:opacity-40 transition-colors duration-150"
                            >
                              {isAssigned ? "Added" : "Assign"}
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {rows.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-crate-800/50 uppercase tracking-wide mb-2">
                    Assignment {`(negotiate the agreed price if it differs from the quote)`}
                  </p>
                  <div className="space-y-2">
                    {rows.map((r) => {
                      const quote = data.quotes.find((q) => q.supplier_id === r.supplier_id);
                      const name = quote?.supplier_name ?? `Supplier #${r.supplier_id}`;
                      return (
                        <div key={r.supplier_id} className="flex items-center gap-2 text-sm">
                          <span className="flex-1 text-crate-800 truncate">{name}</span>
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={r.quantity}
                            onChange={(e) => updateRow(r.supplier_id, "quantity", e.target.value)}
                            placeholder="Qty"
                            className="w-20 border border-sage-300 bg-sage-50/60 rounded-xl px-2 py-1.5 text-right focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
                          />
                          <span className="text-crate-800/40 text-xs w-8">{data.unit_code}</span>
                          <span className="text-crate-800/40">@ Rs.</span>
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={r.agreed_price}
                            onChange={(e) => updateRow(r.supplier_id, "agreed_price", e.target.value)}
                            placeholder="Price"
                            className="w-24 border border-sage-300 bg-sage-50/60 rounded-xl px-2 py-1.5 text-right focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
                          />
                          <button
                            onClick={() => removeRow(r.supplier_id)}
                            className="text-tomato-500 hover:text-tomato-600 text-xs px-1.5 font-medium transition-colors duration-150"
                          >
                            Remove
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {unassignedQuotes.length === 0 && data.quotes.length > 0 && rows.length === 0 && null}

              <div
                className={`text-sm rounded-2xl px-4 py-2.5 font-medium ${
                  Math.abs(remaining) < 0.01
                    ? "bg-crate-700/10 text-crate-800"
                    : remaining > 0
                    ? "bg-mango-500/15 text-[#8A5A0D]"
                    : "bg-tomato-500/10 text-tomato-600"
                }`}
              >
                {Math.abs(remaining) < 0.01
                  ? "Fully assigned."
                  : remaining > 0
                  ? `${remaining.toFixed(2)} ${data.unit_code} still unassigned.`
                  : `Over-assigned by ${Math.abs(remaining).toFixed(2)} ${data.unit_code} — reduce a quantity.`}
              </div>

              {error && <p className="text-tomato-600 text-sm">{error}</p>}
            </div>

            <div className="p-5 border-t border-sage-100 flex justify-end gap-3">
              <button
                onClick={onClose}
                className="text-sm text-crate-700 border border-sage-300 rounded-full px-4 py-2 hover:bg-sage-50 transition-colors duration-150"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving || remaining < -0.01}
                className="text-sm bg-gradient-to-b from-crate-700 to-crate-800 text-white rounded-full px-4 py-2 font-semibold hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100 shadow-md shadow-crate-800/20 transition-all duration-150"
              >
                {saving ? "Saving…" : "Save Assignment"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
