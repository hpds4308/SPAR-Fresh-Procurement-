import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { Settings, fetchSettings, updateSetting } from "../../api/settings";
import { Skeleton } from "../shared/ui/Skeleton";

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
        </div>
      </div>
      {error && <p className="text-tomato-600 text-sm px-1">{error}</p>}
    </div>
  );
}
