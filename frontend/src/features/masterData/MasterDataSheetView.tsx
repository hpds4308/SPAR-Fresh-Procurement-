import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import {
  MasterDataSubmission,
  PublishSummary,
  downloadTeamSheet,
  fetchTeamSheet,
  publishSellingPrices,
} from "../../api/masterData";
import EmptyState from "../shared/EmptyState";
import { IconGrid } from "../shared/Icons";
import MasterDataTable from "../shared/MasterDataTable";
import { ConfirmDialog } from "../shared/ui/Modal";
import { SkeletonTable } from "../shared/ui/Skeleton";
import { useToast } from "../shared/ui/Toast";

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function SkippedList({ label, names }: { label: string; names: string[] }) {
  if (names.length === 0) return null;
  return (
    <details className="mt-1">
      <summary className="cursor-pointer text-crate-800/60">
        {label}: {names.length}
      </summary>
      <p className="mt-1 text-xs text-crate-800/50">{names.join(", ")}</p>
    </details>
  );
}

/**
 * Master Data Team: the latest Master Data Sheet Admin sent, read-only.
 * Download Excel exports exactly that version; Update Selling Prices
 * publishes its selling prices so every branch sees them.
 */
export default function MasterDataSheetView() {
  const [data, setData] = useState<MasterDataSubmission | null>(null);
  const [notSentYet, setNotSentYet] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [summary, setSummary] = useState<PublishSummary | null>(null);
  const { show } = useToast();

  useEffect(() => {
    load();
  }, []);

  function load() {
    setLoading(true);
    setError(null);
    fetchTeamSheet()
      .then((d) => {
        setData(d);
        setNotSentYet(false);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) setNotSentYet(true);
        else setError(err instanceof ApiError ? err.message : "Could not load the master data sheet.");
      })
      .finally(() => setLoading(false));
  }

  const rows = data?.sheet.rows ?? [];
  const categories = useMemo(() => Array.from(new Set(rows.map((r) => r.category_name))).sort(), [rows]);
  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (category && r.category_name !== category) return false;
      if (!q) return true;
      return (
        r.description.toLowerCase().includes(q) ||
        r.product_code.toLowerCase().includes(q) ||
        (r.pos_code ?? "").toLowerCase().includes(q)
      );
    });
  }, [rows, search, category]);
  const toPublish = rows.filter((r) => r.selling_price !== null && r.selling_price !== r.published_selling_price).length;
  const missing = rows.filter((r) => r.selling_price === null).length;

  async function handleDownload() {
    setDownloading(true);
    setError(null);
    try {
      await downloadTeamSheet();
    } catch {
      setError("Could not download the file. Please try again.");
    } finally {
      setDownloading(false);
    }
  }

  async function handlePublish() {
    setPublishing(true);
    setError(null);
    try {
      const result = await publishSellingPrices();
      setSummary(result);
      show("success", `Selling prices published to ${result.branches_updated} branches.`);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not publish selling prices. Please try again.");
    } finally {
      setPublishing(false);
      setConfirmOpen(false);
    }
  }

  if (loading && !data) {
    return (
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-hidden">
        <SkeletonTable rows={8} columns={6} />
      </div>
    );
  }

  if (notSentYet) {
    return (
      <EmptyState
        icon={<IconGrid width={20} height={20} />}
        title="Nothing sent yet"
        description="The Master Data Sheet appears here once Admin clicks Send to Master Data."
      />
    );
  }

  if (!data) {
    return (
      <div className="rounded-2xl bg-tomato-500/10 border border-tomato-500/25 p-6 text-tomato-600 text-sm">
        {error ?? "Could not load the master data sheet."}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 p-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
        <div>
          <p className="text-[10px] uppercase tracking-wide text-crate-800/40">Version from Admin</p>
          <p className="text-crate-950 font-semibold">
            v{data.version} · {formatDateTime(data.sent_at)}
          </p>
          <p className="text-xs text-crate-800/50">Sent by {data.sent_by}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-crate-800/40">Last published</p>
          {data.published_at ? (
            <>
              <p className="text-crate-950 font-semibold">{formatDateTime(data.published_at)}</p>
              <p className="text-xs text-crate-800/50">By {data.published_by}</p>
            </>
          ) : (
            <p className="text-[#8A5A0D] font-semibold">Not published yet</p>
          )}
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-crate-800/40">Products</p>
          <p className="text-crate-950 font-semibold">{data.product_count}</p>
          <p className="text-xs text-crate-800/50">
            {toPublish} to publish · {missing} without a selling price
          </p>
        </div>
      </div>

      <div className="bg-white rounded-2xl shadow-card border border-sage-100 p-4 flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="Search item, code, or POS code…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[12rem] border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
        />
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="border border-sage-300 bg-sage-50/60 rounded-full px-3.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <span className="text-xs text-crate-800/40">
          {filteredRows.length} of {rows.length} items · {data.sheet.suppliers.length} suppliers
        </span>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={handleDownload}
            disabled={downloading}
            className="text-sm border border-sage-300 text-crate-800/70 rounded-full px-4 py-2 font-medium hover:bg-sage-50 disabled:opacity-50 transition-colors duration-150"
          >
            {downloading ? "Preparing…" : "Download Excel"}
          </button>
          <button
            onClick={() => setConfirmOpen(true)}
            disabled={publishing}
            className="text-sm bg-gradient-to-b from-crate-700 to-crate-800 text-white rounded-full px-4 py-2 font-semibold hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100 shadow-md shadow-crate-800/20 transition-all duration-150"
          >
            {publishing ? "Publishing…" : "Update Selling Prices"}
          </button>
        </div>
      </div>

      {summary && (
        <div className="rounded-2xl bg-crate-700/5 border border-crate-700/20 p-4 text-sm text-crate-950">
          <p className="font-semibold">
            ✓ Published version {summary.version} to {summary.branches_updated} branches.
          </p>
          <p className="text-crate-800/70 mt-0.5">
            {summary.products_updated} product{summary.products_updated === 1 ? "" : "s"} updated ·{" "}
            {summary.products_unchanged} already up to date · {summary.skipped_missing_price.length} skipped (no
            selling price) · {summary.skipped_invalid.length} skipped (invalid data)
          </p>
          <SkippedList label="Skipped — no selling price" names={summary.skipped_missing_price} />
          <SkippedList label="Skipped — invalid data" names={summary.skipped_invalid} />
        </div>
      )}
      {error && <p className="text-tomato-600 text-sm px-1">{error}</p>}

      <MasterDataTable suppliers={data.sheet.suppliers} rows={filteredRows} showPublished />
      <p className="text-[11px] text-crate-800/35 px-1">
        This is the Master Data Sheet exactly as Admin sent it — it can't be edited here. Published shows the
        selling price branches see right now. Update Selling Prices publishes every valid selling price on this
        sheet to all branches; order quantities and supplier prices are not changed.
      </p>

      <ConfirmDialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        onConfirm={handlePublish}
        title="Update selling prices for all branches?"
        description={`Every branch will see the selling prices from version ${data.version} (${toPublish} new or changed). Products without a valid selling price are skipped. Order quantities and supplier prices are not changed.`}
        confirmLabel="Publish"
        loading={publishing}
      />
    </div>
  );
}
