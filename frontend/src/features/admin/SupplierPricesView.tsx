import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import {
  AdminSupplierPrice,
  fetchAllPrices,
  fetchLastReferencePrices,
  fetchPriceWindow,
  fetchReferencePrices,
  sendAdjustedPrice,
  setAdjustedPrice,
  unsendAdjustedPrice,
} from "../../api/pricing";
import { compareProductDisplayOrder } from "../../api/orders";
import { Supplier, fetchSuppliers } from "../../api/suppliers";
import { SkeletonTable } from "../shared/ui/Skeleton";
import { IconTag } from "../shared/Icons";

function formatDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

function todayIso(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

type CellState = "idle" | "saving" | "saved" | "error";
type SendState = "idle" | "sending" | "error";

export default function SupplierPricesView() {
  const [deliveryDate, setDeliveryDate] = useState<string>("");
  // Keells reference prices are entered/synced against TODAY's date (see
  // AdminKeellsPrices.tsx), not the supplier submission cycle's delivery
  // date above — these are two different, independent date conventions,
  // so the Keells Price column below must look itself up by today's date
  // rather than reusing `deliveryDate`, or it'll show nothing on any day
  // that isn't also the current cycle's delivery date.
  const [keellsDate] = useState<string>(todayIso());
  const [supplierId, setSupplierId] = useState<number | "">("");
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [rows, setRows] = useState<AdminSupplierPrice[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Draft text for adjusted-price inputs, keyed by supplier_price row id,
  // so typing doesn't fight with the fetched value until it's saved.
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [cellState, setCellState] = useState<Record<number, CellState>>({});
  const [sendState, setSendState] = useState<Record<number, SendState>>({});
  const [sendAllState, setSendAllState] = useState<Record<number, SendState>>({});

  // Keells reference prices, keyed by product_id — independent of the
  // supplier/adjusted-price drafts above, and independent of which
  // supplier filter is active.
  const [referenceDrafts, setReferenceDrafts] = useState<Record<number, string>>({});
  // The most recent Keells price ever entered per product, any date —
  // used to pre-fill a blank date instead of making Admin retype it.
  const [lastReferencePrices, setLastReferencePrices] = useState<
    Record<number, { price: number; delivery_date: string }>
  >({});
  // Product ids whose reference-price field is showing a carried-forward
  // value that has NOT been confirmed for the currently selected date yet
  // (no real row exists for this date until Admin interacts with the field).
  const [carriedForwardIds, setCarriedForwardIds] = useState<Set<number>>(new Set());

  // Frozen-column left offsets, measured from the real rendered widths of
  // the Item/Lowest Price header cells — table auto-layout doesn't honor a
  // hardcoded `width`, columns still grow to fit long item names, so a
  // static px offset drifts out of alignment with the actual columns.
  const itemHeadRef = useRef<HTMLTableCellElement>(null);
  const lowestHeadRef = useRef<HTMLTableCellElement>(null);
  const [stickyOffsets, setStickyOffsets] = useState({ lowest: 0, keells: 0 });

  useEffect(() => {
    fetchSuppliers().then(setSuppliers).catch(() => {});
    fetchPriceWindow()
      .then((w) => setDeliveryDate(w.current_cycle_delivery_date))
      .catch(() => {});
    fetchLastReferencePrices()
      .then((data) => {
        const next: Record<number, { price: number; delivery_date: string }> = {};
        for (const r of data) next[r.product_id] = { price: r.price, delivery_date: r.delivery_date };
        setLastReferencePrices(next);
      })
      .catch(() => {
        // Non-critical — carry-forward pre-fill just won't happen without this.
      });
  }, []);

  useEffect(() => {
    if (!deliveryDate) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchAllPrices({ deliveryDate, supplierId: supplierId || undefined })
      .then((data) => {
        if (cancelled) return;
        setRows(data);
        const nextDrafts: Record<number, string> = {};
        for (const r of data) {
          nextDrafts[r.id] = r.adjusted_price !== null ? String(r.adjusted_price) : "";
        }
        setDrafts(nextDrafts);
        setCellState({});
        setSendState({});
        setSendAllState({});
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load supplier prices.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [deliveryDate, supplierId]);

  useEffect(() => {
    let cancelled = false;
    fetchReferencePrices(keellsDate)
      .then((data) => {
        if (cancelled) return;
        const next: Record<number, string> = {};
        const confirmedIds = new Set<number>();
        for (const r of data) {
          next[r.product_id] = String(r.price);
          confirmedIds.add(r.product_id);
        }
        // Pre-fill anything with no entry for today, using the most
        // recent value we know for that product — Admin sees a number
        // immediately instead of a blank field.
        const nextCarried = new Set<number>();
        for (const [productIdStr, last] of Object.entries(lastReferencePrices)) {
          const productId = Number(productIdStr);
          if (!confirmedIds.has(productId)) {
            next[productId] = String(last.price);
            nextCarried.add(productId);
          }
        }
        setReferenceDrafts(next);
        setCarriedForwardIds(nextCarried);
      })
      .catch(() => {
        // Non-critical reference data — the main pricing table still works without it.
      });
    return () => {
      cancelled = true;
    };
  }, [keellsDate, lastReferencePrices]);

  const q = search.trim().toLowerCase();

  // Pivot: one row per product, one pair of columns (Supplier Price /
  // Adjusted Price) per supplier that quoted anything for this date.
  const supplierColumns = useMemo(() => {
    const seen = new Map<number, string>();
    for (const r of rows) seen.set(r.supplier_id, r.supplier_name);
    return Array.from(seen.entries())
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [rows]);

  const productRows = useMemo(() => {
    const byProduct = new Map<
      number,
      {
        product_id: number;
        description: string;
        code: string;
        category_name: string;
        cells: Map<number, AdminSupplierPrice>;
      }
    >();
    for (const r of rows) {
      if (!byProduct.has(r.product_id)) {
        byProduct.set(r.product_id, {
          product_id: r.product_id,
          description: r.product_description,
          code: r.product_code,
          category_name: r.category_name,
          cells: new Map(),
        });
      }
      byProduct.get(r.product_id)!.cells.set(r.supplier_id, r);
    }
    let list = Array.from(byProduct.values());
    if (q) {
      list = list.filter(
        (p) => p.description.toLowerCase().includes(q) || p.code.toLowerCase().includes(q)
      );
    }
    return list.sort(compareProductDisplayOrder);
  }, [rows, q]);

  // The winning (lowest-price) supplier cell(s) per product, for the summary
  // column — reuses the is_lowest_for_product flag the backend already
  // computes rather than re-deriving it here. The backend flags every
  // supplier tied at the lowest price, so this can return more than one
  // cell — all of them share the same price.
  function bestCellsFor(p: { cells: Map<number, AdminSupplierPrice> }): AdminSupplierPrice[] {
    return Array.from(p.cells.values()).filter((cell) => cell.is_lowest_for_product);
  }

  // Same idea, for the next distinct price tier below the lowest — see
  // pricing_service.list_all_prices for why a tie at the lowest price
  // doesn't count as a second tier.
  function secondLowestCellFor(p: { cells: Map<number, AdminSupplierPrice> }): AdminSupplierPrice | undefined {
    for (const cell of p.cells.values()) {
      if (cell.is_second_lowest_for_product) return cell;
    }
    return undefined;
  }

  const supplierCount = supplierColumns.length;

  useLayoutEffect(() => {
    function measure() {
      const itemWidth = itemHeadRef.current?.offsetWidth ?? 0;
      const lowestWidth = lowestHeadRef.current?.offsetWidth ?? 0;
      setStickyOffsets((prev) => {
        const next = { lowest: itemWidth, keells: itemWidth + lowestWidth };
        if (prev.lowest === next.lowest && prev.keells === next.keells) return prev;
        return next;
      });
    }
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [productRows, supplierColumns]);

  async function saveAdjustedPrice(row: AdminSupplierPrice, raw: string) {
    const trimmed = raw.trim();
    const value = trimmed === "" ? null : Number(trimmed);
    if (value !== null && (Number.isNaN(value) || value <= 0)) {
      setCellState((s) => ({ ...s, [row.id]: "error" }));
      return;
    }
    // No-op if unchanged.
    const current = row.adjusted_price;
    if ((current === null && value === null) || (current !== null && value === current)) {
      return;
    }
    setCellState((s) => ({ ...s, [row.id]: "saving" }));
    try {
      const result = await setAdjustedPrice(row.id, value);
      setRows((prev) =>
        prev.map((r) =>
          r.id === row.id
            ? { ...r, adjusted_price: result.adjusted_price, sent_to_supplier: result.sent_to_supplier }
            : r
        )
      );
      setCellState((s) => ({ ...s, [row.id]: "saved" }));
      setTimeout(() => {
        setCellState((s) => (s[row.id] === "saved" ? { ...s, [row.id]: "idle" } : s));
      }, 1500);
    } catch (err) {
      setCellState((s) => ({ ...s, [row.id]: "error" }));
    }
  }

  // Cells for a supplier that have a draft adjusted price typed in but
  // haven't been sent yet — what "Send All" for that supplier acts on.
  function pendingCellsForSupplier(supplierId: number): AdminSupplierPrice[] {
    const out: AdminSupplierPrice[] = [];
    for (const p of productRows) {
      const cell = p.cells.get(supplierId);
      if (cell && drafts[cell.id]?.trim() !== "" && !cell.sent_to_supplier) out.push(cell);
    }
    return out;
  }

  async function handleSendAll(supplierId: number) {
    const pending = pendingCellsForSupplier(supplierId);
    if (pending.length === 0) return;
    setSendAllState((s) => ({ ...s, [supplierId]: "sending" }));
    const results = await Promise.allSettled(pending.map((cell) => sendAdjustedPrice(cell.id)));
    const sentIds = new Set<number>();
    results.forEach((res, i) => {
      if (res.status === "fulfilled") sentIds.add(pending[i].id);
    });
    setRows((prev) =>
      prev.map((r) => (sentIds.has(r.id) ? { ...r, sent_to_supplier: true } : r))
    );
    setSendAllState((s) => ({ ...s, [supplierId]: sentIds.size === pending.length ? "idle" : "error" }));
  }

  async function handleUnsend(row: AdminSupplierPrice) {
    setSendState((s) => ({ ...s, [row.id]: "sending" }));
    try {
      const result = await unsendAdjustedPrice(row.id);
      setRows((prev) =>
        prev.map((r) => (r.id === row.id ? { ...r, sent_to_supplier: result.sent_to_supplier } : r))
      );
      setSendState((s) => ({ ...s, [row.id]: "idle" }));
    } catch (err) {
      setSendState((s) => ({ ...s, [row.id]: "error" }));
    }
  }

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 p-5">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-xs font-semibold text-crate-800/50 uppercase tracking-wide mb-1.5">
              Delivery Date
            </label>
            <input
              type="date"
              value={deliveryDate}
              onChange={(e) => setDeliveryDate(e.target.value)}
              className="border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-crate-800/50 uppercase tracking-wide mb-1.5">
              Supplier
            </label>
            <select
              value={supplierId}
              onChange={(e) => setSupplierId(e.target.value ? Number(e.target.value) : "")}
              className="border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm text-crate-950 min-w-[12rem] focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
            >
              <option value="">All suppliers</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.supplier_name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex-1 min-w-[10rem]">
            <label className="block text-xs font-semibold text-crate-800/50 uppercase tracking-wide mb-1.5">
              Search
            </label>
            <input
              type="text"
              placeholder="Item name or code…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
            />
          </div>

          <div className="text-xs text-crate-800/40 ml-auto text-right">
            {productRows.length} item{productRows.length === 1 ? "" : "s"} · {supplierCount} supplier
            {supplierCount === 1 ? "" : "s"}
          </div>
        </div>
        {deliveryDate && (
          <p className="text-xs text-crate-800/40 mt-3">
            Showing quotes for {formatDate(deliveryDate)}. Set an Adjusted Price for one or more items, then click{" "}
            <span className="font-medium text-crate-700">Send All</span> at the top of that supplier's column to
            push everything at once — until then it's a draft only you can see, and the supplier's original
            quote is never changed.
          </p>
        )}
      </div>

      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 overflow-auto max-h-[75vh]">
        {loading ? (
          <SkeletonTable rows={10} columns={5} />
        ) : error ? (
          <div className="p-6 text-tomato-600 text-sm">{error}</div>
        ) : productRows.length === 0 || supplierCount === 0 ? (
          <div className="py-12 text-center">
            <div className="mx-auto mb-3.5 w-11 h-11 rounded-full bg-sage-100 flex items-center justify-center text-crate-700/50">
              <IconTag width={20} height={20} />
            </div>
            <p className="text-sm font-semibold text-crate-800/70">No supplier prices submitted yet</p>
            <p className="text-xs text-crate-800/40 mt-1">Prices submitted for this delivery date will appear here.</p>
          </div>
        ) : (
          <table className="w-full text-sm border-collapse">
            <thead className="sticky top-0 z-20 bg-white">
              <tr className="bg-white text-crate-800/40 text-left text-xs uppercase tracking-wide border-b border-sage-100">
                <th
                  ref={itemHeadRef}
                  className="sticky left-0 z-30 bg-white px-4 py-2.5 font-medium align-bottom"
                >
                  Item
                </th>
                <th
                  ref={lowestHeadRef}
                  rowSpan={2}
                  style={{ left: stickyOffsets.lowest }}
                  className="sticky z-30 bg-yellow-100 px-4 py-2.5 text-center border-l border-sage-100 align-middle normal-case tracking-normal"
                >
                  <span className="font-semibold text-crate-800 text-sm">Lowest Price</span>
                  <p className="text-[10px] text-crate-800/35 font-normal normal-case mt-0.5">
                    Best supplier &amp; price
                  </p>
                </th>
                <th
                  rowSpan={2}
                  style={{ left: stickyOffsets.keells }}
                  className="sticky z-30 bg-green-100 px-4 py-2.5 text-center border-l border-r border-sage-200 align-middle normal-case tracking-normal shadow-[4px_0_6px_-4px_rgba(21,56,38,0.12)]"
                >
                  <span className="font-semibold text-crate-800 text-sm">Keells Price</span>
                  <p className="text-[10px] text-crate-800/35 font-normal normal-case mt-0.5">
                    Edit on Keells Prices page
                  </p>
                </th>
                {supplierColumns.map((s) => {
                  const pendingCount = pendingCellsForSupplier(s.id).length;
                  const allState = sendAllState[s.id] ?? "idle";
                  const sendingAll = allState === "sending";
                  return (
                    <th
                      key={s.id}
                      colSpan={2}
                      className="px-4 py-2.5 text-center border-l border-sage-100 normal-case tracking-normal"
                    >
                      <div className="flex flex-col items-center gap-1.5">
                        <span className="font-semibold text-crate-800 text-sm">{s.name}</span>
                        <button
                          onClick={() => handleSendAll(s.id)}
                          disabled={pendingCount === 0 || sendingAll}
                          className={`text-[11px] rounded-full px-3 py-1 font-semibold transition-colors duration-150 ${
                            pendingCount === 0
                              ? "bg-sage-100 text-crate-800/30 cursor-default"
                              : "bg-crate-700 text-white hover:bg-crate-800"
                          } disabled:opacity-60`}
                        >
                          {sendingAll ? "Sending…" : pendingCount === 0 ? "Send All" : `Send All (${pendingCount})`}
                        </button>
                        {allState === "error" && (
                          <span className="text-[10px] text-tomato-600">Some failed — try again</span>
                        )}
                      </div>
                    </th>
                  );
                })}
              </tr>
              <tr className="bg-white text-crate-800/40 text-left text-[11px] uppercase tracking-wide border-b border-sage-100">
                <th className="sticky left-0 z-30 bg-white px-4 pb-2 font-medium"></th>
                {supplierColumns.map((s) => (
                  <th key={`${s.id}-price`} className="px-3 pb-2 font-medium text-right border-l border-sage-100">
                    Supplier Price
                  </th>
                )).flatMap((priceHeader, i) => [
                  priceHeader,
                  <th key={`${supplierColumns[i].id}-adj`} className="px-3 pb-2 font-medium text-right bg-blue-100">
                    Adjusted Price
                  </th>,
                ])}
              </tr>
            </thead>
            <tbody className="divide-y divide-sage-100">
              {productRows.map((p) => (
                <tr key={p.product_id}>
                  <td
                    title={`${p.description} ${p.code}`}
                    className="sticky left-0 z-10 bg-white px-4 py-2.5 text-crate-950 whitespace-nowrap"
                  >
                    {p.description}
                    <span className="text-crate-800/35 text-xs ml-1.5">{p.code}</span>
                  </td>
                  <td
                    style={{ left: stickyOffsets.lowest }}
                    className="sticky z-10 bg-yellow-100 px-3 py-1.5 border-l border-sage-100"
                  >
                    {(() => {
                      const bestCells = bestCellsFor(p);
                      if (bestCells.length === 0) return <span className="text-sm text-crate-800/20">—</span>;
                      const best = bestCells[0];
                      const keells = referenceDrafts[p.product_id] ? Number(referenceDrafts[p.product_id]) : null;
                      const diff = keells !== null ? best.price - keells : null;
                      const secondBest = secondLowestCellFor(p);
                      const supplierNames = bestCells.map((c) => c.supplier_name).join(", ");
                      return (
                        <div className="flex flex-col items-center gap-0.5">
                          <span className="text-sm font-semibold text-crate-800">Rs. {best.price.toFixed(2)}</span>
                          <span className="text-[10px] text-crate-800/50 text-center">{supplierNames}</span>
                          {diff !== null && (
                            <span
                              className={`text-[10px] font-medium ${
                                diff <= 0 ? "text-crate-700" : "text-tomato-600"
                              }`}
                            >
                              Rs. {Math.abs(diff).toFixed(2)} {diff <= 0 ? "below" : "above"} Keells
                            </span>
                          )}
                          {secondBest && (
                            <span className="text-[10px] text-crate-800/35 border-t border-sage-200 mt-0.5 pt-0.5 w-full text-center">
                              2nd: Rs. {secondBest.price.toFixed(2)} ({secondBest.supplier_name})
                            </span>
                          )}
                        </div>
                      );
                    })()}
                  </td>
                  <td
                    style={{ left: stickyOffsets.keells }}
                    className="sticky z-10 bg-green-100 px-3 py-1.5 border-l border-r border-sage-200 shadow-[4px_0_6px_-4px_rgba(21,56,38,0.12)]"
                  >
                    <div className="flex flex-col items-center gap-0.5">
                      {referenceDrafts[p.product_id] ? (
                        <span className={`text-sm ${carriedForwardIds.has(p.product_id) ? "text-mango-600/90" : "text-crate-800/80"}`}>
                          Rs. {Number(referenceDrafts[p.product_id]).toFixed(2)}
                        </span>
                      ) : (
                        <span className="text-sm text-crate-800/20">—</span>
                      )}
                      {carriedForwardIds.has(p.product_id) && lastReferencePrices[p.product_id] && (
                        <span className="text-[9px] text-mango-600/70 leading-none">
                          from {new Date(lastReferencePrices[p.product_id].delivery_date + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" })}
                        </span>
                      )}
                    </div>
                  </td>
                  {supplierColumns.flatMap((s) => {
                    const cell = p.cells.get(s.id);
                    if (!cell) {
                      return [
                        <td
                          key={`${s.id}-price`}
                          className="px-3 py-2.5 text-right text-crate-800/25 border-l border-sage-100"
                        >
                          —
                        </td>,
                        <td key={`${s.id}-adj`} className="px-3 py-2.5 text-right text-crate-800/25 bg-blue-100">
                          —
                        </td>,
                      ];
                    }
                    const state = cellState[cell.id] ?? "idle";
                    const sending = (sendState[cell.id] ?? "idle") === "sending";
                    const sendErrored = (sendState[cell.id] ?? "idle") === "error";
                    const hasDraft = drafts[cell.id]?.trim() !== "";
                    return [
                      <td
                        key={`${s.id}-price`}
                        className={`px-3 py-2.5 text-right border-l border-sage-100 ${
                          cell.is_lowest_for_product
                            ? "bg-crate-700/5 font-semibold text-crate-800"
                            : "text-crate-800/80"
                        }`}
                      >
                        {cell.price.toFixed(2)}
                      </td>,
                      <td key={`${s.id}-adj`} className="px-2 py-1.5 bg-blue-100">
                        <div className="flex flex-col items-end gap-1">
                          <div className="flex items-center justify-end gap-1.5">
                            <input
                              type="number"
                              min="0"
                              step="0.01"
                              placeholder="—"
                              value={drafts[cell.id] ?? ""}
                              onChange={(e) => setDrafts((d) => ({ ...d, [cell.id]: e.target.value }))}
                              onBlur={(e) => saveAdjustedPrice(cell, e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                              }}
                              className={`w-20 border rounded-lg px-2 py-1 text-right text-sm bg-sage-50/60 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-colors duration-150 ${
                                state === "error" ? "border-tomato-500 ring-1 ring-tomato-500/30" : "border-sage-300"
                              }`}
                            />
                            {state === "saving" && <span className="text-[10px] text-crate-800/35">…</span>}
                            {state === "saved" && <span className="text-[10px] text-crate-700">✓</span>}
                            {state === "error" && <span className="text-[10px] text-tomato-600">!</span>}
                          </div>

                          {hasDraft && cell.sent_to_supplier && (
                            <div className="flex items-center gap-1">
                              <span className="text-[10px] uppercase tracking-wide bg-crate-700 text-white rounded-full px-2 py-0.5 font-semibold">
                                Sent
                              </span>
                              <button
                                onClick={() => handleUnsend(cell)}
                                disabled={sending}
                                className="text-[10px] text-crate-800/40 hover:text-tomato-600 underline decoration-dotted disabled:opacity-40 transition-colors duration-150"
                              >
                                Withdraw
                              </button>
                              {sendErrored && <span className="text-[10px] text-tomato-600">Failed</span>}
                            </div>
                          )}
                          {hasDraft && !cell.sent_to_supplier && (
                            <span className="text-[10px] text-crate-800/35">
                              Draft — use "Send All" above
                            </span>
                          )}
                        </div>
                      </td>,
                    ];
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
