import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import { AuditLog, fetchAuditLogActions, fetchAuditLogs } from "../../api/auditLogs";
import EmptyState from "../shared/EmptyState";
import { StatusBadge } from "../shared/ui/Badge";
import { SkeletonTable } from "../shared/ui/Skeleton";
import { IconClock } from "../shared/Icons";

const ACTION_LABELS: Record<string, string> = {
  LOGIN: "Login",
  PASSWORD_CHANGED: "Password changed",
  ORDER_SUBMITTED: "Order submitted",
  DELIVERY_CONFIRMED: "Delivery confirmed",
  PRICES_SUBMITTED: "Prices submitted",
  SUPPLIERS_ASSIGNED: "Suppliers assigned",
  SUPPLIER_ORDER_SET: "Supplier order set",
  SUPPLIER_PRICE_ADJUSTED: "Price adjusted",
  SUPPLIER_PRICE_SENT: "Price sent",
  SUPPLIER_PRICE_UNSENT: "Price withdrawn",
};

function actionTone(action: string): "success" | "warning" | "info" | "neutral" {
  if (action.includes("SENT") || action.includes("CONFIRMED") || action.includes("SUBMITTED")) return "success";
  if (action.includes("UNSENT") || action.includes("ADJUSTED")) return "warning";
  if (action === "LOGIN" || action === "PASSWORD_CHANGED") return "info";
  return "neutral";
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function AdminAuditLog() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [actions, setActions] = useState<string[]>([]);
  const [actionFilter, setActionFilter] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAuditLogActions()
      .then(setActions)
      .catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchAuditLogs({ limit: 200, action: actionFilter || undefined })
      .then(setLogs)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load the audit log."))
      .finally(() => setLoading(false));
  }, [actionFilter]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return logs;
    return logs.filter(
      (l) =>
        (l.username ?? "").toLowerCase().includes(q) ||
        (l.description ?? "").toLowerCase().includes(q) ||
        l.action.toLowerCase().includes(q)
    );
  }, [logs, search]);

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 p-4 flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="Search user or description…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[12rem] border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
        />
        <select
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          className="border border-sage-300 bg-sage-50/60 rounded-full px-3.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
        >
          <option value="">All actions</option>
          {actions.map((a) => (
            <option key={a} value={a}>
              {ACTION_LABELS[a] ?? a}
            </option>
          ))}
        </select>
        <span className="text-xs text-crate-800/40 ml-auto">
          {filtered.length} of {logs.length} entries · most recent 200
        </span>
      </div>

      <div className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-hidden">
        {loading ? (
          <SkeletonTable rows={8} columns={5} />
        ) : error ? (
          <p className="text-tomato-600 text-sm p-6">{error}</p>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={<IconClock width={20} height={20} />}
            title="No activity yet"
            description="Actions like price adjustments, order submissions, and logins will appear here."
          />
        ) : (
          <div className="divide-y divide-sage-100">
            {filtered.map((log, i) => (
              <div
                key={log.id}
                className="flex items-start gap-3 px-5 py-3 motion-safe:animate-fade-up"
                style={{ animationDuration: "0.3s", animationDelay: `${Math.min(i, 12) * 20}ms`, animationFillMode: "backwards" }}
              >
                <span className="text-xs text-crate-800/35 whitespace-nowrap w-32 shrink-0 pt-1">
                  {formatTime(log.created_at)}
                </span>
                <StatusBadge tone={actionTone(log.action)}>{ACTION_LABELS[log.action] ?? log.action}</StatusBadge>
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-crate-950">{log.description ?? "—"}</p>
                  <p className="text-xs text-crate-800/40 mt-0.5">
                    {log.username ?? "System"}
                    {log.role ? ` · ${log.role}` : ""}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
