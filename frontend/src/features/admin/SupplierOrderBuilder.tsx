import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import { Supplier, fetchSuppliers } from "../../api/suppliers";
import { Product, fetchProducts, fetchOrderMatrix, OrderMatrix } from "../../api/orders";
import {
  SupplierOrderItem,
  SupplierPricePreview,
  fetchAssignedQuantities,
  fetchSupplierOrderAdmin,
  fetchSupplierPricePreview,
  setSupplierOrderAdmin,
} from "../../api/supplierOrders";
import { SkeletonTable } from "../shared/ui/Skeleton";

// One cell in the grid = one branch+product combination.
function cellKey(productId: number, branchId: number): string {
  return `${productId}:${branchId}`;
}

type ExtraDetail = { agreed_price: string; notes: string };

function todayIso(): string {
  const d = new Date();
  return d.toISOString().slice(0, 10);
}

function formatDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

export default function SupplierOrderBuilder() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [supplierId, setSupplierId] = useState<number | "">("");
  const [deliveryDate, setDeliveryDate] = useState(todayIso());
  const [matrix, setMatrix] = useState<OrderMatrix | null>(null);

  // Which product rows are visible in the grid. Starts as "whatever branches
  // ordered for this date" (matching the reference layout — items down the
  // side, branches across the top) plus anything already saved on this
  // supplier's order; admin can add more rows via the search box.
  const [rowProductIds, setRowProductIds] = useState<number[]>([]);
  const [addSearch, setAddSearch] = useState("");

  // Grid quantities, keyed by "productId:branchId".
  const [qty, setQty] = useState<Record<string, string>>({});
  // Optional per-cell agreed price / notes, same key. Only meaningful for
  // cells with a quantity.
  const [extra, setExtra] = useState<Record<string, ExtraDetail>>({});
  const [showPricesFor, setShowPricesFor] = useState<Set<string>>(new Set());

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  // Quantity per product already given to OTHER suppliers for this date —
  // subtracted from branch demand so Required Qty reflects what's actually
  // still unassigned, not the full original demand every time.
  const [assignedElsewhere, setAssignedElsewhere] = useState<Record<number, number>>({});

  // This supplier's resolved price per product — a reference shown right
  // in the grid so Admin can see what they charge while still deciding
  // quantities, without switching over to the Supplier Prices page.
  const [supplierPrices, setSupplierPrices] = useState<Record<number, SupplierPricePreview>>({});

  useEffect(() => {
    fetchSuppliers().then(setSuppliers).catch(() => {});
    fetchProducts().then(setProducts).catch(() => {});
  }, []);

  useEffect(() => {
    fetchOrderMatrix(deliveryDate)
      .then(setMatrix)
      .catch(() => setMatrix(null));
  }, [deliveryDate]);

  useEffect(() => {
    if (!supplierId || !matrix) {
      setQty({});
      setExtra({});
      setRowProductIds([]);
      setAssignedElsewhere({});
      setSupplierPrices({});
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSavedMessage(null);
    Promise.all([
      fetchSupplierOrderAdmin(supplierId, deliveryDate),
      fetchAssignedQuantities(deliveryDate, supplierId),
      fetchSupplierPricePreview(supplierId, deliveryDate),
    ])
      .then(([order, assigned, prices]) => {
        if (cancelled) return;
        const nextQty: Record<string, string> = {};
        const nextExtra: Record<string, ExtraDetail> = {};
        const savedProductIds = new Set<number>();
        for (const item of order.items as SupplierOrderItem[]) {
          const key = cellKey(item.product_id, item.branch_id);
          nextQty[key] = String(item.quantity);
          nextExtra[key] = {
            agreed_price: item.agreed_price !== null ? String(item.agreed_price) : "",
            notes: item.notes ?? "",
          };
          savedProductIds.add(item.product_id);
        }
        // Default rows: anything any branch ordered this date, plus
        // anything already saved on this supplier's order (even if no
        // branch happened to order it — e.g. a manually added item).
        const demandProductIds = matrix.rows
          .filter((r) => Object.keys(r.quantities).length > 0)
          .map((r) => r.product_id);
        const merged = Array.from(new Set([...demandProductIds, ...savedProductIds]));
        setQty(nextQty);
        setExtra(nextExtra);
        setRowProductIds(merged);
        setAssignedElsewhere(assigned);
        const priceMap: Record<number, SupplierPricePreview> = {};
        for (const p of prices) priceMap[p.product_id] = p;
        setSupplierPrices(priceMap);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load existing order.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [supplierId, deliveryDate, matrix]);

  const branches = matrix?.branches ?? [];

  const productById = useMemo(() => {
    const m = new Map<number, Product>();
    for (const p of products) m.set(p.id, p);
    return m;
  }, [products]);

  const demandByProduct = useMemo(() => {
    const m = new Map<number, Record<string, number>>();
    if (matrix) for (const r of matrix.rows) m.set(r.product_id, r.quantities);
    return m;
  }, [matrix]);

  const rows = useMemo(() => {
    return rowProductIds
      .map((id) => productById.get(id))
      .filter((p): p is Product => !!p)
      .sort((a, b) => a.description.localeCompare(b.description));
  }, [rowProductIds, productById]);

  const searchResults = useMemo(() => {
    const q = addSearch.trim().toLowerCase();
    if (!q) return [];
    return products
      .filter(
        (p) =>
          !rowProductIds.includes(p.id) &&
          (p.description.toLowerCase().includes(q) || p.product_code.toLowerCase().includes(q))
      )
      .slice(0, 8);
  }, [addSearch, products, rowProductIds]);

  function addRow(productId: number) {
    setRowProductIds((prev) => (prev.includes(productId) ? prev : [...prev, productId]));
    setAddSearch("");
  }

  function removeRow(productId: number) {
    setRowProductIds((prev) => prev.filter((id) => id !== productId));
    setQty((prev) => {
      const next = { ...prev };
      for (const b of branches) delete next[cellKey(productId, b.branch_id)];
      return next;
    });
  }

  function setCellQty(productId: number, branchId: number, value: string) {
    const key = cellKey(productId, branchId);
    setQty((prev) => ({ ...prev, [key]: value }));
  }

  function setCellDetail(productId: number, branchId: number, field: keyof ExtraDetail, value: string) {
    const key = cellKey(productId, branchId);
    setExtra((prev) => ({ ...prev, [key]: { ...(prev[key] ?? { agreed_price: "", notes: "" }), [field]: value } }));
  }

  function fillFromDemand() {
    if (!matrix) return;
    setQty((prev) => {
      const next = { ...prev };
      for (const r of matrix.rows) {
        for (const b of matrix.branches) {
          const d = r.quantities[String(b.branch_id)];
          const key = cellKey(r.product_id, b.branch_id);
          if (d && !next[key]) next[key] = String(d);
        }
      }
      return next;
    });
    setRowProductIds((prev) => {
      const demandIds = matrix.rows.filter((r) => Object.keys(r.quantities).length > 0).map((r) => r.product_id);
      return Array.from(new Set([...prev, ...demandIds]));
    });
  }

  const filledCells = useMemo(() => {
    return Object.entries(qty)
      .filter(([, v]) => v.trim() !== "" && parseFloat(v) > 0)
      .map(([key]) => key);
  }, [qty]);

  const grandTotal = useMemo(() => {
    let total = 0;
    for (const key of filledCells) {
      const q = parseFloat(qty[key]) || 0;
      const price = parseFloat(extra[key]?.agreed_price ?? "") || 0;
      if (extra[key]?.agreed_price) total += q * price;
    }
    return total;
  }, [filledCells, qty, extra]);

  async function handleSave() {
    if (!supplierId) {
      setError("Choose a supplier first.");
      return;
    }
    setError(null);
    setSavedMessage(null);

    if (filledCells.length === 0) {
      setError("Enter at least one quantity in the grid below.");
      return;
    }

    const parsed = filledCells.map((key) => {
      const [productIdStr, branchIdStr] = key.split(":");
      const priceRaw = extra[key]?.agreed_price?.trim() ?? "";
      return {
        branch_id: Number(branchIdStr),
        product_id: Number(productIdStr),
        quantity: parseFloat(qty[key]),
        agreed_price: priceRaw === "" ? null : parseFloat(priceRaw),
        notes: extra[key]?.notes?.trim() || null,
      };
    });

    for (const p of parsed) {
      if (p.agreed_price !== null && p.agreed_price < 0) {
        setError("Agreed price can't be negative.");
        return;
      }
    }

    setSaving(true);
    try {
      await setSupplierOrderAdmin(supplierId as number, deliveryDate, parsed);
      setSavedMessage("Order saved.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the order.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 p-5">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-xs font-semibold text-crate-800/50 uppercase tracking-wide mb-1.5">
              Supplier
            </label>
            <select
              value={supplierId}
              onChange={(e) => setSupplierId(e.target.value ? Number(e.target.value) : "")}
              className="border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm text-crate-950 min-w-[14rem] focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
            >
              <option value="">Select a supplier…</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.supplier_name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-crate-800/50 uppercase tracking-wide mb-1.5">
              Order Date
            </label>
            <input
              type="date"
              value={deliveryDate}
              onChange={(e) => setDeliveryDate(e.target.value)}
              className="border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
            />
          </div>

          {matrix && matrix.rows.some((r) => Object.keys(r.quantities).length > 0) && (
            <button
              onClick={fillFromDemand}
              disabled={!supplierId}
              className="text-xs text-crate-700 border border-sage-300 rounded-full px-3.5 py-2 hover:bg-sage-50 disabled:opacity-40 transition-colors duration-150 ml-auto"
            >
              Fill quantities from branch orders
            </button>
          )}
        </div>
        <p className="text-xs text-crate-800/40 mt-3">
          {formatDate(deliveryDate)}. Pick the supplier and order date first — the order below is saved
          for that combination.
        </p>
      </div>

      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <p className="text-xs font-semibold text-crate-800/50 uppercase tracking-wide">Order lines</p>
          <div className="relative">
            <input
              type="text"
              placeholder="+ Add item…"
              value={addSearch}
              onChange={(e) => setAddSearch(e.target.value)}
              disabled={!supplierId}
              className="text-sm border border-sage-300 bg-sage-50/60 rounded-full px-3.5 py-1.5 min-w-[12rem] focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white disabled:opacity-40 transition-all duration-150"
            />
            {searchResults.length > 0 && (
              <div className="absolute right-0 z-20 mt-1 w-64 bg-white border border-sage-200 rounded-xl shadow-lg py-1 max-h-56 overflow-y-auto">
                {searchResults.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => addRow(p.id)}
                    className="w-full text-left text-sm px-3 py-1.5 hover:bg-sage-50 transition-colors duration-150"
                  >
                    {p.description}
                    <span className="text-crate-800/35 text-xs ml-1.5">{p.product_code}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {!supplierId ? (
          <p className="text-sm text-crate-800/40 text-center py-6">Choose a supplier to start building an order.</p>
        ) : loading ? (
          <SkeletonTable rows={5} columns={4} />
        ) : branches.length === 0 ? (
          <p className="text-sm text-crate-800/40 text-center py-6">No active branches to order for.</p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-crate-800/40 text-center py-6">
            No items yet. Use "+ Add item" above, or "Fill quantities from branch orders" to start from what
            branches ordered.
          </p>
        ) : (
          <div className="overflow-x-auto -mx-5 px-5">
            <table className="text-sm border-collapse min-w-max">
              <thead>
                <tr className="text-crate-800/40 text-left text-xs uppercase tracking-wide border-b border-sage-100">
                  <th className="pr-4 py-2 font-medium sticky left-0 bg-white">Item</th>
                  <th className="px-3 py-2 font-semibold text-crate-800 text-center border-l border-sage-100 normal-case tracking-normal whitespace-nowrap">
                    Supplier Price
                  </th>
                  <th className="px-3 py-2 font-semibold text-crate-800 text-center border-l border-sage-100 normal-case tracking-normal whitespace-nowrap">
                    Required Qty
                    <div className="text-[9px] font-normal text-crate-800/35">Total branch demand</div>
                  </th>
                  {branches.map((b) => (
                    <th key={b.branch_id} className="px-3 py-2 font-semibold text-crate-800 text-center border-l border-sage-100 normal-case tracking-normal">
                      {b.branch_name}
                    </th>
                  ))}
                  <th className="pl-3 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-sage-100">
                {rows.map((p) => {
                  const demand = demandByProduct.get(p.id) ?? {};
                  const productId = p.id;
                  // Required Qty = total branch demand for this item MINUS
                  // whatever's already been given to OTHER suppliers for
                  // the same date — the actual remaining need, so the same
                  // demand doesn't get double-ordered across suppliers.
                  // Never negative even if other suppliers were over-given.
                  const totalDemand = Object.values(demand).reduce((sum, v) => sum + (v ?? 0), 0);
                  const alreadyAssigned = assignedElsewhere[productId] ?? 0;
                  const requiredQty = Math.max(0, totalDemand - alreadyAssigned);
                  return (
                    <tr key={productId}>
                      <td className="pr-4 py-2 text-crate-950 whitespace-nowrap sticky left-0 bg-white">
                        {p.description}
                        <span className="text-crate-800/35 text-xs ml-1.5">{p.product_code}</span>
                      </td>
                      <td className="px-3 py-2 text-center border-l border-sage-100 whitespace-nowrap">
                        {(() => {
                          const sp = supplierPrices[productId];
                          if (!sp) return <span className="text-crate-800/20">—</span>;
                          return (
                            <>
                              <span className={sp.is_estimated ? "text-mango-600/90" : "text-crate-800/80"}>
                                Rs. {sp.price.toFixed(2)}
                              </span>
                              {sp.is_estimated && (
                                <div className="text-[9px] text-mango-600/70 leading-none mt-0.5">
                                  est. from {new Date(sp.as_of + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" })}
                                </div>
                              )}
                            </>
                          );
                        })()}
                      </td>
                      <td className="px-3 py-2 text-center border-l border-sage-100 whitespace-nowrap">
                        <span className="font-semibold text-crate-800">
                          {requiredQty > 0 ? requiredQty : <span className="text-crate-800/20 font-normal">—</span>}
                        </span>
                        {alreadyAssigned > 0 && (
                          <div className="text-[10px] text-crate-800/35 font-normal leading-none mt-0.5">
                            {totalDemand} total · {alreadyAssigned} given elsewhere
                          </div>
                        )}
                      </td>
                      {branches.map((b) => {
                        const key = cellKey(productId, b.branch_id);
                        const hadDemand = (demand[String(b.branch_id)] ?? 0) > 0;
                        const hasQty = qty[key]?.trim() !== "" && qty[key] !== undefined;
                        return (
                          <td
                            key={b.branch_id}
                            className={`px-2 py-1.5 text-center border-l border-sage-100 ${hadDemand ? "bg-mango-500/5" : ""}`}
                          >
                            <div className="flex flex-col items-center gap-1">
                              <input
                                type="number"
                                min="0"
                                step="0.01"
                                placeholder={hadDemand ? String(demand[String(b.branch_id)]) : "—"}
                                value={qty[key] ?? ""}
                                onChange={(e) => setCellQty(productId, b.branch_id, e.target.value)}
                                className="w-16 border border-sage-300 bg-white rounded-lg px-1.5 py-1 text-center text-sm focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 transition-colors duration-150"
                              />
                              {hasQty && (
                                <button
                                  onClick={() =>
                                    setShowPricesFor((prev) => {
                                      const next = new Set(prev);
                                      next.has(key) ? next.delete(key) : next.add(key);
                                      return next;
                                    })
                                  }
                                  className="text-[10px] text-crate-800/35 hover:text-crate-700 transition-colors duration-150"
                                >
                                  {extra[key]?.agreed_price ? `@ Rs.${extra[key].agreed_price}` : "+ price/notes"}
                                </button>
                              )}
                              {hasQty && showPricesFor.has(key) && (
                                <div className="flex flex-col items-stretch gap-1 pt-1 w-32">
                                  <input
                                    type="number"
                                    min="0"
                                    step="0.01"
                                    placeholder="Agreed price"
                                    value={extra[key]?.agreed_price ?? ""}
                                    onChange={(e) => setCellDetail(productId, b.branch_id, "agreed_price", e.target.value)}
                                    className="border border-sage-300 bg-white rounded-lg px-1.5 py-1 text-center text-xs focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700"
                                  />
                                  <input
                                    type="text"
                                    placeholder="Notes"
                                    value={extra[key]?.notes ?? ""}
                                    onChange={(e) => setCellDetail(productId, b.branch_id, "notes", e.target.value)}
                                    className="border border-sage-300 bg-white rounded-lg px-1.5 py-1 text-center text-xs focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700"
                                  />
                                </div>
                              )}
                            </div>
                          </td>
                        );
                      })}
                      <td className="pl-3 py-1.5">
                        <button
                          onClick={() => removeRow(productId)}
                          className="text-tomato-500 hover:text-tomato-600 text-xs font-medium transition-colors duration-150"
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {rows.length > 0 && (
          <p className="text-[11px] text-crate-800/35 mt-3">
            <span className="inline-block w-2.5 h-2.5 rounded-sm bg-mango-500/20 align-middle mr-1.5" /> shaded
            cells are pre-filled with what that branch actually ordered — placeholder shows the demand figure
            even if you haven't typed a value yet. "Required Qty" is the total across all branches, regardless
            of supplier — use it as your target if this item is being split across more than one supplier.
          </p>
        )}

        {filledCells.length > 0 && (
          <div className="flex justify-end mt-3 text-sm text-crate-800/70">
            Estimated total (priced lines only):{" "}
            <span className="font-semibold text-crate-950 ml-1.5">Rs. {grandTotal.toFixed(2)}</span>
          </div>
        )}

        {error && <p className="text-tomato-600 text-sm mt-3">{error}</p>}
        {savedMessage && <p className="text-crate-700 text-sm mt-3 font-medium">{savedMessage}</p>}

        <div className="flex justify-end mt-4">
          <button
            onClick={handleSave}
            disabled={saving || !supplierId}
            className="text-sm bg-gradient-to-b from-crate-700 to-crate-800 text-white rounded-full px-5 py-2 font-semibold hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100 shadow-md shadow-crate-800/20 transition-all duration-150"
          >
            {saving ? "Saving…" : "Save order to supplier"}
          </button>
        </div>
      </div>
    </div>
  );
}
