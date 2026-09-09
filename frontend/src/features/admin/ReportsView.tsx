import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import { AdminReport, fetchAdminReport, downloadReport } from "../../api/reports";
import { CategoryBadge } from "../shared/ui/CategoryBadge";

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}
function daysAgoISO(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}
function formatShort(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
function rs(n: number): string {
  return `Rs. ${n.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

const RANGE_PRESETS = [
  { label: "7 days", days: 7 },
  { label: "14 days", days: 14 },
  { label: "30 days", days: 30 },
];

export default function ReportsView() {
  const [startDate, setStartDate] = useState(daysAgoISO(6));
  const [endDate, setEndDate] = useState(todayISO());
  const [report, setReport] = useState<AdminReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchAdminReport(startDate, endDate)
      .then((r) => {
        if (!cancelled) setReport(r);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load the report.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [startDate, endDate]);

  const maxDailySpend = useMemo(
    () => Math.max(1, ...(report?.daily.map((d) => d.spend) ?? [0])),
    [report]
  );
  const maxSupplierSpend = useMemo(
    () => Math.max(1, ...(report?.by_supplier.map((s) => s.spend) ?? [0])),
    [report]
  );
  const maxCategorySpend = useMemo(
    () => Math.max(1, ...(report?.by_category.map((c) => c.spend) ?? [0])),
    [report]
  );

  async function handleDownload() {
    setDownloading(true);
    try {
      await downloadReport(startDate, endDate);
    } catch {
      setError("Could not download the report. Please try again.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-2xl shadow-sm p-4 flex flex-wrap items-center gap-3 justify-between">
        <div className="flex flex-wrap items-center gap-2">
          {RANGE_PRESETS.map((p) => (
            <button
              key={p.label}
              onClick={() => {
                setEndDate(todayISO());
                setStartDate(daysAgoISO(p.days - 1));
              }}
              className="text-sm px-3 py-1.5 rounded-full bg-sage-100 text-crate-800 font-medium hover:bg-sage-200 transition-colors duration-150"
            >
              Last {p.label}
            </button>
          ))}
          <span className="text-sage-300 mx-1">|</span>
          <input
            type="date"
            value={startDate}
            max={endDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="border border-sage-300 rounded-full px-3 py-1.5 text-sm text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30"
          />
          <span className="text-crate-800/50 text-sm">to</span>
          <input
            type="date"
            value={endDate}
            min={startDate}
            max={todayISO()}
            onChange={(e) => setEndDate(e.target.value)}
            className="border border-sage-300 rounded-full px-3 py-1.5 text-sm text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30"
          />
        </div>
        <button
          onClick={handleDownload}
          disabled={downloading || !report}
          className="text-sm bg-crate-700 text-white rounded-full px-4 py-1.5 font-medium hover:bg-crate-800 active:scale-[0.98] transition-all duration-150 disabled:opacity-50"
        >
          {downloading ? "Preparing…" : "Download Excel"}
        </button>
      </div>

      {error && <p className="text-tomato-600 text-sm">{error}</p>}

      {loading && !report ? (
        <div className="bg-white rounded-2xl shadow-sm p-6 text-crate-800/40 text-sm">Loading report…</div>
      ) : report ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard label="Branch orders" value={String(report.totals.total_orders)} accent="blue" />
            <KpiCard
              label="Fulfillment"
              value={`${Math.round(report.totals.fulfillment_rate * 100)}%`}
              hint={`${report.totals.assigned_orders} of ${report.totals.total_orders} fulfilled`}
              accent="violet"
            />
            <KpiCard label="Total spend" value={rs(report.totals.total_spend)} accent="emerald" />
            <KpiCard label="Days covered" value={String(report.totals.days_count)} accent="amber" />
          </div>

          <div className="bg-white rounded-2xl shadow-sm p-5">
            <h3 className="font-display font-semibold text-sm text-crate-950 mb-4">Spend by day</h3>
            {report.daily.length === 0 ? (
              <p className="text-sm text-crate-800/40">No orders in this range.</p>
            ) : (
              <div className="space-y-2">
                {report.daily.map((d) => (
                  <div key={d.delivery_date} className="flex items-center gap-3 text-sm">
                    <span className="w-16 text-crate-800/60 shrink-0">{formatShort(d.delivery_date)}</span>
                    <div className="flex-1 bg-sage-50 rounded-full h-6 overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-crate-600 to-crate-700 rounded-full transition-all duration-500"
                        style={{ width: `${(d.spend / maxDailySpend) * 100}%` }}
                      />
                    </div>
                    <span className="w-24 text-right text-crate-950 font-medium shrink-0">{rs(d.spend)}</span>
                    <span className="w-20 text-right text-crate-800/50 text-xs shrink-0">
                      {d.assigned_orders_count}/{d.orders_count} fulfilled
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="grid md:grid-cols-2 gap-5">
            <div className="bg-white rounded-2xl shadow-sm p-5">
              <h3 className="font-display font-semibold text-sm text-crate-950 mb-4">Spend by supplier</h3>
              {report.by_supplier.length === 0 ? (
                <p className="text-sm text-crate-800/40">No assignments in this range.</p>
              ) : (
                <div className="space-y-2">
                  {report.by_supplier.map((s) => (
                    <div key={s.supplier_id} className="flex items-center gap-3 text-sm">
                      <span className="w-28 truncate text-crate-800/70 shrink-0">{s.supplier_name}</span>
                      <div className="flex-1 bg-sage-50 rounded-full h-5 overflow-hidden">
                        <div
                          className="h-full bg-mango-400 rounded-full transition-all duration-500"
                          style={{ width: `${(s.spend / maxSupplierSpend) * 100}%` }}
                        />
                      </div>
                      <span className="w-20 text-right text-crate-950 font-medium shrink-0">{rs(s.spend)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="bg-white rounded-2xl shadow-sm p-5">
              <h3 className="font-display font-semibold text-sm text-crate-950 mb-4">Spend by category</h3>
              {report.by_category.length === 0 ? (
                <p className="text-sm text-crate-800/40">No assignments in this range.</p>
              ) : (
                <div className="space-y-2">
                  {report.by_category.map((c) => (
                    <div key={c.category_name} className="flex items-center gap-3 text-sm">
                      <span className="w-28 truncate text-crate-800/70 shrink-0">{c.category_name}</span>
                      <div className="flex-1 bg-sage-50 rounded-full h-5 overflow-hidden">
                        <div
                          className="h-full bg-tomato-500 rounded-full transition-all duration-500"
                          style={{ width: `${(c.spend / maxCategorySpend) * 100}%` }}
                        />
                      </div>
                      <span className="w-20 text-right text-crate-950 font-medium shrink-0">{rs(c.spend)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="bg-white rounded-2xl shadow-sm p-5">
            <h3 className="font-display font-semibold text-sm text-crate-950 mb-4">
              Top products by quantity ordered
            </h3>
            {report.top_products.length === 0 ? (
              <p className="text-sm text-crate-800/40">No orders in this range.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-crate-800/40 text-left text-xs uppercase">
                    <th className="pb-2 font-medium">Product</th>
                    <th className="pb-2 font-medium">Category</th>
                    <th className="pb-2 font-medium text-right">Quantity</th>
                    <th className="pb-2 font-medium text-right">Spend</th>
                    <th className="pb-2 font-medium text-right">Orders</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-sage-100">
                  {report.top_products.map((p) => (
                    <tr key={p.product_id}>
                      <td className="py-2 text-crate-950">{p.description}</td>
                      <td className="py-2">
                        <CategoryBadge name={p.category_name} />
                      </td>
                      <td className="py-2 text-right text-crate-800">
                        {p.total_quantity} {p.unit_code}
                      </td>
                      <td className="py-2 text-right text-crate-950 font-medium">{rs(p.total_spend)}</td>
                      <td className="py-2 text-right text-crate-800/60">{p.order_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}

const KPI_ACCENTS = {
  blue: { bar: "bg-blue-500", dot: "bg-blue-500" },
  violet: { bar: "bg-violet-500", dot: "bg-violet-500" },
  emerald: { bar: "bg-emerald-500", dot: "bg-emerald-500" },
  amber: { bar: "bg-amber-500", dot: "bg-amber-500" },
} as const;

function KpiCard({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string;
  hint?: string;
  accent: keyof typeof KPI_ACCENTS;
}) {
  const { bar, dot } = KPI_ACCENTS[accent];
  return (
    <div className="bg-white rounded-2xl shadow-sm overflow-hidden">
      <div className={`h-1 ${bar}`} />
      <div className="p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-crate-800/50 flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${dot}`} aria-hidden="true" />
          {label}
        </p>
        <p className="font-display font-bold text-2xl text-crate-950 mt-1">{value}</p>
        {hint && <p className="text-xs text-crate-800/40 mt-0.5">{hint}</p>}
      </div>
    </div>
  );
}
