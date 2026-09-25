import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import { Product, compareProductDisplayOrder, fetchProducts } from "../../api/orders";
import { Promotion, PromotionType, fetchAllPromotions, savePromotions } from "../../api/promotions";
import { CategoryBadge } from "../shared/ui/CategoryBadge";
import { PROMOTION_TYPES } from "../shared/ui/PromotionBadge";
import { Modal } from "../shared/ui/Modal";
import Button from "../shared/ui/Button";

function todayIso(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

type Draft = { type: PromotionType | null; start: string; end: string };

const EMPTY: Draft = { type: null, start: "", end: "" };

const inputClass =
  "border border-sage-300 bg-sage-50/60 rounded-full px-3 py-1.5 text-sm text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150";

function statusOf(d: Draft, today: string): { label: string; className: string } | null {
  if (!d.type || !d.start || !d.end) return null;
  if (d.end < today) return { label: "Ended", className: "text-crate-800/40" };
  if (d.start > today) return { label: "Upcoming", className: "text-mango-500" };
  return { label: "Running", className: "text-crate-700" };
}

// Admin sets one promotion per fruit/veg item: a type (Fresh Choice /
// Special Weekend / Special) and the date range it runs for. Branches see
// it as a colored label next to the product name while today is inside
// that range; once the end date passes the label disappears on its own.
export default function AdminPromotions() {
  const [products, setProducts] = useState<Product[]>([]);
  const [drafts, setDrafts] = useState<Record<number, Draft>>({});
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string>("ALL");
  const [onlyPromoted, setOnlyPromoted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const today = todayIso();

  function applySaved(list: Promotion[]) {
    const next: Record<number, Draft> = {};
    for (const p of list) next[p.product_id] = { type: p.promotion_type, start: p.start_date, end: p.end_date };
    setDrafts(next);
    setDirty(false);
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchProducts(), fetchAllPromotions()])
      .then(([p, promos]) => {
        if (cancelled) return;
        setProducts([...p].sort(compareProductDisplayOrder));
        applySaved(promos);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load promotions.");
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
      if (onlyPromoted && !drafts[p.id]?.type) return false;
      return true;
    });
  }, [products, category, search, onlyPromoted, drafts]);

  const promotedCount = useMemo(() => Object.values(drafts).filter((d) => d.type).length, [drafts]);

  function update(productId: number, patch: Partial<Draft>) {
    setDrafts((prev) => {
      const cur = prev[productId] ?? EMPTY;
      const next = { ...cur, ...patch };
      // Picking a type on a fresh row starts the range today, so the
      // admin usually only has to choose an end date.
      if (patch.type && !cur.type && !cur.start) next.start = today;
      return { ...prev, [productId]: next };
    });
    setDirty(true);
    setSaved(false);
  }

  function remove(productId: number) {
    setDrafts((prev) => {
      const next = { ...prev };
      delete next[productId];
      return next;
    });
    setDirty(true);
    setSaved(false);
  }

  async function save(lines: Promotion[]) {
    setError(null);
    setSaved(false);
    setSaving(true);
    try {
      applySaved(await savePromotions(lines));
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  function handleSave() {
    const names = new Map(products.map((p) => [p.id, p.description]));
    const lines: Promotion[] = [];
    for (const [pid, d] of Object.entries(drafts)) {
      if (!d.type) continue;
      const name = names.get(Number(pid)) ?? `Product ${pid}`;
      if (!d.start || !d.end) {
        setError(`${name}: choose both a start and an end date.`);
        return;
      }
      if (d.end < d.start) {
        setError(`${name}: the end date can't be before the start date.`);
        return;
      }
      lines.push({ product_id: Number(pid), promotion_type: d.type, start_date: d.start, end_date: d.end });
    }
    save(lines);
  }

  async function handleClearAll() {
    setConfirmClear(false);
    await save([]);
  }

  if (loading) {
    return <p className="text-sm text-crate-800/50 p-6">Loading promotions…</p>;
  }

  return (
    <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 overflow-hidden">
      <div className="p-6 border-b border-sage-100">
        <p className="font-display font-semibold text-crate-950">Promotions</p>
        <p className="text-sm text-crate-800/60 mt-1">
          Choose a promotion type and date range for each item. Branches see the promotion as a label next to the
          product name while it's running, and it ends automatically after the end date.
        </p>
        <div className="flex flex-wrap items-center gap-3 mt-3">
          {PROMOTION_TYPES.map((t) => (
            <span key={t.id} className="flex items-center gap-1.5 text-xs text-crate-800/70">
              <span className={`w-2.5 h-2.5 rounded-full ${t.dot}`} />
              {t.label}
            </span>
          ))}
        </div>
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
          <label className="flex items-center gap-2 text-sm text-crate-800/70 whitespace-nowrap">
            <input
              type="checkbox"
              checked={onlyPromoted}
              onChange={(e) => setOnlyPromoted(e.target.checked)}
              className="accent-crate-700"
            />
            On promotion only
          </label>
        </div>
      </div>

      <div className="hidden lg:grid grid-cols-[minmax(0,1.2fr)_minmax(0,1.6fr)_minmax(0,1.2fr)] gap-4 px-6 py-2 bg-sage-50/60 border-b border-sage-100 text-[11px] uppercase tracking-wide text-crate-800/50 font-semibold">
        <span>Fruit &amp; Vegetables</span>
        <span>Promotion Type</span>
        <span>Date Range</span>
      </div>

      <div className="max-h-[32rem] overflow-y-auto divide-y divide-sage-100">
        {filtered.length === 0 && (
          <p className="p-6 text-sm text-crate-800/35 text-center">No products match your search.</p>
        )}
        {filtered.map((p) => {
          const d = drafts[p.id] ?? EMPTY;
          const status = statusOf(d, today);
          return (
            <div
              key={p.id}
              className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1.6fr)_minmax(0,1.2fr)] gap-3 lg:gap-4 lg:items-center px-6 py-3 hover:bg-sage-50/50 transition-colors duration-100"
            >
              <div className="min-w-0">
                <p className="text-sm text-crate-950 truncate">{p.description}</p>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className="text-xs text-crate-800/40">{p.product_code}</span>
                  <CategoryBadge name={p.category_name} />
                </div>
              </div>

              <div role="radiogroup" aria-label={`Promotion type for ${p.description}`} className="flex flex-wrap gap-2">
                {PROMOTION_TYPES.map((t) => {
                  const checked = d.type === t.id;
                  return (
                    <label
                      key={t.id}
                      className={`flex items-center gap-1.5 cursor-pointer rounded-full border px-2.5 py-1 text-xs font-medium transition-colors duration-100 ${
                        checked ? `${t.badge} border-transparent` : "border-sage-300 text-crate-800/60 hover:bg-sage-50"
                      }`}
                    >
                      <input
                        type="radio"
                        name={`promo-${p.id}`}
                        checked={checked}
                        onChange={() => update(p.id, { type: t.id })}
                        className="sr-only"
                      />
                      <span
                        className={`w-3 h-3 rounded-full border-2 flex items-center justify-center ${
                          checked ? "border-current" : "border-sage-300"
                        }`}
                      >
                        <span className={`w-1.5 h-1.5 rounded-full ${checked ? t.dot : "bg-transparent"}`} />
                      </span>
                      {t.label}
                    </label>
                  );
                })}
                {d.type && (
                  <button
                    type="button"
                    onClick={() => remove(p.id)}
                    className="text-xs text-crate-800/40 hover:text-tomato-600 px-1"
                  >
                    Remove
                  </button>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <input
                  type="date"
                  aria-label={`Promotion start date for ${p.description}`}
                  value={d.start}
                  disabled={!d.type}
                  max={d.end || undefined}
                  onChange={(e) => update(p.id, { start: e.target.value })}
                  className={`${inputClass} disabled:opacity-40`}
                />
                <span className="text-xs text-crate-800/40">to</span>
                <input
                  type="date"
                  aria-label={`Promotion end date for ${p.description}`}
                  value={d.end}
                  disabled={!d.type}
                  min={d.start || undefined}
                  onChange={(e) => update(p.id, { end: e.target.value })}
                  className={`${inputClass} disabled:opacity-40`}
                />
                {status && <span className={`text-xs font-medium ${status.className}`}>{status.label}</span>}
              </div>
            </div>
          );
        })}
      </div>

      <div className="p-6 border-t border-sage-100 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-crate-800/60">
          {promotedCount} product{promotedCount === 1 ? "" : "s"} on promotion
          {dirty && <span className="text-tomato-600"> · unsaved changes</span>}
        </p>
        <div className="flex items-center gap-3">
          {saved && <p className="text-crate-700 text-sm">✓ Saved.</p>}
          {error && <p className="text-tomato-600 text-sm">{error}</p>}
          <Button variant="danger" onClick={() => setConfirmClear(true)} disabled={saving || promotedCount === 0}>
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
        title="Clear all promotions?"
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
          This removes every promotion, and branches will stop seeing the labels. This can't be undone.
        </p>
      </Modal>
    </div>
  );
}
