import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { Product, fetchProducts } from "../../api/orders";
import {
  ExcelPricePreview,
  LastPrice,
  PriceWindow,
  downloadPriceTemplate,
  fetchLastPrices,
  fetchPriceWindow,
  fetchMyPrices,
  previewPriceExcel,
  submitPrices,
} from "../../api/pricing";
import { CategoryBadge } from "../shared/ui/CategoryBadge";
import PriceExcelPreviewModal from "./PriceExcelPreviewModal";
import { ProductPromotion } from "../shared/ui/PromotionBadge";
import { ONE_DECIMAL_STEP, formatOneDecimal, isOneDecimal } from "../shared/oneDecimal";

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

const outlineButton =
  "border border-sage-300 text-crate-800 rounded-full px-4 py-2 text-sm font-medium hover:bg-sage-50 active:scale-[0.98] disabled:opacity-40 disabled:hover:bg-transparent transition-all duration-150";

function TemplateDownloadButton() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function handleClick() {
    setError(null);
    setBusy(true);
    try {
      await downloadPriceTemplate();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not download the price template.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <span className="inline-flex items-center gap-2">
      <button onClick={handleClick} disabled={busy} className={outlineButton}>
        {busy ? "Downloading…" : "Download Excel template"}
      </button>
      {error && <span className="text-tomato-600 text-xs">{error}</span>}
    </span>
  );
}

export default function PriceForm({ onSubmitted }: { onSubmitted: () => void }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [window_, setWindow] = useState<PriceWindow | null>(null);
  const [prices, setPrices] = useState<Record<number, string>>({});
  const [lastPrices, setLastPrices] = useState<Record<number, LastPrice>>({});
  // Product IDs a real photo was found for, discovered by silently
  // preloading every product's image once products are known (below) —
  // this decides whether hovering an item's name can pop anything up at
  // all, rather than trying and failing on every hover.
  const [hasImage, setHasImage] = useState<Set<number>>(new Set());
  // The single floating preview, positioned in viewport coordinates
  // (not relative to the scrolling list) so it's never clipped by the
  // list's own overflow — see showPreview/hidePreview below.
  const [preview, setPreview] = useState<{ productCode: string; top: number; left: number } | null>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string>("ALL");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  // Excel upload: the parsed file waiting for the supplier to confirm.
  const fileInput = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [excel, setExcel] = useState<{ fileName: string; preview: ExcelPricePreview } | null>(null);
  const [excelSubmitting, setExcelSubmitting] = useState(false);
  const [excelError, setExcelError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [p, w] = await Promise.all([fetchProducts(), fetchPriceWindow()]);
        if (cancelled) return;
        setProducts(p);
        setWindow(w);

        const mine = await fetchMyPrices(w.delivery_date);
        if (cancelled) return;

        // Last price ever quoted per product, regardless of date. Also
        // doubles as the "new delivery date" fallback below: when this
        // date has no submission yet, it's necessarily the supplier's
        // most recent earlier one.
        let last: LastPrice[] = [];
        try {
          last = await fetchLastPrices();
          if (cancelled) return;
        } catch {
          // Non-critical — the form still works fine without this reference.
        }
        const lastMap: Record<number, LastPrice> = {};
        for (const lp of last) lastMap[lp.product_id] = lp;
        setLastPrices(lastMap);

        // Pre-fill priority: this delivery date's own submission first;
        // otherwise carry forward the supplier's latest previous price as
        // a starting default. Either way these are just starting values —
        // nothing is "submitted" for this date until Submit is clicked.
        const prefill: Record<number, string> = {};
        for (const mp of mine) prefill[mp.product_id] = String(mp.price);
        for (const lp of last) {
          if (!(lp.product_id in prefill)) prefill[lp.product_id] = String(lp.price);
        }
        setPrices(prefill);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load the price form.");
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
    () => Object.values(prices).filter((v) => parseFloat(v) > 0).length,
    [prices]
  );

  function setPrice(productId: number, value: string) {
    if (!isOneDecimal(value)) return; // e.g. 5.71 — the second decimal must be 0
    setPrices((prev) => ({ ...prev, [productId]: value }));
  }

  function clearAll() {
    setPrices({});
  }

  function shortDate(iso: string): string {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
  }

  async function handleSubmit() {
    setError(null);
    const entries = Object.entries(prices)
      .map(([productId, price]) => ({ product_id: Number(productId), price: parseFloat(price) }))
      .filter((e) => e.price > 0);

    if (entries.length === 0) {
      setError("Enter a price for at least one product.");
      return;
    }

    setSubmitting(true);
    try {
      await submitPrices(entries);
      setSuccess(true);
      onSubmitted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit prices. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleExcelChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // so choosing the same file again still fires onChange
    if (!file) return;
    setUploadError(null);
    setUploading(true);
    try {
      const preview = await previewPriceExcel(file);
      setExcelError(null);
      setExcel({ fileName: file.name, preview });
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Could not read that Excel file. Please try again.");
    } finally {
      setUploading(false);
    }
  }

  function excelEntries() {
    return (excel?.preview.lines ?? [])
      .filter((l) => !l.error && l.product_id !== null && l.price !== null)
      .map((l) => ({ product_id: l.product_id as number, price: l.price as number }));
  }

  async function handleExcelSubmit() {
    const entries = excelEntries();
    if (entries.length === 0) return;
    setExcelError(null);
    setExcelSubmitting(true);
    try {
      await submitPrices(entries);
      const next: Record<number, string> = {};
      for (const e of entries) next[e.product_id] = String(e.price);
      setPrices(next);
      setExcel(null);
      setSuccess(true);
      onSubmitted();
    } catch (err) {
      setExcelError(err instanceof ApiError ? err.message : "Could not submit prices. Please try again.");
    } finally {
      setExcelSubmitting(false);
    }
  }

  function handleExcelLoadIntoForm() {
    const next: Record<number, string> = {};
    for (const e of excelEntries()) next[e.product_id] = String(e.price);
    setPrices(next);
    setSearch("");
    setCategory("ALL");
    setExcel(null);
  }

  if (loading) {
    return (
      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 p-8 text-crate-800/40 text-sm text-center">
        Loading products…
      </div>
    );
  }

  if (window_ && !window_.is_open) {
    return (
      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 p-6">
        <p className="text-crate-800 font-semibold">Price submission is closed right now.</p>
        <p className="text-crate-800/60 text-sm mt-1">
          Suppliers can submit prices on {window_.submission_days_label} only, before the daily
          cutoff of {window_.cutoff_time}.
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <TemplateDownloadButton />
          <span className="text-xs text-crate-800/50">Fill it in now and upload it when submission opens.</span>
        </div>
      </div>
    );
  }

  if (success) {
    return (
      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 p-6">
        <p className="text-crate-700 font-semibold">Prices submitted successfully.</p>
        <p className="text-crate-800/60 text-sm mt-1">
          They apply to delivery on {window_ ? formatDate(window_.delivery_date) : "today"}.
          You can still adjust them before the {window_?.cutoff_time} cutoff.
        </p>
        <button
          onClick={() => setSuccess(false)}
          className="mt-4 text-sm text-crate-700 border border-sage-300 rounded-full px-4 py-1.5 hover:bg-sage-50 transition-colors duration-150"
        >
          Back to price entry
        </button>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 overflow-hidden">
      {previewPopup}
      {excel && (
        <PriceExcelPreviewModal
          fileName={excel.fileName}
          preview={excel.preview}
          deliveryDateLabel={window_ ? formatDate(window_.delivery_date) : null}
          submitting={excelSubmitting}
          error={excelError}
          onSubmit={handleExcelSubmit}
          onLoadIntoForm={handleExcelLoadIntoForm}
          onClose={() => setExcel(null)}
        />
      )}
      <div className="p-6 border-b border-sage-100">
        {window_ && (
          <p className="text-sm text-crate-800/70">
            Pricing for delivery on <span className="font-medium text-crate-800">{formatDate(window_.delivery_date)}</span>{" "}
            &middot; closes at {window_.cutoff_time} today &middot; you can resubmit to update a price
            before then
          </p>
        )}
        <div className="mt-4 rounded-xl border border-dashed border-sage-300 bg-sage-50/50 p-4 flex flex-col sm:flex-row sm:items-center gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-crate-800">Prefer Excel?</p>
            <p className="text-xs text-crate-800/55 mt-0.5">
              Download the template, fill in the Price column (leave blank for products you don't supply), then
              upload it here.
            </p>
            {uploadError && <p className="text-xs text-tomato-600 mt-1.5">{uploadError}</p>}
          </div>
          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <TemplateDownloadButton />
            <input
              ref={fileInput}
              type="file"
              accept=".xlsx,.xls,.csv"
              className="hidden"
              onChange={handleExcelChosen}
            />
            <button onClick={() => fileInput.current?.click()} disabled={uploading} className={outlineButton}>
              {uploading ? "Reading file…" : "Upload Excel"}
            </button>
          </div>
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
        </div>
      </div>

      <div className="max-h-[28rem] overflow-y-auto divide-y divide-sage-100">
        {filtered.length === 0 && (
          <p className="p-6 text-sm text-crate-800/35 text-center">No products match your search.</p>
        )}
        {filtered.map((p) => {
          const last = lastPrices[p.id];
          return (
            <div key={p.id} className="flex items-center justify-between px-6 py-3 hover:bg-sage-50/50 transition-colors duration-100">
              <div className="min-w-0">
                <div className="flex items-center gap-2 min-w-0">
                  <p
                    className={`text-sm text-crate-950 truncate w-fit ${hasImage.has(p.id) ? "cursor-pointer" : ""}`}
                    onMouseEnter={(e) => hasImage.has(p.id) && showPreview(p.id, e.currentTarget)}
                    onMouseLeave={hidePreview}
                  >
                    {p.description}
                  </p>
                  <ProductPromotion productId={p.id} className="shrink-0" />
                </div>
                <div className="flex items-center flex-wrap gap-1.5 mt-0.5">
                  <span className="text-xs text-crate-800/40">
                    {p.product_code}
                    {p.subcategory ? ` · ${p.subcategory}` : ""}
                    {last && (
                      <span className="text-crate-800/30">
                        {" "}
                        &middot; last: Rs. {last.price.toFixed(2)} ({shortDate(last.delivery_date)})
                      </span>
                    )}
                  </span>
                  <CategoryBadge name={p.category_name} />
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0 ml-4">
                <span className="text-xs text-crate-800/40">Rs.</span>
                <input
                  type="number"
                  min="0"
                  step={ONE_DECIMAL_STEP}
                  placeholder="0.00"
                  value={prices[p.id] ?? ""}
                  onChange={(e) => setPrice(p.id, e.target.value)}
                  onBlur={(e) => {
                    const v = formatOneDecimal(e.target.value);
                    if (v !== e.target.value) setPrice(p.id, v);
                  }}
                  className="w-24 border border-sage-300 bg-sage-50/60 rounded-full px-3 py-1.5 text-sm text-right text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
                />
                <span className="text-xs text-crate-800/40 w-10">/{p.unit_code}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="p-6 border-t border-sage-100 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <p className="text-sm text-crate-800/60">
            {lineCount} product{lineCount === 1 ? "" : "s"} with a price entered
          </p>
        </div>
        <div className="flex items-center gap-3">
          {error && <p className="text-tomato-600 text-sm">{error}</p>}
          <button
            onClick={clearAll}
            disabled={lineCount === 0}
            title="Clears the values shown on this form only — does not affect anything already submitted."
            className="border border-sage-300 text-crate-800/70 rounded-full px-4 py-2.5 text-sm font-medium hover:bg-sage-50 active:scale-[0.98] disabled:opacity-40 disabled:hover:bg-transparent transition-all duration-150"
          >
            Clear All
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || lineCount === 0}
            className="bg-gradient-to-b from-crate-700 to-crate-800 text-white rounded-full px-5 py-2.5 text-sm font-semibold hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100 shadow-md shadow-crate-800/20 transition-all duration-150"
          >
            {submitting ? "Submitting…" : "Submit Prices"}
          </button>
        </div>
      </div>
    </div>
  );
}
