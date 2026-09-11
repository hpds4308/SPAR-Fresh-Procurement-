import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import {
  Settings,
  fetchMasterDataEmail,
  fetchSettings,
  updateMasterDataEmail,
  updateSetting,
} from "../../api/settings";
import {
  Branch,
  OrderDeadlineException,
  fetchBranches,
  fetchOrderDeadlineExceptions,
  grantOrderDeadlineException,
  revokeOrderDeadlineException,
} from "../../api/branches";
import { Skeleton } from "../shared/ui/Skeleton";

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

type FieldState = "idle" | "saving" | "saved" | "error";

const FIELDS: { key: keyof Settings; label: string; hint: string; type: "time" | "text" }[] = [
  {
    key: "branch_order_deadline",
    label: "Branch order cutoff",
    hint: "Branches can submit orders for the day up until this time (Asia/Colombo).",
    type: "time",
  },
  {
    key: "supplier_price_deadline",
    label: "Supplier price cutoff",
    hint: "Suppliers can submit prices up until this time (Asia/Colombo).",
    type: "time",
  },
  {
    key: "support_phone",
    label: "Support contact number",
    hint: "Shown to branches and suppliers on the Guidelines pages.",
    type: "text",
  },
];

export default function AdminSettings() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [fieldState, setFieldState] = useState<Record<string, FieldState>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSettings()
      .then((s) => {
        setSettings(s);
        setDrafts({
          branch_order_deadline: s.branch_order_deadline,
          supplier_price_deadline: s.supplier_price_deadline,
          support_phone: s.support_phone,
        });
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load settings."))
      .finally(() => setLoading(false));
  }, []);

  async function save(key: keyof Settings, value: string) {
    if (!settings || value.trim() === "" || value === settings[key]) return;
    setFieldState((s) => ({ ...s, [key]: "saving" }));
    try {
      const updated = await updateSetting(key, value.trim());
      setSettings(updated);
      setFieldState((s) => ({ ...s, [key]: "saved" }));
      setTimeout(() => {
        setFieldState((s) => (s[key] === "saved" ? { ...s, [key]: "idle" } : s));
      }, 1500);
    } catch (err) {
      setFieldState((s) => ({ ...s, [key]: "error" }));
      setError(err instanceof ApiError ? err.message : "Could not save that setting.");
    }
  }

  if (loading) {
    return (
      <div className="space-y-4 max-w-xl">
        <div className="bg-white rounded-2xl shadow-card border border-sage-100 p-6 space-y-6">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-3 w-full" />
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="space-y-1.5">
              <Skeleton className="h-3 w-32" />
              <Skeleton className="h-9 w-48" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 max-w-xl">
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 p-6">
        <h2 className="font-display font-semibold text-lg text-crate-950 mb-1">System Settings</h2>
        <p className="text-sm text-crate-800/50 mb-6">
          These used to only be changeable by editing the server's <code>.env</code> file — now they're
          editable here, and take effect immediately.
        </p>

        <div className="space-y-5">
          {FIELDS.map((field) => {
            const state = fieldState[field.key] ?? "idle";
            return (
              <div key={field.key}>
                <label className="block text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-1.5">
                  {field.label}
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type={field.type}
                    value={drafts[field.key] ?? ""}
                    onChange={(e) => setDrafts((d) => ({ ...d, [field.key]: e.target.value }))}
                    onBlur={(e) => save(field.key, e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
                    className={`border rounded-full px-4 py-2 text-sm bg-sage-50/60 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-colors duration-150 ${
                      field.type === "time" ? "w-40" : "w-64"
                    } ${state === "error" ? "border-tomato-500 ring-1 ring-tomato-500/30" : "border-sage-300"}`}
                  />
                  {state === "saving" && <span className="text-xs text-crate-800/35">Saving…</span>}
                  {state === "saved" && <span className="text-xs text-crate-700">✓ Saved</span>}
                  {state === "error" && <span className="text-xs text-tomato-600">Failed</span>}
                </div>
                <p className="text-xs text-crate-800/40 mt-1.5">{field.hint}</p>
              </div>
            );
          })}

          <MasterDataEmailField />
        </div>
      </div>
      {error && <p className="text-tomato-600 text-sm px-1">{error}</p>}

      <LateSubmissionPanel />
    </div>
  );
}

/**
 * The recipient for "Send to Master Data" on the Master Data Sheet page.
 * Separate from the fields above because it's admin-only and has its own
 * endpoint (it's deliberately not in the public GET /settings payload).
 * Until it's set, the send button returns a clear "set an address first"
 * error rather than emailing nowhere.
 */
function MasterDataEmailField() {
  const [saved, setSaved] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [state, setState] = useState<FieldState>("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMasterDataEmail()
      .then((r) => {
        setSaved(r.master_data_email);
        setDraft(r.master_data_email);
      })
      .catch(() => setSaved(""));
  }, []);

  async function save(value: string) {
    const trimmed = value.trim();
    if (saved === null || trimmed === "" || trimmed === saved) return;
    setState("saving");
    setError(null);
    try {
      const updated = await updateMasterDataEmail(trimmed);
      setSaved(updated.master_data_email);
      setDraft(updated.master_data_email);
      setState("saved");
      setTimeout(() => setState((s) => (s === "saved" ? "idle" : s)), 1500);
    } catch (err) {
      setState("error");
      setError(err instanceof ApiError ? err.message : "Could not save that address.");
    }
  }

  return (
    <div>
      <label className="block text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-1.5">
        Master Data recipient email
      </label>
      <div className="flex items-center gap-2">
        <input
          type="email"
          value={draft}
          placeholder="name@example.com"
          onChange={(e) => setDraft(e.target.value)}
          onBlur={(e) => save(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
          className={`border rounded-full px-4 py-2 text-sm bg-sage-50/60 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-colors duration-150 w-64 ${
            state === "error" ? "border-tomato-500 ring-1 ring-tomato-500/30" : "border-sage-300"
          }`}
        />
        {state === "saving" && <span className="text-xs text-crate-800/35">Saving…</span>}
        {state === "saved" && <span className="text-xs text-crate-700">✓ Saved</span>}
        {state === "error" && <span className="text-xs text-tomato-600">Failed</span>}
      </div>
      <p className="text-xs text-crate-800/40 mt-1.5">
        Where "Send to Master Data" on the Master Data Sheet page emails the Excel export. Needs the
        server's <code>SMTP_*</code> settings configured too.
      </p>
      {error && <p className="text-tomato-600 text-xs mt-1">{error}</p>}
    </div>
  );
}

/**
 * Admin's escape hatch for the daily cutoff: let one specific branch
 * submit (or keep editing) its order for one specific date past today's
 * normal cutoff, without changing the cutoff itself for anyone else.
 * Scoped to one branch + one date per grant — see order_service.py's
 * grant_late_submission for why this stays a one-off exception rather
 * than a standing rule.
 */
function LateSubmissionPanel() {
  const [branches, setBranches] = useState<Branch[]>([]);
  const [orderDate, setOrderDate] = useState(todayISO());
  const [selectedBranchId, setSelectedBranchId] = useState<number | "">("");
  const [exceptions, setExceptions] = useState<OrderDeadlineException[]>([]);
  const [loading, setLoading] = useState(true);
  const [granting, setGranting] = useState(false);
  const [revokingId, setRevokingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchBranches().then(setBranches).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    fetchOrderDeadlineExceptions(orderDate)
      .then(setExceptions)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load exceptions."))
      .finally(() => setLoading(false));
  }, [orderDate]);

  async function handleGrant() {
    if (!selectedBranchId) {
      setError("Choose a branch first.");
      return;
    }
    setError(null);
    setGranting(true);
    try {
      await grantOrderDeadlineException(selectedBranchId, orderDate);
      setSelectedBranchId("");
      const fresh = await fetchOrderDeadlineExceptions(orderDate);
      setExceptions(fresh);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not grant the exception.");
    } finally {
      setGranting(false);
    }
  }

  async function handleRevoke(branchId: number) {
    setRevokingId(branchId);
    try {
      await revokeOrderDeadlineException(branchId, orderDate);
      setExceptions((prev) => prev.filter((e) => e.branch_id !== branchId));
    } catch {
      setError("Could not withdraw that exception.");
    } finally {
      setRevokingId(null);
    }
  }

  const eligibleBranches = branches.filter(
    (b) => b.status === "ACTIVE" && !exceptions.some((e) => e.branch_id === b.id)
  );

  return (
    <div className="bg-white rounded-2xl shadow-card border border-sage-100 p-6">
      <h2 className="font-display font-semibold text-lg text-crate-950 mb-1">Late Order Submission</h2>
      <p className="text-sm text-crate-800/50 mb-5">
        Let one branch submit (or keep editing) its order for one date, past today's cutoff — a one-time
        exception, not a change to the cutoff itself.
      </p>

      <div className="flex flex-wrap items-end gap-3 mb-5">
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-1.5">
            Order Date
          </label>
          <input
            type="date"
            value={orderDate}
            onChange={(e) => setOrderDate(e.target.value)}
            className="border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-1.5">
            Branch
          </label>
          <select
            value={selectedBranchId}
            onChange={(e) => setSelectedBranchId(e.target.value ? Number(e.target.value) : "")}
            className="border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm min-w-[12rem] focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
          >
            <option value="">Select a branch…</option>
            {eligibleBranches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.branch_name}
              </option>
            ))}
          </select>
        </div>
        <button
          onClick={handleGrant}
          disabled={granting || !selectedBranchId}
          className="text-sm bg-gradient-to-b from-crate-700 to-crate-800 text-white rounded-full px-4 py-2 font-semibold hover:brightness-110 disabled:opacity-50 transition-all duration-150"
        >
          {granting ? "Granting…" : "Grant exception"}
        </button>
      </div>

      {error && <p className="text-tomato-600 text-sm mb-3">{error}</p>}

      {loading ? (
        <Skeleton className="h-10 w-full" />
      ) : exceptions.length === 0 ? (
        <p className="text-sm text-crate-800/40">No exceptions granted for this date.</p>
      ) : (
        <div className="divide-y divide-sage-100 border border-sage-100 rounded-xl overflow-hidden">
          {exceptions.map((e) => (
            <div key={e.branch_id} className="flex items-center justify-between px-4 py-2.5 text-sm">
              <div>
                <span className="text-crate-950 font-medium">{e.branch_name}</span>
                <span className="text-crate-800/40 text-xs ml-2">granted by {e.granted_by_username}</span>
              </div>
              <button
                onClick={() => handleRevoke(e.branch_id)}
                disabled={revokingId === e.branch_id}
                className="text-tomato-500 hover:text-tomato-600 text-xs font-medium disabled:opacity-50 transition-colors duration-150"
              >
                {revokingId === e.branch_id ? "Withdrawing…" : "Withdraw"}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
