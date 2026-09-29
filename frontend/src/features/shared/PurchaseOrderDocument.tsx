import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { BranchPurchaseOrder, PurchaseOrder, PurchaseOrderLine } from "../../api/purchaseOrders";
import { StatusBadge } from "./ui/Badge";
import Button from "./ui/Button";
import { formatDateTime, formatLongDate } from "./PriceSheetParts";

/** "supplier" = all branches combined; "matrix" = items x branches with
 *  the quantity for each branch; "branches" = every branch PO; "all" =
 *  all of those; a number = that one branch's PO. */
export type PoView = "supplier" | "matrix" | "branches" | "all" | number;

function money(n: number): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function PoStatusBadge({ status }: { status: PurchaseOrder["status"] }) {
  return status === "ISSUED" ? (
    <StatusBadge tone="success">Issued</StatusBadge>
  ) : (
    <StatusBadge tone="danger">Cancelled</StatusBadge>
  );
}

function LinesTable({ lines, total }: { lines: PurchaseOrderLine[]; total: number }) {
  const anyEstimated = lines.some((l) => l.price_is_estimated);
  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-crate-800/50 border-y border-crate-800/20">
              <th className="py-2 pr-2 font-medium w-8">#</th>
              <th className="py-2 px-2 font-medium">Item</th>
              <th className="py-2 px-2 font-medium text-right">Qty</th>
              <th className="py-2 px-2 font-medium">Unit</th>
              <th className="py-2 px-2 font-medium text-right whitespace-nowrap">Unit price (Rs.)</th>
              <th className="py-2 pl-2 font-medium text-right whitespace-nowrap">Amount (Rs.)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-sage-100">
            {lines.map((l, i) => (
              <tr key={`${l.product_id}:${l.unit_price}`} className="break-inside-avoid">
                <td className="py-1.5 pr-2 text-crate-800/40 tabular-nums">{i + 1}</td>
                <td className="py-1.5 px-2 text-crate-950">
                  {l.product_description}
                  <span className="text-crate-800/40 text-xs ml-1.5">{l.product_code}</span>
                  {l.notes && <div className="text-xs text-crate-800/50">{l.notes}</div>}
                </td>
                <td className="py-1.5 px-2 text-right tabular-nums">{l.quantity}</td>
                <td className="py-1.5 px-2 text-crate-800/60">{l.unit_code}</td>
                <td className="py-1.5 px-2 text-right tabular-nums">
                  {money(l.unit_price)}
                  {l.price_is_estimated && <span className="text-mango-600 text-[10px] ml-0.5">*</span>}
                </td>
                <td className="py-1.5 pl-2 text-right tabular-nums">{money(l.line_total)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-crate-800/30">
              <td colSpan={5} className="py-2 px-2 text-right font-semibold text-crate-950">
                Total
              </td>
              <td className="py-2 pl-2 text-right font-semibold text-crate-950 tabular-nums whitespace-nowrap">
                Rs. {money(total)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
      {anyEstimated && (
        <p className="text-[11px] text-crate-800/50 mt-1">
          * Price taken from the supplier's most recent quote for an earlier date.
        </p>
      )}
    </>
  );
}

/** Items down the side, one column per branch: what quantity of each item
 *  goes to which branch — how a supplier packs and loads the delivery. */
function BranchMatrixTable({ po }: { po: PurchaseOrder }) {
  const rows = new Map<string, { line: PurchaseOrderLine; qty: Map<number, number>; total: number }>();
  for (const b of po.branches) {
    for (const l of b.lines) {
      const key = `${l.product_id}:${l.unit_code}`;
      const row = rows.get(key) ?? { line: l, qty: new Map<number, number>(), total: 0 };
      row.qty.set(b.branch_id, (row.qty.get(b.branch_id) ?? 0) + l.quantity);
      row.total = Math.round((row.total + l.quantity) * 100) / 100;
      rows.set(key, row);
    }
  }
  const sorted = [...rows.values()].sort((a, b) => a.line.product_description.localeCompare(b.line.product_description));
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-xs text-crate-800/50 border-y border-crate-800/20">
            <th className="py-2 pr-2 font-medium text-left uppercase tracking-wide sticky left-0 bg-white">Item</th>
            <th className="py-2 px-2 font-medium text-left uppercase tracking-wide">Unit</th>
            {po.branches.map((b) => (
              <th key={b.branch_id} className="py-2 px-2 font-semibold text-crate-800 text-right border-l border-sage-100">
                {b.branch_name}
                <div className="text-[10px] font-normal text-crate-800/40">{b.branch_code}</div>
              </th>
            ))}
            <th className="py-2 pl-2 font-semibold text-crate-950 text-right border-l border-crate-800/20 uppercase tracking-wide">
              Total
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-sage-100">
          {sorted.map(({ line, qty, total }) => (
            <tr key={`${line.product_id}:${line.unit_code}`} className="break-inside-avoid">
              <td className="py-1.5 pr-2 text-crate-950 sticky left-0 bg-white">
                {line.product_description}
                <span className="text-crate-800/40 text-xs ml-1.5">{line.product_code}</span>
              </td>
              <td className="py-1.5 px-2 text-crate-800/60">{line.unit_code}</td>
              {po.branches.map((b) => (
                <td key={b.branch_id} className="py-1.5 px-2 text-right tabular-nums border-l border-sage-100">
                  {qty.has(b.branch_id) ? qty.get(b.branch_id) : <span className="text-crate-800/20">—</span>}
                </td>
              ))}
              <td className="py-1.5 pl-2 text-right tabular-nums font-semibold text-crate-950 border-l border-crate-800/20">
                {total}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-crate-800/30 text-xs">
            <td colSpan={2} className="py-2 pr-2 font-semibold text-crate-950 sticky left-0 bg-white">
              Amount (Rs.)
            </td>
            {po.branches.map((b) => (
              <td key={b.branch_id} className="py-2 px-2 text-right tabular-nums border-l border-sage-100">
                {money(b.total)}
              </td>
            ))}
            <td className="py-2 pl-2 text-right tabular-nums font-semibold text-crate-950 border-l border-crate-800/20 whitespace-nowrap">
              {money(po.total_amount)}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

/** Admin's e-signature on an issued PO: who issued it and when, above the
 *  "Authorised by" line. Not shown once the PO is cancelled. */
function ApprovedStamp({ po }: { po: PurchaseOrder }) {
  return (
    <div className="po-stamp inline-block -rotate-2 mb-2 rounded-lg border-2 border-[#16a34a] bg-[#16a34a]/5 px-3 py-1.5 text-[#15803d]">
      <p className="flex items-center gap-1.5 font-bold uppercase tracking-[0.2em] text-sm">
        <svg width="14" height="14" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M1 5l3 3 5-6" />
        </svg>
        Approved
      </p>
      <p className="text-[10px] leading-snug whitespace-nowrap">
        E-signed{po.issued_by_name ? ` by ${po.issued_by_name}` : ""} · {formatDateTime(po.issued_at)}
      </p>
      <p className="text-[10px] leading-snug">
        {po.po_number} · revision {po.revision}
      </p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-crate-800/40 font-semibold">{label}</p>
      <div className="text-sm text-crate-950 mt-0.5">{children}</div>
    </div>
  );
}

/** One printable page: the supplier PO when `branch` is omitted, otherwise that branch's PO. */
function PoPage({
  po,
  branch,
  matrix = false,
  pageLabel,
}: {
  po: PurchaseOrder;
  branch?: BranchPurchaseOrder;
  matrix?: boolean;
  pageLabel?: string;
}) {
  const s = po.supplier;
  return (
    <section className={`po-page space-y-5 ${matrix ? "po-page-wide" : ""}`}>
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-crate-800/20 pb-4">
        <div>
          <p className="font-display text-xl font-semibold text-crate-900">SPAR Sri Lanka</p>
          <p className="text-xs text-crate-800/50">Fresh Produce Procurement</p>
        </div>
        <div className="text-right">
          <p className="text-xs uppercase tracking-[0.2em] text-crate-800/50 font-semibold">
            {branch
              ? `Purchase order · ${branch.branch_name}`
              : matrix
              ? "Purchase order — items by branch"
              : "Purchase order"}
          </p>
          <p className="font-mono text-lg font-semibold text-crate-950">{branch ? branch.po_number : po.po_number}</p>
          <p className="text-xs text-crate-800/50">
            Revision {po.revision}
            {branch ? ` · part of ${po.po_number}` : ""}
          </p>
          {pageLabel && <p className="text-xs font-semibold text-crate-800/70 mt-0.5">{pageLabel}</p>}
        </div>
      </header>

      {po.status === "CANCELLED" && (
        <p className="rounded-lg border-2 border-tomato-500/60 text-tomato-600 font-semibold text-center py-2 uppercase tracking-wide">
          Cancelled{po.cancelled_at ? ` on ${formatDateTime(po.cancelled_at)}` : ""} — do not supply
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Supplier">
          <p className="font-semibold">{s.supplier_name}</p>
          <p className="text-crate-800/60 text-xs">Code {s.supplier_code}</p>
          {s.address && <p className="text-crate-800/70 text-xs whitespace-pre-line">{s.address}</p>}
          {(s.contact_person || s.phone) && (
            <p className="text-crate-800/70 text-xs">{[s.contact_person, s.phone].filter(Boolean).join(" · ")}</p>
          )}
          {s.email && <p className="text-crate-800/70 text-xs">{s.email}</p>}
          {s.company_number && <p className="text-crate-800/70 text-xs">Reg. no. {s.company_number}</p>}
        </Field>
        <Field label="Deliver to">
          {branch ? (
            <>
              <p className="font-semibold">SPAR {branch.branch_name}</p>
              <p className="text-crate-800/60 text-xs">Branch {branch.branch_code}</p>
              {branch.branch_location && <p className="text-crate-800/70 text-xs">{branch.branch_location}</p>}
            </>
          ) : (
            <>
              <p className="font-semibold">
                {po.branch_count} SPAR branch{po.branch_count === 1 ? "" : "es"}
              </p>
              <p className="text-crate-800/60 text-xs">
                {matrix ? "Quantity for each branch below" : "Per the branch purchase orders below"}
              </p>
            </>
          )}
        </Field>
        <Field label="Delivery date">
          <p className="font-semibold">{formatLongDate(po.delivery_date)}</p>
          <p className="text-crate-800/60 text-xs mt-1">
            Issued {formatDateTime(po.issued_at)}
            {po.issued_by_name ? ` by ${po.issued_by_name}` : ""}
          </p>
        </Field>
      </div>

      {branch ? (
        <LinesTable lines={branch.lines} total={branch.total} />
      ) : matrix ? (
        <BranchMatrixTable po={po} />
      ) : (
        <>
          <LinesTable lines={po.consolidated_lines} total={po.total_amount} />
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-crate-800/50 mb-1.5">
              Branch purchase orders
            </p>
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-crate-800/50 border-y border-crate-800/20">
                  <th className="py-1.5 pr-2 font-medium">PO number</th>
                  <th className="py-1.5 px-2 font-medium">Branch</th>
                  <th className="py-1.5 px-2 font-medium text-right">Items</th>
                  <th className="py-1.5 pl-2 font-medium text-right">Amount (Rs.)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-sage-100">
                {po.branches.map((b) => (
                  <tr key={b.branch_id}>
                    <td className="py-1.5 pr-2 font-mono text-xs">{b.po_number}</td>
                    <td className="py-1.5 px-2">{b.branch_name}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{b.lines.length}</td>
                    <td className="py-1.5 pl-2 text-right tabular-nums">{money(b.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="grid grid-cols-2 gap-10 pt-10 items-end break-inside-avoid">
        <div>
          {po.status === "ISSUED" && <ApprovedStamp po={po} />}
          <div className="border-t border-crate-800/40 pt-1.5 text-xs text-crate-800/60">
            Authorised by — SPAR Fresh Procurement
          </div>
        </div>
        <div className="border-t border-crate-800/40 pt-1.5 text-xs text-crate-800/60">
          {branch ? `Received by — SPAR ${branch.branch_name}` : `Accepted by — ${s.supplier_name}`}
        </div>
      </div>
    </section>
  );
}

export function PurchaseOrderDocument({ po, view }: { po: PurchaseOrder; view: PoView }) {
  const branchPages =
    view === "branches" || view === "all" ? po.branches : typeof view === "number" ? po.branches.filter((b) => b.branch_id === view) : [];
  // Every page of this view, in order, so each can say "Page 2 of 3".
  const pages: { key: string; branch?: BranchPurchaseOrder; matrix?: boolean }[] = [
    ...(view === "supplier" || view === "all" ? [{ key: "supplier" }] : []),
    ...(view === "matrix" || view === "all" ? [{ key: "matrix", matrix: true }] : []),
    ...branchPages.map((b) => ({ key: `branch-${b.branch_id}`, branch: b })),
  ];
  return (
    <div className="space-y-10">
      {pages.map((p, i) => (
        <PoPage
          key={p.key}
          po={po}
          branch={p.branch}
          matrix={p.matrix}
          pageLabel={pages.length > 1 ? `Page ${i + 1} of ${pages.length}` : undefined}
        />
      ))}
    </div>
  );
}

/**
 * The PO on screen with a view picker and a Print / Save as PDF button.
 * Printing renders the chosen view into a body-level portal that stays in
 * normal page flow (see index.css), so a long PO runs onto as many pages
 * as it needs and each branch PO starts on a new page.
 */
export function PurchaseOrderViewer({
  po,
  actions,
  branchOnly = false,
  defaultView = "branches",
}: {
  po: PurchaseOrder;
  actions?: React.ReactNode;
  /** Branch accounts: show just their branch PO, no view picker. */
  branchOnly?: boolean;
  defaultView?: PoView;
}) {
  const initialView: PoView = branchOnly && po.branches.length === 1 ? po.branches[0].branch_id : defaultView;
  const [view, setView] = useState<PoView>(initialView);

  useEffect(() => {
    setView(initialView);
  }, [po.id, initialView]);

  useEffect(() => {
    const done = () => document.body.classList.remove("po-printing");
    window.addEventListener("afterprint", done);
    return () => {
      window.removeEventListener("afterprint", done);
      done();
    };
  }, []);

  function print() {
    document.body.classList.add("po-printing");
    window.print();
  }

  return (
    <div className="space-y-4">
      <div className="no-print flex flex-wrap items-center gap-3">
        {!branchOnly && (
          <select
            value={String(view)}
            onChange={(e) => {
              const v = e.target.value;
              setView(v === "supplier" || v === "matrix" || v === "branches" || v === "all" ? v : Number(v));
            }}
            className="border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white"
          >
            <option value="branches">
              Branch-wise PO — {po.branches.length} page{po.branches.length === 1 ? "" : "s"}, one per branch
            </option>
            <option value="supplier">Combined PO (all branches on one page)</option>
            <option value="matrix">Items by branch (quantity per branch)</option>
            {po.branches.map((b) => (
              <option key={b.branch_id} value={b.branch_id}>
                Branch PO — {b.branch_name}
              </option>
            ))}
            <option value="all">Everything</option>
          </select>
        )}
        <Button variant="secondary" size="sm" onClick={print}>
          Print / Save as PDF
        </Button>
        {actions && <div className="flex flex-wrap gap-2 ml-auto">{actions}</div>}
      </div>
      <PurchaseOrderDocument po={po} view={view} />
      {createPortal(
        <div className="po-print-root">
          <PurchaseOrderDocument po={po} view={view} />
        </div>,
        document.body
      )}
    </div>
  );
}
