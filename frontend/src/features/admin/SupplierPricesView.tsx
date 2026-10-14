import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import {
  AdminSupplierPrice,
  fetchAllPrices,
  fetchLastReferencePrices,
  fetchPriceWindow,
  fetchReferencePrices,
  setAdjustedPrice,
} from "../../api/pricing";
import { sendForApproval, withdrawSheet } from "../../api/priceApprovals";
import { compareProductDisplayOrder } from "../../api/orders";
import { Supplier, fetchSuppliers } from "../../api/suppliers";
import { SkeletonTable } from "../shared/ui/Skeleton";
import { IconTag } from "../shared/Icons";
import { PriceAnswerLabel, RowApprovalBadge } from "../shared/PriceSheetParts";
import { ConfirmDialog } from "../shared/ui/Modal";
import { ProductPromotion } from "../shared/ui/PromotionBadge";
import SupplierColumnFilter, { ColumnFilter, FILTER_LABELS, SortDir, cellMatches } from "./SupplierColumnFilter";

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
  // Per supplier column: sending a sheet for approval / withdrawing one.
  const [sendAllState, setSendAllState] = useState<Record<number, SendState>>({});
  const [sendError, setSendError] = useState<Record<number, string>>({});
  // Bumped to refetch every row — after sending/withdrawing a sheet, or an
  // edit that voided one (which changes other cells' status too).
  const [reloadKey, setReloadKey] = useState(0);
  // Adjusted-price saves still in flight, so "Send for approval" (clicking
  // it blurs the input, which starts a save) waits for them first.
  const savesInFlight = useRef<Set<Promise<void>>>(new Set());
  // Editing a price the supplier has signed (or is about to) cancels that
  // whole sheet — confirm first.
  const [confirmEdit, setConfirmEdit] = useState<{ row: AdminSupplierPrice; raw: string } | null>(null);

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

  // Frozen-column left offset for Keells Price, measured from the real
  // rendered width of the Item header cell rather than hardcoded, so it
  // stays aligned however the table lays the Item column out.
  const itemHeadRef = useRef<HTMLTableCellElement>(null);
  const [stickyOffsets, setStickyOffsets] = useState({ keells: 0 });

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
  }, [deliveryDate, supplierId, reloadKey]);

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

  // Excel-style column filters/sort (funnel button in each supplier's
  // header): they narrow and order the ROWS by that supplier's cells, while
  // every supplier's columns stay visible. Several columns can be filtered
  // at once (all must match). productRows stays unfiltered — the header
  // counts and "Send for approval" work on every item.
  const [colFilters, setColFilters] = useState<Record<number, ColumnFilter>>({});
  const [colSort, setColSort] = useState<{ supplierId: number; dir: SortDir } | null>(null);
  useEffect(() => {
    setColFilters({});
    setColSort(null);
  }, [deliveryDate]);

  const visibleRows = useMemo(() => {
    const active = Object.entries(colFilters).map(([id, f]) => [Number(id), f] as const);
    let list = active.length
      ? productRows.filter((p) => active.every(([id, f]) => cellMatches(f, p.cells.get(id))))
      : productRows;
    if (colSort) {
      const { supplierId, dir } = colSort;
      // Items this supplier didn't price go to the bottom, in their usual order.
      list = [...list].sort((a, b) => {
        const pa = a.cells.get(supplierId)?.price;
        const pb = b.cells.get(supplierId)?.price;
        if (pa === undefined || pb === undefined) return (pa === undefined ? 1 : 0) - (pb === undefined ? 1 : 0);
        return dir === "asc" ? pa - pb : pb - pa;
      });
    }
    return list;
  }, [productRows, colFilters, colSort]);

  const filtersActive = Object.keys(colFilters).length > 0 || colSort !== null;

  function setColumnFilter(supplierId: number, f: ColumnFilter | undefined) {
    setColFilters((prev) => {
      const next = { ...prev };
      if (f) next[supplierId] = f;
      else delete next[supplierId];
      return next;
    });
  }

  const supplierCount = supplierColumns.length;

  useLayoutEffect(() => {
    function measure() {
      const itemWidth = itemHeadRef.current?.offsetWidth ?? 0;
      setStickyOffsets((prev) => (prev.keells === itemWidth ? prev : { keells: itemWidth }));
    }
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [productRows, supplierColumns]);

  async function saveAdjustedPrice(row: AdminSupplierPrice, raw: string, confirmed = false) {
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
    const onLiveSheet = row.approval_status === "APPROVED" || row.approval_status === "PENDING";
    if (onLiveSheet && !confirmed) {
      setConfirmEdit({ row, raw });
      return;
    }
    setCellState((s) => ({ ...s, [row.id]: "saving" }));
    const save = (async () => {
      try {
        const result = await setAdjustedPrice(row.id, value);
        if (onLiveSheet) {
          // The whole sheet was voided, so other cells changed status too.
          setReloadKey((k) => k + 1);
        } else {
          setRows((prev) =>
            prev.map((r) =>
              r.id === row.id
                ? {
                    ...r,
                    adjusted_price: result.adjusted_price,
                    sent_to_supplier: false,
                    approval_status: result.adjusted_price === null ? null : "DRAFT",
                    revision_id: null,
                    rejection_reason: null,
                    counter_price: null,
                  }
                : r
            )
          );
        }
        setCellState((s) => ({ ...s, [row.id]: "saved" }));
        setTimeout(() => {
          setCellState((s) => (s[row.id] === "saved" ? { ...s, [row.id]: "idle" } : s));
        }, 1500);
      } catch (err) {
        setCellState((s) => ({ ...s, [row.id]: "error" }));
      }
    })();
    savesInFlight.current.add(save);
    await save;
    savesInFlight.current.delete(save);
  }

  function cellsForSupplier(supplierId: number): AdminSupplierPrice[] {
    const out: AdminSupplierPrice[] = [];
    for (const p of productRows) {
      const cell = p.cells.get(supplierId);
      if (cell) out.push(cell);
    }
    return out;
  }

  // Adjusted prices for a supplier that aren't agreed or waiting yet — what
  // "Send for approval" puts on the new sheet (the backend also folds in
  // anything still awaiting signature). Counts a typed-but-unsaved value
  // too, since clicking the button saves it first.
  function unsentCellsForSupplier(supplierId: number): AdminSupplierPrice[] {
    return cellsForSupplier(supplierId).filter((cell) => {
      const typed = drafts[cell.id]?.trim() ?? "";
      const changedLocally = typed !== "" && Number(typed) !== cell.adjusted_price;
      return changedLocally || cell.approval_status === "DRAFT" || cell.approval_status === "REJECTED";
    });
  }

  async function handleSendForApproval(supplierId: number) {
    setSendAllState((s) => ({ ...s, [supplierId]: "sending" }));
    setSendError((e) => ({ ...e, [supplierId]: "" }));
    await Promise.allSettled(Array.from(savesInFlight.current));
    try {
      await sendForApproval(supplierId, deliveryDate);
      setSendAllState((s) => ({ ...s, [supplierId]: "idle" }));
      setReloadKey((k) => k + 1);
    } catch (err) {
      setSendAllState((s) => ({ ...s, [supplierId]: "error" }));
      setSendError((e) => ({
        ...e,
        [supplierId]: err instanceof ApiError ? err.message : "Could not send — try again.",
      }));
    }
  }

  async function handleWithdraw(supplierId: number, revisionId: number) {
    setSendAllState((s) => ({ ...s, [supplierId]: "sending" }));
    setSendError((e) => ({ ...e, [supplierId]: "" }));
    try {
      await withdrawSheet(revisionId);
      setSendAllState((s) => ({ ...s, [supplierId]: "idle" }));
      setReloadKey((k) => k + 1);
    } catch (err) {
      setSendAllState((s) => ({ ...s, [supplierId]: "error" }));
      setSendError((e) => ({
        ...e,
        [supplierId]: err instanceof ApiError ? err.message : "Could not withdraw — try again.",
      }));
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
            {filtersActive && visibleRows.length !== productRows.length ? `${visibleRows.length} of ` : ""}
            {productRows.length} item{productRows.length === 1 ? "" : "s"} · {supplierCount} supplier
            {supplierCount === 1 ? "" : "s"}
          </div>
        </div>
        {deliveryDate && (
          <p className="text-xs text-crate-800/40 mt-3">
            Showing quotes for {formatDate(deliveryDate)}. Set an Adjusted Price for one or more items, then click{" "}
            <span className="font-medium text-crate-700">Send for approval</span> at the top of that supplier's
            column — they get one price sheet and approve (e-sign) or reject each item. A rejected item can come
            back with the supplier's own final price, which then applies. If you adjust a rejected item and send it
            again, it goes as your final price: the supplier can only approve or reject it. Until they respond, their
            own quote is the price that applies, and it stays that way if they don't respond before the delivery date.
          </p>
        )}
      </div>

      {filtersActive && (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-crate-800/50 font-semibold uppercase tracking-wide">Filters</span>
          {Object.entries(colFilters).map(([id, f]) => (
            <button
              key={`f-${id}`}
              onClick={() => setColumnFilter(Number(id), undefined)}
              className="rounded-full bg-crate-700 text-white pl-3 pr-2 py-1 font-semibold hover:bg-crate-800"
              title="Remove this filter"
            >
              {supplierColumns.find((c) => c.id === Number(id))?.name ?? "Supplier"}: {FILTER_LABELS[f]} ×
            </button>
          ))}
          {colSort && (
            <button
              onClick={() => setColSort(null)}
              className="rounded-full bg-crate-700 text-white pl-3 pr-2 py-1 font-semibold hover:bg-crate-800"
              title="Remove this sort"
            >
              Sorted by {supplierColumns.find((c) => c.id === colSort.supplierId)?.name ?? "supplier"}:{" "}
              {colSort.dir === "asc" ? "low → high" : "high → low"} ×
            </button>
          )}
          <button
            onClick={() => {
              setColFilters({});
              setColSort(null);
            }}
            className="text-crate-700 font-semibold hover:underline"
          >
            Clear all
          </button>
        </div>
      )}

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
          <table className="text-sm border-collapse">
            <thead className="sticky top-0 z-20 bg-white">
              <tr className="bg-white text-crate-800/40 text-left text-xs uppercase tracking-wide border-b border-sage-100">
                <th
                  ref={itemHeadRef}
                  className="sticky left-0 z-30 bg-white px-4 py-2.5 font-medium align-bottom w-60 min-w-[15rem] max-w-[15rem]"
                >
                  Item
                </th>
                <th
                  rowSpan={2}
                  style={{ left: stickyOffsets.keells }}
                  className="sticky z-30 bg-green-100 px-4 py-2.5 text-center border-l border-r border-sage-200 align-middle normal-case tracking-normal shadow-[4px_0_6px_-4px_rgba(21,56,38,0.12)] min-w-[8rem]"
                >
                  <span className="font-semibold text-crate-800 text-sm">Keells Price</span>
                  <p className="text-[10px] text-crate-800/35 font-normal normal-case mt-0.5">
                    Edit on Keells Prices page
                  </p>
                </th>
                {supplierColumns.map((s) => {
                  const unsentCount = unsentCellsForSupplier(s.id).length;
                  const allState = sendAllState[s.id] ?? "idle";
                  const busy = allState === "sending";
                  const cells = cellsForSupplier(s.id);
                  const pendingCell = cells.find((c) => c.approval_status === "PENDING");
                  const approvedCount = cells.filter((c) => c.approval_status === "APPROVED").length;
                  const rejectedCells = cells.filter((c) => c.approval_status === "REJECTED");
                  const rejectedCell = rejectedCells[0];
                  return (
                    <th
                      key={s.id}
                      colSpan={2}
                      className={`px-4 py-2.5 text-center border-l border-sage-100 normal-case tracking-normal ${
                        colFilters[s.id] || colSort?.supplierId === s.id ? "bg-crate-700/10" : ""
                      }`}
                    >
                      <div className="flex flex-col items-center gap-1.5">
                        <span className="flex items-center gap-1.5">
                          <span className="font-semibold text-crate-800 text-sm">{s.name}</span>
                          <SupplierColumnFilter
                            supplierName={s.name}
                            filter={colFilters[s.id]}
                            sortDir={colSort?.supplierId === s.id ? colSort.dir : undefined}
                            onFilter={(f) => setColumnFilter(s.id, f)}
                            onSort={(dir) => setColSort(dir ? { supplierId: s.id, dir } : null)}
                          />
                        </span>
                        <button
                          onClick={() => handleSendForApproval(s.id)}
                          disabled={unsentCount === 0 || busy}
                          className={`text-[11px] rounded-full px-3 py-1 font-semibold transition-colors duration-150 ${
                            unsentCount === 0
                              ? "bg-sage-100 text-crate-800/30 cursor-default"
                              : "bg-crate-700 text-white hover:bg-crate-800"
                          } disabled:opacity-60`}
                        >
                          {busy
                            ? "Working…"
                            : unsentCount === 0
                            ? "Send for approval"
                            : `Send for approval (${unsentCount})`}
                        </button>
                        {pendingCell && pendingCell.revision_id !== null && (
                          <span className="text-[10px] text-[#8A5A0D] font-normal">
                            Awaiting signature ·{" "}
                            <button
                              onClick={() => handleWithdraw(s.id, pendingCell.revision_id!)}
                              disabled={busy}
                              className="underline decoration-dotted hover:text-tomato-600 disabled:opacity-40"
                            >
                              Withdraw
                            </button>
                          </span>
                        )}
                        {approvedCount > 0 && (
                          <span className="text-[10px] text-crate-700 font-normal">✓ {approvedCount} approved</span>
                        )}
                        {rejectedCell && (
                          <span
                            className="text-[10px] text-tomato-600 font-normal max-w-[14rem] truncate"
                            title={rejectedCell.rejection_reason ?? undefined}
                          >
                            ✗ {rejectedCells.length} rejected
                            {rejectedCell.rejection_reason ? `: ${rejectedCell.rejection_reason}` : ""}
                          </span>
                        )}
                        {allState === "error" && sendError[s.id] && (
                          <span className="text-[10px] text-tomato-600 font-normal max-w-[14rem]">{sendError[s.id]}</span>
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
              {visibleRows.length === 0 && (
                <tr>
                  <td colSpan={2 + supplierCount * 2} className="sticky left-0 px-4 py-10 text-left text-sm text-crate-800/50">
                    No items match these filters.{" "}
                    <button
                      onClick={() => {
                        setColFilters({});
                        setColSort(null);
                      }}
                      className="text-crate-700 font-semibold hover:underline"
                    >
                      Clear filters
                    </button>
                  </td>
                </tr>
              )}
              {visibleRows.map((p) => (
                <tr key={p.product_id}>
                  <td
                    title={`${p.description} ${p.code}`}
                    className="sticky left-0 z-10 bg-white px-4 py-2.5 text-crate-950 w-60 min-w-[15rem] max-w-[15rem]"
                  >
                    <span className="block break-words">{p.description}</span>
                    <span className="flex flex-wrap items-center gap-1.5 mt-0.5">
                      <span className="text-crate-800/35 text-xs">{p.code}</span>
                      <ProductPromotion productId={p.product_id} />
                      {(["EXPIRED", "REJECTED"] as const).map((status) => {
                        const who = [...p.cells.values()]
                          .filter((c) => c.approval_status === status)
                          .map((c) => c.supplier_name);
                        return who.length > 0 ? <PriceAnswerLabel key={status} status={status} suppliers={who} /> : null;
                      })}
                    </span>
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

                          {cell.adjusted_price !== null && (
                            <span
                              title={cell.approval_status === "REJECTED" ? cell.rejection_reason ?? undefined : undefined}
                            >
                              <RowApprovalBadge status={cell.approval_status} />
                            </span>
                          )}
                          {cell.approval_status === "REJECTED" && cell.counter_price !== null && (
                            <span
                              className="text-[10px] text-tomato-600 whitespace-nowrap"
                              title="The supplier rejected your price and gave this final price instead"
                            >
                              Supplier: {cell.counter_price.toFixed(2)}
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

      <ConfirmDialog
        open={confirmEdit !== null}
        onClose={() => {
          if (confirmEdit) {
            const { row } = confirmEdit;
            setDrafts((d) => ({ ...d, [row.id]: row.adjusted_price !== null ? String(row.adjusted_price) : "" }));
          }
          setConfirmEdit(null);
        }}
        onConfirm={() => {
          if (confirmEdit) saveAdjustedPrice(confirmEdit.row, confirmEdit.raw, true);
          setConfirmEdit(null);
        }}
        title={
          confirmEdit?.row.approval_status === "APPROVED"
            ? "Change a price the supplier has signed?"
            : "Change a price awaiting signature?"
        }
        description={
          confirmEdit
            ? `${confirmEdit.row.supplier_name}'s whole price sheet for this date will be cancelled and its prices go back to draft. You'll need to send it for approval again — until they sign, their own quoted prices apply.`
            : undefined
        }
        confirmLabel="Change price"
        danger
      />
    </div>
  );
}
