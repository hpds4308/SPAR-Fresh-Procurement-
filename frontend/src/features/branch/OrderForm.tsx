import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import {
  Product,
  OrderWindow,
  Order,
  fetchProducts,
  fetchOrderWindow,
  fetchMyOrderToday,
  fetchStockInHand,
  submitOrder,
  saveDraftOrder,
} from "../../api/orders";
import { CategoryBadge } from "../shared/ui/CategoryBadge";
import { PromotionBadge } from "../shared/ui/PromotionBadge";
import { useActivePromotions } from "../shared/useActivePromotions";

function formatDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
}

// Only some products have a real photo on file (named by product code);
// most don't. Nothing is shown by default — hovering the item name pops
// up the photo, only for products a preload check confirmed actually has
// one, so hovering an item with no photo does nothing rather than
// showing an empty or broken box.
function productImageUrl(productCode: string): string {
  return `/images/products/${productCode}.png`;
}

const PREVIEW_SIZE = 180;

export default function OrderForm({ onSubmitted }: { onSubmitted: () => void }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [window_, setWindow] = useState<OrderWindow | null>(null);
  const [myOrder, setMyOrder] = useState<Order | null>(null);
  const [stockByProduct, setStockByProduct] = useState<Record<number, number>>({});
  const promotions = useActivePromotions();
  // Product IDs a real photo was found for, discovered by silently
  // preloading every product's image once products are known (below) —
  // this decides whether hovering an item's name can pop anything up at
  // all, rather than trying and failing on every hover.
  const [hasImage, setHasImage] = useState<Set<number>>(new Set());
  // The single floating preview, positioned in viewport coordinates
  // (not relative to the scrolling list) so it's never clipped by the
  // list's own overflow — see showPreview/hidePreview below.
  const [preview, setPreview] = useState<{ productCode: string; top: number; left: number } | null>(null);
  const [quantities, setQuantities] = useState<Record<number, string>>({});
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string>("ALL");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draftSaved, setDraftSaved] = useState(false);

  // A DRAFT is still editable; anything past that (SUBMITTED/ASSIGNED/
  // CONFIRMED) is locked — the branch can view it but not change it.
  const isLocked = myOrder !== null && myOrder.status !== "DRAFT";

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        // Stock-in-hand is a reference display only — a POS outage or
        // missing setup must never stop the order form itself from loading,
        // so its failure is swallowed here rather than joining the others.
        const [p, w, mine, stock] = await Promise.all([
          fetchProducts(),
          fetchOrderWindow(),
          fetchMyOrderToday(),
          fetchStockInHand().catch(() => ({})),
        ]);
        if (!cancelled) {
          setProducts(p);
          setWindow(w);
          setMyOrder(mine);
          setStockByProduct(stock);
          if (mine && mine.status === "DRAFT") {
            const prefill: Record<number, string> = {};
            for (const ln of mine.lines) prefill[ln.product_id] = String(ln.quantity);
            setQuantities(prefill);
          }
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load order form.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  // Silently probes every product's photo once, off-screen — populates
  // hasImage per product as each check resolves, so the hover preview
  // only ever offers to pop up for an item that genuinely has one.
  useEffect(() => {
    if (products.length === 0) return;
    let cancelled = false;
    for (const p of products) {
      const img = new Image();
      img.onload = () => {
        if (!cancelled) setHasImage((prev) => (prev.has(p.id) ? prev : new Set(prev).add(p.id)));
      };
      img.src = productImageUrl(p.product_code);
    }
    return () => {
      cancelled = true;
    };
  }, [products]);

  const productCodeById = useMemo(() => {
    const m = new Map<number, string>();
    for (const p of products) m.set(p.id, p.product_code);
    return m;
  }, [products]);

  function showPreview(productId: number, target: HTMLElement) {
    const productCode = productCodeById.get(productId);
    if (!productCode) return;
    const rect = target.getBoundingClientRect();
    // Prefer just above the name; if that would run off the top of the
    // viewport (an item near the top of the scrolled list), show it just
    // below instead.
    const top = rect.top - PREVIEW_SIZE - 10 >= 8 ? rect.top - PREVIEW_SIZE - 10 : rect.bottom + 10;
    setPreview({ productCode, top, left: rect.left });
  }

  function hidePreview() {
    setPreview(null);
  }

  // Fixed positioning (viewport coordinates, from getBoundingClientRect)
  // rather than absolute — so the popup is never clipped by the product
  // list's own scroll container, wherever the hovered row currently sits.
  const previewPopup = preview && (
    <div
      className="fixed z-50 pointer-events-none rounded-xl border border-sage-200 bg-white p-1.5 shadow-xl"
      style={{ top: preview.top, left: preview.left }}
    >
      <img
        src={productImageUrl(preview.productCode)}
        alt=""
        className="rounded-lg object-contain"
        style={{ width: PREVIEW_SIZE, height: PREVIEW_SIZE }}
      />
    </div>
  );

  const categories = useMemo(() => {
    const set = new Set(products.map((p) => p.category_name));
    return ["ALL", ...Array.from(set).sort()];
  }, [products]);

  const filtered = useMemo(() => {
    return products.filter((p) => {
      if (category !== "ALL" && p.category_name !== category) return false;
      if (search.trim() && !p.description.toLowerCase().includes(search.trim().toLowerCase())) return false;
      return true;
    });
  }, [products, category, search]);

  const lineCount = useMemo(
    () => Object.values(quantities).filter((v) => parseFloat(v) > 0).length,
    [quantities]
  );

  function setQty(productId: number, value: string) {
    setQuantities((prev) => ({ ...prev, [productId]: value }));
    setDraftSaved(false);
  }

  function buildLines() {
    return Object.entries(quantities)
      .map(([productId, qty]) => ({ product_id: Number(productId), quantity: parseFloat(qty) }))
      .filter((l) => l.quantity > 0);
  }

  async function handleSaveDraft() {
    setError(null);
    setDraftSaved(false);
    const lines = buildLines();
    if (lines.length === 0) {
      setError("Enter a quantity for at least one product.");
      return;
    }
    setSaving(true);
    try {
      const order = await saveDraftOrder(lines);
      setMyOrder(order);
      setDraftSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the draft. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  async function handleSubmit() {
    setError(null);
    const lines = buildLines();

    if (lines.length === 0) {
      setError("Enter a quantity for at least one product.");
      return;
    }

    setSubmitting(true);
    try {
      const order = await submitOrder(lines);
      setMyOrder(order);
      onSubmitted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit the order. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 p-8 text-crate-800/40 text-sm text-center">
        Loading products…
      </div>
    );
  }

  if (isLocked && myOrder) {
    return (
      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 p-6">
        {previewPopup}
        {myOrder.auto_submitted ? (
          <>
            <p className="text-[#8A5A0D] font-semibold">Your order was submitted automatically.</p>
            <p className="text-crate-800/60 text-sm mt-1">
              Nothing was submitted before the {window_?.cutoff_time ?? ""} cutoff, so{" "}
              {myOrder.auto_submit_source === "DRAFT"
                ? "your saved draft was submitted for you."
                : myOrder.auto_submit_source === "LATEST"
                  ? "your latest previous order was copied and submitted for you."
                  : "last week's order for the same day was copied and submitted for you."}{" "}
              Contact SPAR Fresh Procurement if anything needs to change.
            </p>
          </>
        ) : (
          <p className="text-crate-700 font-semibold">Order submitted successfully.</p>
        )}
        <p className="text-crate-800/60 text-sm mt-1">
          It will be delivered on {formatDate(myOrder.delivery_date)}. This order is now read-only — you
          can view it below, but quantities can no longer be changed.
        </p>
        <div className="mt-4 divide-y divide-sage-100 border border-sage-100 rounded-xl overflow-hidden">
          {myOrder.lines.map((ln) => (
            <div key={ln.id} className="flex items-center justify-between px-4 py-2 text-sm">
              <span
                className={`text-crate-950 truncate w-fit ${hasImage.has(ln.product_id) ? "cursor-pointer" : ""}`}
                onMouseEnter={(e) => hasImage.has(ln.product_id) && showPreview(ln.product_id, e.currentTarget)}
                onMouseLeave={hidePreview}
              >
                {ln.product_description}
              </span>
              <span className="text-crate-800/70 shrink-0 ml-3">
                {ln.quantity} {ln.unit_code}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (window_ && !window_.is_open) {
    return (
      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 p-6">
        <p className="text-crate-800 font-semibold">Ordering is closed for today.</p>
        <p className="text-crate-800/60 text-sm mt-1">
          The daily cutoff is {window_.cutoff_time}. Please come back before {window_.cutoff_time}{" "}
          tomorrow to place tomorrow's order.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 overflow-hidden">
      {previewPopup}
      <div className="p-6 border-b border-sage-100">
        {window_ && (
          <p className="text-sm text-crate-800/70">
            Ordering today for delivery on{" "}
            <span className="font-medium text-crate-800">{formatDate(window_.delivery_date)}</span>{" "}
            &middot; closes at {window_.cutoff_time} today
          </p>
        )}
        <div className="flex flex-col sm:flex-row gap-3 mt-4">
          <input
            placeholder="Search products…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 min-w-0 border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm text-crate-950 placeholder:text-crate-950/35 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
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

      <div className="max-h-[28rem] overflow-y-auto divide-y divide-sage-100">
        {filtered.length === 0 && (
          <p className="p-6 text-sm text-crate-800/35 text-center">No products match your search.</p>
        )}
        {filtered.map((p) => (
          <div key={p.id} className="flex items-center justify-between px-6 py-3 hover:bg-sage-50/50 transition-colors duration-100">
            <div className="min-w-0 flex-1 pr-2">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 min-w-0">
                <p
                  className={`text-sm text-crate-950 truncate w-fit max-w-full ${hasImage.has(p.id) ? "cursor-pointer" : ""}`}
                  onMouseEnter={(e) => hasImage.has(p.id) && showPreview(p.id, e.currentTarget)}
                  onMouseLeave={hidePreview}
                >
                  {p.description}
                </p>
                {promotions[p.id] && (
                  <PromotionBadge
                    name={promotions[p.id].promotion_name}
                    color={promotions[p.id].color}
                    endDate={promotions[p.id].end_date}
                    className="max-w-full truncate align-middle"
                  />
                )}
              </div>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="text-xs text-crate-800/40">
                  {p.product_code}
                  {p.subcategory ? ` · ${p.subcategory}` : ""}
                </span>
                <CategoryBadge name={p.category_name} />
              </div>
            </div>
            <div className="text-right shrink-0 w-28 px-2">
              <p className="text-[10px] uppercase tracking-wide whitespace-nowrap text-crate-800/35">Stock in Hand</p>
              <p className="text-sm text-crate-800/70">
                {stockByProduct[p.id] !== undefined ? `${stockByProduct[p.id]} ${p.unit_code}` : "—"}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0 ml-4">
              <input
                type="number"
                min="0"
                step="0.01"
                placeholder="0"
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
          {lineCount} product{lineCount === 1 ? "" : "s"} with a quantity entered
        </p>
        <div className="flex items-center gap-3">
          {draftSaved && <p className="text-crate-700 text-sm">✓ Draft saved.</p>}
          {error && <p className="text-tomato-600 text-sm">{error}</p>}
          <button
            onClick={handleSaveDraft}
            disabled={saving || submitting || lineCount === 0}
            className="text-sm text-crate-700 border border-sage-300 rounded-full px-5 py-2.5 font-semibold hover:bg-sage-50 active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100 transition-all duration-150"
          >
            {saving ? "Saving…" : "Save Order"}
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || saving || lineCount === 0}
            className="bg-gradient-to-b from-crate-700 to-crate-800 text-white rounded-full px-5 py-2.5 text-sm font-semibold hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100 shadow-md shadow-crate-800/20 transition-all duration-150"
          >
            {submitting ? "Submitting…" : "Submit Order"}
          </button>
        </div>
      </div>
    </div>
  );
}
