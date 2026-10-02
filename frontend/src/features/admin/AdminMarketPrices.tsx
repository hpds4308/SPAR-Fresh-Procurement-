import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import {
  downloadLocalMarketExcel,
  fetchLocalMarketPrices,
  LocalMarketImportResult,
  LocalMarketReport,
  MarketRange,
  MARKETS,
  syncLocalMarketPrices,
  uploadLocalMarketBulletin,
} from "../../api/localMarketPrices";
import EmptyState from "../shared/EmptyState";
import { SkeletonTable } from "../shared/ui/Skeleton";
import { CategoryBadge } from "../shared/ui/CategoryBadge";
import { IconBranches } from "../shared/Icons";

function formatDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

function formatShortDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

function formatPrice(n: number): string {
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// HARTI quotes whole rupees, so "450 – 500" rather than "450.00 – 500.00".
function formatRangeEnd(n: number): string {
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

const DC_CODE_WIDTH = 90;

function MarketCells({ range }: { range: MarketRange | null }) {
  if (!range) {
    return (
      <>
        <td className="px-3 py-2.5 text-right text-crate-800/20 border-l border-sage-100">—</td>
        <td className="px-3 py-2.5 text-right text-crate-800/20">—</td>
      </>
    );
  }
  return (
    <>
      <td className="px-3 py-2.5 text-right whitespace-nowrap tabular-nums text-crate-800/60 border-l border-sage-100">
        {formatRangeEnd(range.min)} – {formatRangeEnd(range.max)}
      </td>
      <td className="px-3 py-2.5 text-right whitespace-nowrap tabular-nums text-crate-950">{formatPrice(range.average)}</td>
    </>
  );
}

// Prices here come only from HARTI's daily bulletin — "Fetch latest from
// HARTI", "Upload PDF", or the scheduled import (see backend
// harti_import_service.py) — and each import replaces that report date's
// prices in one shot, so there's nothing to type in by hand. Each
// market's Avg is the midpoint of its range; Final Avg is the mean of the
// markets that had a price, and is what Price History charts as "Local Market".
export default function AdminMarketPrices() {
  const [report, setReport] = useState<LocalMarketReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");

  const [busy, setBusy] = useState<"sync" | "upload" | "export" | null>(null);
  const [importResult, setImportResult] = useState<LocalMarketImportResult | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const latestRequest = useRef(0);

  async function load(reportDate?: string) {
    const requestId = ++latestRequest.current;
    setLoading(true);
    try {
      const data = await fetchLocalMarketPrices(reportDate);
      if (requestId !== latestRequest.current) return;
      setReport(data);
      setError(null);
    } catch (err) {
      if (requestId !== latestRequest.current) return;
      setError(err instanceof ApiError ? err.message : "Could not load local market prices.");
    } finally {
      if (requestId === latestRequest.current) setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function runImport(kind: "sync" | "upload", action: () => Promise<LocalMarketImportResult>) {
    setBusy(kind);
    setActionError(null);
    setImportResult(null);
    try {
      const result = await action();
      setImportResult(result);
      await load(result.report_date);
    } catch (err) {
      setActionError(
        err instanceof ApiError
          ? err.message
          : kind === "sync"
          ? "Could not fetch prices from HARTI."
          : "Could not import that PDF."
      );
    } finally {
      setBusy(null);
    }
  }

  async function handleExport() {
    if (!report?.report_date) return;
    setBusy("export");
    setActionError(null);
    try {
      await downloadLocalMarketExcel(report.report_date);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not download the local market prices.");
    } finally {
      setBusy(null);
    }
  }

  const rows = useMemo(() => report?.rows ?? [], [report]);

  const categories = useMemo(
    () => Array.from(new Set(rows.map((r) => r.category_name).filter((c): c is string => !!c))).sort(),
    [rows]
  );

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows
      .filter((r) => (category ? r.category_name === category : true))
      .filter((r) => (q ? [r.system_name, r.dc_code, r.pdf_name].some((s) => s.toLowerCase().includes(q)) : true));
  }, [rows, search, category]);

  // How many items each market priced on this bulletin — HARTI sometimes
  // has no figures at all for a market (Keppetipola often), and a column
  // of dashes reads like a bug without this.
  const pricedCount = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const m of MARKETS) counts[m.key] = rows.filter((r) => r[m.key]).length;
    return counts;
  }, [rows]);

  const reportDate = report?.report_date ?? null;
  const availableDates = report?.available_dates ?? [];
  const inputClass =
    "border border-sage-300 bg-sage-50/60 rounded-full px-4 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150";
  const secondaryButtonClass =
    "text-sm border border-sage-300 text-crate-800/70 rounded-full px-4 py-1.5 font-medium hover:bg-sage-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-150";

  if (error && !report) {
    return (
      <div className="rounded-2xl bg-tomato-500/10 border border-tomato-500/25 p-6 text-tomato-600 text-sm">{error}</div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <label htmlFor="local-market-report-date" className="text-sm text-crate-800/70">
            Bulletin
          </label>
          <select
            id="local-market-report-date"
            value={reportDate ?? ""}
            onChange={(e) => load(e.target.value)}
            disabled={availableDates.length === 0}
            className={`${inputClass} px-3.5 disabled:opacity-60`}
          >
            {availableDates.length === 0 ? (
              <option value="">None imported yet</option>
            ) : (
              availableDates.map((d, i) => (
                <option key={d} value={d}>
                  {formatShortDate(d)}
                  {i === 0 ? " (latest)" : ""}
                </option>
              ))
            )}
          </select>
          <input
            type="text"
            placeholder="Search item, DC code or HARTI name…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={`flex-1 min-w-[12rem] ${inputClass}`}
          />
          <select value={category} onChange={(e) => setCategory(e.target.value)} className={`${inputClass} px-3.5`}>
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <span className="text-xs text-crate-800/40">{filteredRows.length} items</span>
          <div className="flex flex-wrap items-center gap-2 ml-auto">
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              disabled={busy !== null}
              className={secondaryButtonClass}
            >
              {busy === "upload" ? "Importing PDF…" : "Upload PDF"}
            </button>
            <input
              ref={fileInput}
              type="file"
              accept="application/pdf,.pdf"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = ""; // let the same file be picked again after a failed import
                if (file) runImport("upload", () => uploadLocalMarketBulletin(file));
              }}
            />
            <button
              type="button"
              onClick={handleExport}
              disabled={busy !== null || rows.length === 0}
              className={secondaryButtonClass}
            >
              {busy === "export" ? "Preparing…" : "Export Excel"}
            </button>
            <button
              type="button"
              onClick={() => runImport("sync", syncLocalMarketPrices)}
              disabled={busy !== null}
              className="border border-crate-700/30 bg-crate-700 hover:bg-crate-800 rounded-full px-4 py-1.5 text-sm text-white transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {busy === "sync" ? "Fetching from HARTI…" : "Fetch latest from HARTI"}
            </button>
          </div>
        </div>
        <p className="text-xs text-crate-800/40 mt-3">
          {reportDate ? (
            <>
              Wholesale prices (Rs. per kg) from HARTI's daily price bulletin for {formatDate(reportDate)}
              {report?.imported_at && (
                <>
                  {" "}
                  — imported{" "}
                  {new Date(report.imported_at).toLocaleString(undefined, {
                    day: "numeric",
                    month: "short",
                    hour: "numeric",
                    minute: "2-digit",
                  })}
                </>
              )}
              .{" "}
            </>
          ) : (
            "No HARTI bulletin has been imported yet. "
          )}
          Each market's Avg is the midpoint of its range; Final Avg is the average of the markets that had a price
          (a dash means that market didn't price the item that day). "Fetch latest from HARTI" downloads the newest
          English bulletin from harti.gov.lk — if the site can't be reached, download the PDF yourself and use "Upload
          PDF". Importing a date again replaces its prices. A reference for Admin only, not shown to suppliers.
        </p>
        {actionError && <p className="text-xs text-tomato-600 mt-2">{actionError}</p>}
        {importResult && (
          <p className="text-xs text-crate-700 mt-2">
            ✓ Imported {importResult.saved} item{importResult.saved === 1 ? "" : "s"} from the bulletin for{" "}
            {formatDate(importResult.report_date)}.
            {importResult.not_priced.length > 0 && (
              <> No price in any of the four markets: {importResult.not_priced.join(", ")}.</>
            )}
            {importResult.unmatched.length > 0 && (
              <>
                {" "}
                Not in the product list, so left out of Price History:{" "}
                {importResult.unmatched.map((u) => `${u.system_name} (${u.dc_code})`).join(", ")}.
              </>
            )}
          </p>
        )}
      </div>

      <div className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-hidden">
        {loading ? (
          <SkeletonTable rows={8} columns={6} />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={<IconBranches width={20} height={20} />}
            title="No local market prices yet"
            description={'Use "Fetch latest from HARTI" to import today\'s bulletin.'}
          />
        ) : filteredRows.length === 0 ? (
          <EmptyState icon={<IconBranches width={20} height={20} />} title="No items match your filters" />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm border-collapse">
              <thead>
                <tr className="bg-sage-50 text-crate-800/50 text-xs uppercase tracking-wide">
                  <th
                    rowSpan={2}
                    className="text-left align-bottom px-3 py-2.5 sticky z-20 bg-sage-50"
                    style={{ left: 0, width: DC_CODE_WIDTH, minWidth: DC_CODE_WIDTH }}
                  >
                    DC Code
                  </th>
                  <th
                    rowSpan={2}
                    className="text-left align-bottom px-3 py-2.5 sticky z-20 bg-sage-50 shadow-[2px_0_2px_-1px_rgba(21,56,38,0.08)]"
                    style={{ left: DC_CODE_WIDTH, minWidth: 210 }}
                  >
                    System Name
                  </th>
                  {MARKETS.map((m) => (
                    <th key={m.key} colSpan={2} className="text-center px-3 pt-2.5 pb-1 font-semibold border-l border-sage-100">
                      {m.label}
                      <span className="block normal-case tracking-normal font-normal text-[10px] text-crate-800/35">
                        {pricedCount[m.key] > 0 ? `${pricedCount[m.key]} of ${rows.length} items` : "no prices this day"}
                      </span>
                    </th>
                  ))}
                  <th
                    rowSpan={2}
                    className="text-right align-bottom px-4 py-2.5 font-semibold text-crate-800/70 bg-sage-100/70 border-l border-sage-200 whitespace-nowrap"
                  >
                    Final Avg
                  </th>
                </tr>
                <tr className="bg-sage-50 text-crate-800/40 text-[10px] uppercase tracking-wide">
                  {MARKETS.map((m) => (
                    <Fragment key={m.key}>
                      <th className="text-right px-3 pb-2 font-medium border-l border-sage-100">Range</th>
                      <th className="text-right px-3 pb-2 font-medium">Avg</th>
                    </Fragment>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-sage-100">
                {filteredRows.map((r) => (
                  <tr key={r.dc_code} className="hover:bg-sage-50/50 transition-colors duration-100">
                    <td
                      className="px-3 py-2.5 text-crate-800/50 tabular-nums sticky z-10 bg-white"
                      style={{ left: 0, width: DC_CODE_WIDTH, minWidth: DC_CODE_WIDTH }}
                    >
                      {r.dc_code}
                    </td>
                    <td
                      className="px-3 py-2.5 sticky z-10 bg-white shadow-[2px_0_2px_-1px_rgba(21,56,38,0.08)]"
                      style={{ left: DC_CODE_WIDTH, minWidth: 210 }}
                    >
                      <p className="text-crate-950 whitespace-nowrap">{r.system_name}</p>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <span className="text-[11px] text-crate-800/40 whitespace-nowrap">HARTI: {r.pdf_name}</span>
                        {r.category_name && <CategoryBadge name={r.category_name} />}
                      </div>
                    </td>
                    {MARKETS.map((m) => (
                      <MarketCells key={m.key} range={r[m.key]} />
                    ))}
                    <td className="px-4 py-2.5 text-right whitespace-nowrap tabular-nums font-semibold text-crate-950 bg-sage-50/60 border-l border-sage-200">
                      Rs. {formatPrice(r.final_average)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {error && report && <p className="text-tomato-600 text-sm px-1">{error}</p>}
    </div>
  );
}
