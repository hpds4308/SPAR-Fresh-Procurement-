import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import {
  MasterDataFieldName,
  MasterDataRow,
  MasterDataSheet,
  downloadMasterData,
  fetchMasterData,
  sendMasterDataEmail,
  updateMasterDataField,
} from "../../api/masterData";
import EmptyState from "../shared/EmptyState";
import { IconGrid } from "../shared/Icons";
import { ConfirmDialog } from "../shared/ui/Modal";
import { SkeletonTable } from "../shared/ui/Skeleton";
import { CategoryBadge } from "../shared/ui/CategoryBadge";

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
  const [sendingEmail, setSendingEmail] = useState(false);
  const [emailSentMessage, setEmailSentMessage] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);

  const [drafts, setDrafts] = useState<Record<CellKey, string>>({});
  const [cellState, setCellState] = useState<Record<CellKey, CellState>>({});

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
    try {
      const updated = await updateMasterDataField(productId, field, value);
      setSheet((prev) => (prev ? { ...prev, rows: prev.rows.map((r) => (r.product_id === productId ? updated : r)) } : prev));
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

  async function handleSendEmail() {
    setSendingEmail(true);
    setError(null);
    setEmailSentMessage(null);
    try {
      const result = await sendMasterDataEmail();
      setEmailSentMessage(`Sent to ${result.sent_to}`);
      setTimeout(() => setEmailSentMessage((m) => (m ? null : m)), 5000);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send the email. Please try again.");
    } finally {
      setSendingEmail(false);
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
            onClick={handleSendEmail}
            disabled={sendingEmail}
            title="Emails the current sheet as an Excel attachment"
            className="text-sm border border-sage-300 text-crate-800/70 rounded-full px-4 py-2 font-medium hover:bg-sage-50 disabled:opacity-50 transition-colors duration-150"
          >
            {sendingEmail ? "Sending…" : "Send to Master Data"}
          </button>
        </div>
      </div>

      {emailSentMessage && (
        <p className="text-crate-700 text-sm px-1 font-medium">✓ {emailSentMessage}</p>
      )}
      {error && sheet && <p className="text-tomato-600 text-sm px-1">{error}</p>}

      <div className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-x-auto">
        <table className="text-sm border-collapse min-w-max">
          <thead>
            <tr className="bg-sage-50 text-crate-800/50 text-xs uppercase tracking-wide">
              <th className="text-left px-3 py-2.5 sticky z-20 bg-sage-50" style={{ left: 0, width: 90, minWidth: 90 }}>
                Category
              </th>
              <th className="text-left px-3 py-2.5 sticky z-20 bg-sage-50" style={{ left: 90, width: 90, minWidth: 90 }}>
                Code
              </th>
              <th className="text-left px-3 py-2.5 sticky z-20 bg-sage-50" style={{ left: 180, width: 90, minWidth: 90 }}>
                POS Code
              </th>
              <th
                className="text-left px-3 py-2.5 sticky z-20 bg-sage-50 shadow-[2px_0_2px_-1px_rgba(21,56,38,0.08)]"
                style={{ left: 270, width: 190, minWidth: 190 }}
              >
                Description
              </th>
              <th className="text-right px-3 py-2.5 whitespace-nowrap">Target GP%</th>
              <th className="text-right px-3 py-2.5 whitespace-nowrap">Selling Price</th>
              <th className="text-right px-3 py-2.5 whitespace-nowrap">GP%</th>
              <th className="text-right px-3 py-2.5 whitespace-nowrap">
                Cost Price
                <div className="text-[9px] font-normal normal-case text-crate-800/35">Highest submitted price</div>
              </th>
              {sheet.suppliers.map((s) => (
                <th key={s.supplier_id} className="text-right px-3 py-2.5 whitespace-nowrap bg-mango-500/10">
                  {s.supplier_name}
                  <div className="text-[9px] font-normal normal-case text-crate-800/35">Adjusted CP</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-sage-100">
            {filteredRows.map((row) => {
              const gpBelow = row.computed_gp_percent !== null && row.computed_gp_percent < row.target_gp_percent;
              return (
                <tr key={row.product_id} className="hover:bg-sage-50/50 transition-colors duration-100">
                  <td className="px-3 py-2 sticky z-10 bg-white" style={{ left: 0, width: 90 }}>
                    <CategoryBadge name={row.category_name} />
                  </td>
                  <td className="px-3 py-2 text-crate-800/40 sticky z-10 bg-white" style={{ left: 90, width: 90 }}>
                    {row.product_code}
                  </td>
                  <td className="px-3 py-2 text-crate-800/60 sticky z-10 bg-white" style={{ left: 180, width: 90 }}>
                    {row.pos_code ?? <span className="text-crate-800/20">—</span>}
                  </td>
                  <td
                    className="px-3 py-2 text-crate-950 sticky z-10 bg-white shadow-[2px_0_2px_-1px_rgba(21,56,38,0.08)]"
                    style={{ left: 270, width: 190 }}
                  >
                    {row.description}
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <input
                        type="number"
                        min="0"
                        max="100"
                        step="0.1"
                        placeholder="30.0"
                        value={drafts[`${row.product_id}:target_gp_percent`] ?? ""}
                        onChange={(e) =>
                          setDrafts((d) => ({ ...d, [`${row.product_id}:target_gp_percent`]: e.target.value }))
                        }
                        onBlur={(e) => saveField(row.product_id, "target_gp_percent", e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
                        className={`w-16 border rounded-lg px-1.5 py-1 text-right text-xs bg-sage-50/60 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white ${
                          cellState[`${row.product_id}:target_gp_percent`] === "error" ? "border-tomato-500" : "border-sage-300"
                        }`}
                      />
                      <span className="text-[10px] text-crate-800/35">%</span>
                    </div>
                  </td>
                  <td className="px-2 py-1.5">
                    <div className="flex items-center justify-end gap-1">
                      <span className="text-[10px] text-crate-800/35">Rs.</span>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        placeholder="—"
                        value={drafts[`${row.product_id}:selling_price`] ?? ""}
                        onChange={(e) =>
                          setDrafts((d) => ({ ...d, [`${row.product_id}:selling_price`]: e.target.value }))
                        }
                        onBlur={(e) => saveField(row.product_id, "selling_price", e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
                        className={`w-20 border rounded-lg px-1.5 py-1 text-right text-xs bg-sage-50/60 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white ${
                          cellState[`${row.product_id}:selling_price`] === "error" ? "border-tomato-500" : "border-sage-300"
                        }`}
                      />
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    {row.computed_gp_percent !== null ? (
                      <span className={`font-semibold ${gpBelow ? "text-tomato-600" : "text-crate-700"}`}>
                        {(row.computed_gp_percent * 100).toFixed(1)}%
                      </span>
                    ) : (
                      <span className="text-crate-800/20">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right text-crate-800/70 whitespace-nowrap">
                    {row.cost_price !== null ? `Rs. ${row.cost_price.toFixed(2)}` : <span className="text-crate-800/20">—</span>}
                  </td>
                  {sheet.suppliers.map((s) => {
                    const price = row.supplier_prices[s.supplier_id];
                    return (
                      <td key={s.supplier_id} className="px-3 py-2 text-right text-crate-800/70 bg-mango-500/5">
                        {price !== null && price !== undefined ? price.toFixed(2) : <span className="text-crate-800/20">—</span>}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-crate-800/35 px-1">
        POS Code is fixed, sourced from the original uploaded product data — not editable here. Cost Price is
        the highest current SUBMITTED price among suppliers who've quoted an item — not their Adjusted Price —
        it's computed, not editable. Supplier columns mirror Supplier Prices and are read-only here; edit them
        there. Target GP% defaults to 30% until you set your own.
      </p>

      <ConfirmDialog
        open={confirmClearOpen}
        onClose={() => setConfirmClearOpen(false)}
        onConfirm={handleClearAll}
        title="Clear all visible rows?"
        description={`This clears Target GP% and Selling Price for all ${filteredRows.length} currently visible item${filteredRows.length === 1 ? "" : "s"} — Target GP% will fall back to the 30% default. POS Code, Cost Price, and supplier prices are unaffected. This can't be undone.`}
        confirmLabel="Clear All"
        danger
        loading={clearing}
      />
    </div>
  );
}
