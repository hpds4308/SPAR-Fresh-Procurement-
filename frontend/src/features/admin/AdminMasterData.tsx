import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import {
  MasterDataFieldName,
  MasterDataRow,
  MasterDataSheet,
  autoGenerateSellingPrices,
  downloadMasterData,
  fetchMasterData,
  sendToMasterData,
  updateMasterDataField,
} from "../../api/masterData";
import EmptyState from "../shared/EmptyState";
import { IconGrid } from "../shared/Icons";
import MasterDataTable from "../shared/MasterDataTable";
import { ConfirmDialog } from "../shared/ui/Modal";
import { SkeletonTable } from "../shared/ui/Skeleton";
import { useToast } from "../shared/ui/Toast";

type CellState = "idle" | "saving" | "saved" | "error";
type CellKey = `${number}:${MasterDataFieldName}`;

function pct(v: number): string {
  return (v * 100).toFixed(1);
}

export default function AdminMasterData() {
  const [sheet, setSheet] = useState<MasterDataSheet | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [sending, setSending] = useState(false);
  const [sentMessage, setSentMessage] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [confirmGenerateOpen, setConfirmGenerateOpen] = useState(false);
  const [generateMessage, setGenerateMessage] = useState<string | null>(null);

  const [drafts, setDrafts] = useState<Record<CellKey, string>>({});
  const [cellState, setCellState] = useState<Record<CellKey, CellState>>({});
  // Cell saves still in flight — "Send to Master Data" waits for them so
  // the team never gets a sheet missing the last thing Admin typed.
  const pendingSaves = useRef(new Set<Promise<unknown>>());
  const { show } = useToast();

  useEffect(() => {
    load();
  }, []);

  function seedDrafts(rows: MasterDataRow[]) {
    const nextDrafts: Record<CellKey, string> = {};
    for (const r of rows) {
      nextDrafts[`${r.product_id}:target_gp_percent`] = pct(r.target_gp_percent);
      nextDrafts[`${r.product_id}:selling_price`] = r.selling_price !== null ? String(r.selling_price) : "";
    }
    setDrafts(nextDrafts);
    setCellState({});
  }

  function load() {
    setLoading(true);
    setError(null);
    fetchMasterData()
      .then((data) => {
        setSheet(data);
        seedDrafts(data.rows);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load the master data sheet."))
      .finally(() => setLoading(false));
  }

  const categories = useMemo(() => {
    if (!sheet) return [];
    return Array.from(new Set(sheet.rows.map((r) => r.category_name))).sort();
  }, [sheet]);

  const filteredRows = useMemo(() => {
    if (!sheet) return [];
    const q = search.trim().toLowerCase();
    return sheet.rows.filter((r) => {
      if (category && r.category_name !== category) return false;
      if (!q) return true;
      return (
        r.description.toLowerCase().includes(q) ||
        r.product_code.toLowerCase().includes(q) ||
        (r.pos_code ?? "").toLowerCase().includes(q)
      );
    });
  }, [sheet, search, category]);

  async function saveField(productId: number, field: MasterDataFieldName, raw: string) {
    const key: CellKey = `${productId}:${field}`;
    const trimmed = raw.trim();
    let value: string | number | null;

    if (field === "target_gp_percent") {
      if (trimmed === "") {
        value = null;
      } else {
        const n = Number(trimmed);
        if (Number.isNaN(n) || n < 0 || n > 100) {
          setCellState((s) => ({ ...s, [key]: "error" }));
          return;
        }
        value = n / 100;
      }
    } else {
      if (trimmed === "") {
        value = null;
      } else {
        const n = Number(trimmed);
        if (Number.isNaN(n) || n <= 0) {
          setCellState((s) => ({ ...s, [key]: "error" }));
          return;
        }
        value = n;
      }
    }

    setCellState((s) => ({ ...s, [key]: "saving" }));
    const request = updateMasterDataField(productId, field, value);
    pendingSaves.current.add(request);
    request.catch(() => {}).finally(() => pendingSaves.current.delete(request));
    try {
      const updated = await request;
      setSheet((prev) => (prev ? { ...prev, rows: prev.rows.map((r) => (r.product_id === productId ? updated : r)) } : prev));
      // Server rounds selling price up to the next 10 — show what was actually saved.
      if (field === "selling_price") {
        setDrafts((d) => ({ ...d, [key]: updated.selling_price !== null ? String(updated.selling_price) : "" }));
      }
      setCellState((s) => ({ ...s, [key]: "saved" }));
      setTimeout(() => setCellState((s) => (s[key] === "saved" ? { ...s, [key]: "idle" } : s)), 1500);
    } catch {
      setCellState((s) => ({ ...s, [key]: "error" }));
    }
  }

  async function handleDownload() {
    setDownloading(true);
    setError(null);
    try {
      await downloadMasterData();
    } catch {
      setError("Could not download the file. Please try again.");
    } finally {
      setDownloading(false);
    }
  }

  async function handleSend() {
    if (sending) return;
    setSending(true);
    setError(null);
    setSentMessage(null);
    try {
      // Save whatever cell is still being typed in, then wait for every save.
      if (document.activeElement instanceof HTMLInputElement) document.activeElement.blur();
      await new Promise((r) => setTimeout(r, 0));
      await Promise.allSettled(Array.from(pendingSaves.current));
      if (Object.values(cellState).includes("error")) {
        setError("Some cells couldn't be saved (marked in red) — fix them before sending.");
        return;
      }
      const result = await sendToMasterData();
      const message = result.created
        ? `Sent to the Master Data Team as version ${result.version} — ${result.product_count} products, ${result.products_with_price} with a selling price.`
        : `Nothing changed since version ${result.version} — the Master Data Team already has this sheet.`;
      setSentMessage(
        message +
          (result.emailed_to ? ` Also emailed to ${result.emailed_to}.` : "") +
          (result.email_error ? ` (The email copy wasn't sent: ${result.email_error})` : "")
      );
      show("success", result.created ? `Master Data Sheet v${result.version} sent.` : "Already up to date.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send to Master Data. Please try again.");
    } finally {
      setSending(false);
    }
  }

  // Clears every currently-visible row's editable drafts (Target GP%,
  // Selling Price) back to blank / the 30% default — a bulk reset, not
  // just a local-form clear, since each cell already auto-saves on its own.
  // POS Code is fixed and not touched — it's sourced from the original
  // uploaded product data, never cleared from here.
  async function handleClearAll() {
    if (!sheet) return;
    setClearing(true);
    setError(null);
    try {
      for (const row of filteredRows) {
        await Promise.all([
          updateMasterDataField(row.product_id, "target_gp_percent", null),
          updateMasterDataField(row.product_id, "selling_price", null),
        ]);
      }
      const fresh = await fetchMasterData();
      setSheet(fresh);
      seedDrafts(fresh.rows);
    } catch {
      setError("Some rows may not have cleared — reload and check before continuing.");
    } finally {
      setClearing(false);
      setConfirmClearOpen(false);
    }
  }

  // Fills Selling Price only for items that have none yet, from Cost Price
  // and each row's own Target GP% (rounded up to the next 10 server-side).
  // Prices already there — typed or generated earlier — are kept.
  async function handleAutoGenerate() {
    setGenerating(true);
    setError(null);
    setGenerateMessage(null);
    try {
      const result = await autoGenerateSellingPrices();
      const fresh = await fetchMasterData();
      setSheet(fresh);
      seedDrafts(fresh.rows);
      setGenerateMessage(
        `${result.total_products} products: ${result.generated} price${result.generated === 1 ? "" : "s"} generated, ` +
          `${result.preserved} existing kept, ${result.without_price} still without a selling price (no cost price yet).`
      );
      setTimeout(() => setGenerateMessage((m) => (m ? null : m)), 10000);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not auto-generate selling prices. Please try again.");
    } finally {
      setGenerating(false);
      setConfirmGenerateOpen(false);
    }
  }

  if (loading) {
    return (
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-hidden">
        <SkeletonTable rows={8} columns={6} />
      </div>
    );
  }

  if (error && !sheet) {
    return (
      <div className="rounded-2xl bg-tomato-500/10 border border-tomato-500/25 p-6 text-tomato-600 text-sm">
        {error}
      </div>
    );
  }

  if (!sheet || sheet.rows.length === 0) {
    return (
      <EmptyState
        icon={<IconGrid width={20} height={20} />}
        title="No active products"
        description="The master data sheet will list every active product once your catalogue has some."
      />
    );
  }

  return (
    <div className="space-y-4">
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
          {filteredRows.length} of {sheet.rows.length} items · {sheet.suppliers.length} suppliers
        </span>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => setConfirmGenerateOpen(true)}
            disabled={generating}
            title="Fills Selling Price for items that don't have one yet, from Cost Price and Target GP%, rounded up to the next 10"
            className="text-sm border border-sage-300 text-crate-800/70 rounded-full px-4 py-2 font-medium hover:bg-sage-50 disabled:opacity-50 transition-colors duration-150"
          >
            {generating ? "Generating…" : "Auto-generate Selling Price"}
          </button>
          <button
            onClick={() => setConfirmClearOpen(true)}
            disabled={clearing}
            className="text-sm border border-sage-300 text-crate-800/70 rounded-full px-4 py-2 font-medium hover:bg-sage-50 disabled:opacity-50 transition-colors duration-150"
          >
            {clearing ? "Clearing…" : "Clear All"}
          </button>
          <button
            onClick={handleDownload}
            disabled={downloading}
            className="text-sm bg-gradient-to-b from-crate-700 to-crate-800 text-white rounded-full px-4 py-2 font-semibold hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100 shadow-md shadow-crate-800/20 transition-all duration-150"
          >
            {downloading ? "Preparing…" : "Download Excel"}
          </button>
          <button
            onClick={handleSend}
            disabled={sending}
            title="Saves the sheet and makes it the latest version for the Master Data Team (also emailed if a recipient is set in Settings)"
            className="text-sm border border-sage-300 text-crate-800/70 rounded-full px-4 py-2 font-medium hover:bg-sage-50 disabled:opacity-50 transition-colors duration-150"
          >
            {sending ? "Sending…" : "Send to Master Data"}
          </button>
        </div>
      </div>

      {sentMessage && <p className="text-crate-700 text-sm px-1 font-medium">✓ {sentMessage}</p>}
      {generateMessage && (
        <p className="text-crate-700 text-sm px-1 font-medium">✓ {generateMessage}</p>
      )}
      {error && sheet && <p className="text-tomato-600 text-sm px-1">{error}</p>}

      <MasterDataTable
        suppliers={sheet.suppliers}
        rows={filteredRows}
        renderTargetGp={(row) => (
          <div className="flex items-center justify-end gap-1">
            <input
              type="number"
              min="0"
              max="100"
              step="0.1"
              placeholder="30.0"
              value={drafts[`${row.product_id}:target_gp_percent`] ?? ""}
              onChange={(e) => setDrafts((d) => ({ ...d, [`${row.product_id}:target_gp_percent`]: e.target.value }))}
              onBlur={(e) => saveField(row.product_id, "target_gp_percent", e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
              className={`w-16 border rounded-lg px-1.5 py-1 text-right text-xs bg-sage-50/60 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white ${
                cellState[`${row.product_id}:target_gp_percent`] === "error" ? "border-tomato-500" : "border-sage-300"
              }`}
            />
            <span className="text-[10px] text-crate-800/35">%</span>
          </div>
        )}
        renderSellingPrice={(row) => (
          <div className="flex items-center justify-end gap-1">
            <span className="text-[10px] text-crate-800/35">Rs.</span>
            <input
              type="number"
              min="0"
              step="0.01"
              placeholder="—"
              value={drafts[`${row.product_id}:selling_price`] ?? ""}
              onChange={(e) => setDrafts((d) => ({ ...d, [`${row.product_id}:selling_price`]: e.target.value }))}
              onBlur={(e) => saveField(row.product_id, "selling_price", e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
              className={`w-20 border rounded-lg px-1.5 py-1 text-right text-xs bg-sage-50/60 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white ${
                cellState[`${row.product_id}:selling_price`] === "error" ? "border-tomato-500" : "border-sage-300"
              }`}
            />
            <span
              title={row.selling_price_source === "AUTO" ? "Auto-generated" : row.selling_price_source === "MANUAL" ? "Entered manually" : undefined}
              className={`text-[9px] font-semibold w-8 ${row.selling_price_source === "AUTO" ? "text-[#8A5A0D]" : "text-crate-800/35"}`}
            >
              {row.selling_price_source === "AUTO" ? "AUTO" : row.selling_price_source === "MANUAL" ? "MAN" : ""}
            </span>
          </div>
        )}
      />
      <p className="text-[11px] text-crate-800/35 px-1">
        POS Code is fixed, sourced from the original uploaded product data — not editable here. Cost Price is
        the highest of the supplier prices in the same row — it's computed, not editable. Keells Price is the latest price entered on Keells Prices — edit it
        there. Supplier columns mirror Supplier Prices and are read-only here; edit them
        there. Target GP% defaults to 30% until you set your own. AUTO / MAN beside a selling price shows whether
        it was auto-generated or typed in. Branches only see selling prices after the Master Data Team publishes
        them.
      </p>

      <ConfirmDialog
        open={confirmGenerateOpen}
        onClose={() => setConfirmGenerateOpen(false)}
        onConfirm={handleAutoGenerate}
        title="Auto-generate selling prices?"
        description="This fills in Selling Price only for items that don't have one yet, from Cost Price and Target GP%, then removes decimals and rounds up to the next 10. Selling prices already on the sheet — typed in or generated earlier — are kept, and published prices are not changed. Items with no Cost Price stay blank."
        confirmLabel="Generate"
        loading={generating}
      />

      <ConfirmDialog
        open={confirmClearOpen}
        onClose={() => setConfirmClearOpen(false)}
        onConfirm={handleClearAll}
        title="Clear all visible rows?"
        description={`This clears Target GP% and Selling Price for all ${filteredRows.length} currently visible item${filteredRows.length === 1 ? "" : "s"} — Target GP% will fall back to the 30% default. POS Code, Keells Price, Cost Price, and supplier prices are unaffected. This can't be undone.`}
        confirmLabel="Clear All"
        danger
        loading={clearing}
      />
    </div>
  );
}
