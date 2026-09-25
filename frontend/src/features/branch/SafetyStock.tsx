import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import { Product, compareProductDisplayOrder, fetchProducts } from "../../api/orders";
import { fetchMySafetyStock, saveMySafetyStock } from "../../api/safetyStock";
import { CategoryBadge } from "../shared/ui/CategoryBadge";
import { Modal } from "../shared/ui/Modal";
import Button from "../shared/ui/Button";

// The branch's standing safety-stock level per product. Unlike an order,
// nothing here is per-day: saved figures stay as they are, day after day,
// until the branch edits and saves again (or clears them).
export default function SafetyStock() {
  const [products, setProducts] = useState<Product[]>([]);
  const [quantities, setQuantities] = useState<Record<number, string>>({});
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string>("ALL");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function applySaved(q: Record<number, number>, at: string | null) {
    const next: Record<number, string> = {};
    for (const [pid, qty] of Object.entries(q)) next[Number(pid)] = String(qty);
    setQuantities(next);
    setUpdatedAt(at);
    setDirty(false);
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchProducts(), fetchMySafetyStock()])
      .then(([p, s]) => {
        if (cancelled) return;
        setProducts([...p].sort(compareProductDisplayOrder));
        applySaved(s.quantities, s.updated_at);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load safety stock.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const categories = useMemo(() => {
    const set = new Set(products.map((p) => p.category_name));
    return ["ALL", ...Array.from(set).sort()];
  }, [products]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return products.filter((p) => {
      if (category !== "ALL" && p.category_name !== category) return false;
      if (q && !p.description.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [products, category, search]);

  const filledCount = useMemo(
    () => Object.values(quantities).filter((v) => parseFloat(v) > 0).length,
    [quantities]
  );

  function setQty(productId: number, value: string) {
    setQuantities((prev) => ({ ...prev, [productId]: value }));
    setDirty(true);
    setSaved(false);
  }

  async function save(lines: { product_id: number; quantity: number }[]) {
    setError(null);
    setSaved(false);
    setSaving(true);
    try {
      const s = await saveMySafetyStock(lines);
      applySaved(s.quantities, s.updated_at);
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  function handleSave() {
    const lines = Object.entries(quantities)
      .map(([pid, qty]) => ({ product_id: Number(pid), quantity: parseFloat(qty) }))
      .filter((l) => l.quantity > 0);
    save(lines);
  }

  async function handleClearAll() {
    setConfirmClear(false);
    await save([]);
  }

  if (loading) {
    return <p className="text-sm text-crate-800/50 p-6">Loading safety stock…</p>;
  }

  return (
    <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 overflow-hidden">
      <div className="p-6 border-b border-sage-100">
        <p className="font-display font-semibold text-crate-950">Safety Stock</p>
        <p className="text-sm text-crate-800/60 mt-1">
          Enter the safety stock quantity for each item. Saved quantities stay in place every day until you change
          them.
          {updatedAt && <> Last saved {new Date(updatedAt).toLocaleString()}.</>}
        </p>
        <div className="flex flex-col sm:flex-row gap-3 mt-4">
          <input
            placeholder="Search products…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm text-crate-950 placeholder:text-crate-950/35 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
          />
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
          >
            {categories.map((c) => (
              <option key={c} value={c}>
                {c === "ALL" ? "All categories" : c}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex items-center justify-between px-6 py-2 bg-sage-50/60 border-b border-sage-100 text-[11px] uppercase tracking-wide text-crate-800/50 font-semibold">
        <span>Fruit &amp; Vegetables</span>
        <span className="w-36 text-right pr-12">Quantity</span>
      </div>

      <div className="max-h-[28rem] overflow-y-auto divide-y divide-sage-100">
        {filtered.length === 0 && (
          <p className="p-6 text-sm text-crate-800/35 text-center">No products match your search.</p>
        )}
        {filtered.map((p) => (
          <div key={p.id} className="flex items-center justify-between px-6 py-3 hover:bg-sage-50/50 transition-colors duration-100">
            <div className="min-w-0">
              <p className="text-sm text-crate-950 truncate">{p.description}</p>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="text-xs text-crate-800/40">{p.product_code}</span>
                <CategoryBadge name={p.category_name} />
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0 ml-4">
              <input
                type="number"
                min="0"
                step="0.01"
                placeholder="0"
                aria-label={`Safety stock for ${p.description}`}
                value={quantities[p.id] ?? ""}
                onChange={(e) => setQty(p.id, e.target.value)}
                className="w-24 border border-sage-300 bg-sage-50/60 rounded-full px-3 py-1.5 text-sm text-right text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
              />
              <span className="text-xs text-crate-800/40 w-10">{p.unit_code}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="p-6 border-t border-sage-100 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-crate-800/60">
          {filledCount} product{filledCount === 1 ? "" : "s"} with a quantity entered
          {dirty && <span className="text-tomato-600"> · unsaved changes</span>}
        </p>
        <div className="flex items-center gap-3">
          {saved && <p className="text-crate-700 text-sm">✓ Saved.</p>}
          {error && <p className="text-tomato-600 text-sm">{error}</p>}
          <Button
            variant="danger"
            onClick={() => setConfirmClear(true)}
            disabled={saving || (filledCount === 0 && !updatedAt)}
          >
            Clear All
          </Button>
          <Button onClick={handleSave} loading={saving} disabled={!dirty}>
            Save
          </Button>
        </div>
      </div>

      <Modal
        open={confirmClear}
        onClose={() => setConfirmClear(false)}
        title="Clear all safety stock?"
        actions={
          <>
            <Button variant="secondary" size="sm" onClick={() => setConfirmClear(false)}>
              Cancel
            </Button>
            <Button variant="danger" size="sm" onClick={handleClearAll}>
              Clear All
            </Button>
          </>
        }
      >
        <p className="text-sm text-crate-800/70">
          This removes every saved safety stock quantity for your branch. This can't be undone.
        </p>
      </Modal>
    </div>
  );
}
