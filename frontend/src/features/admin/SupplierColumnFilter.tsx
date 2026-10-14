import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AdminSupplierPrice } from "../../api/pricing";

// Excel-style filter on one supplier's column of Supplier Prices: it narrows
// the ROWS (items) to those matching this supplier's cell, while every other
// supplier's columns stay visible for those rows.
export type ColumnFilter =
  | "priced"
  | "missing"
  | "lowest"
  | "adjusted"
  | "DRAFT"
  | "PENDING"
  | "APPROVED"
  | "REJECTED"
  | "EXPIRED";

export type SortDir = "asc" | "desc";

export const FILTER_LABELS: Record<ColumnFilter, string> = {
  priced: "Items they priced",
  missing: "Items they didn't price",
  lowest: "Items where they're cheapest",
  adjusted: "Items with an adjusted price",
  DRAFT: "Adjusted — draft (not sent)",
  PENDING: "Awaiting signature",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  EXPIRED: "Not approved",
};

const GROUPS: { title: string; options: ColumnFilter[] }[] = [
  { title: "Show only", options: ["priced", "missing", "lowest", "adjusted"] },
  { title: "Approval status", options: ["DRAFT", "PENDING", "APPROVED", "REJECTED", "EXPIRED"] },
];

/** Whether one supplier's cell for an item passes that supplier's column filter. */
export function cellMatches(filter: ColumnFilter, cell: AdminSupplierPrice | undefined): boolean {
  switch (filter) {
    case "priced":
      return cell !== undefined;
    case "missing":
      return cell === undefined;
    case "lowest":
      return cell?.is_lowest_for_product === true;
    case "adjusted":
      return cell?.adjusted_price != null;
    default:
      return cell?.approval_status === filter;
  }
}

function FunnelIcon({ filled }: { filled: boolean }) {
  return (
    <svg viewBox="0 0 20 20" width={14} height={14} fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth={1.7} strokeLinejoin="round">
      <path d="M3 4h14l-5.5 6.5V16l-3 1.5v-7L3 4Z" />
    </svg>
  );
}

export default function SupplierColumnFilter({
  supplierName,
  filter,
  sortDir,
  onFilter,
  onSort,
}: {
  supplierName: string;
  filter: ColumnFilter | undefined;
  sortDir: SortDir | undefined;
  onFilter: (f: ColumnFilter | undefined) => void;
  onSort: (d: SortDir | undefined) => void;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const active = filter !== undefined || sortDir !== undefined;

  // The table scrolls inside its own box, which would clip a dropdown, so the
  // menu is portalled to <body> and placed under the button.
  useLayoutEffect(() => {
    if (!open || !buttonRef.current) return;
    const r = buttonRef.current.getBoundingClientRect();
    const width = 240;
    setPos({ top: r.bottom + 6, left: Math.max(8, Math.min(r.left + r.width / 2 - width / 2, window.innerWidth - width - 8)) });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (e.target instanceof Node && (menuRef.current?.contains(e.target) || buttonRef.current?.contains(e.target))) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", close);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const option = (selected: boolean, label: string, onClick: () => void) => (
    <button
      key={label}
      type="button"
      onClick={() => {
        onClick();
        setOpen(false);
      }}
      className={`w-full text-left px-3 py-1.5 text-sm flex items-center gap-2 hover:bg-sage-50 ${
        selected ? "text-crate-800 font-semibold" : "text-crate-950"
      }`}
    >
      <span className={`w-3 text-crate-700 ${selected ? "" : "invisible"}`}>✓</span>
      {label}
    </button>
  );

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={`Filter or sort by ${supplierName}`}
        aria-expanded={open}
        title={`Filter or sort by ${supplierName}`}
        className={`inline-flex items-center justify-center w-6 h-6 rounded-md border transition-colors ${
          active
            ? "bg-crate-700 border-crate-700 text-white"
            : "bg-white border-sage-300 text-crate-800/50 hover:text-crate-800 hover:border-crate-700"
        }`}
      >
        <FunnelIcon filled={active} />
      </button>
      {open &&
        pos &&
        createPortal(
          <div
            ref={menuRef}
            role="menu"
            style={{ top: pos.top, left: pos.left, width: 240 }}
            className="fixed z-[70] bg-white border border-sage-200 rounded-xl shadow-lg py-1.5 normal-case tracking-normal text-left"
          >
            <p className="px-3 pt-1 pb-1.5 text-[11px] font-semibold uppercase tracking-wide text-crate-800/45 truncate">
              {supplierName}
            </p>
            <p className="px-3 pt-1 text-[10px] font-semibold uppercase tracking-wide text-crate-800/40">Sort by their price</p>
            {option(sortDir === "asc", "Low → high", () => onSort(sortDir === "asc" ? undefined : "asc"))}
            {option(sortDir === "desc", "High → low", () => onSort(sortDir === "desc" ? undefined : "desc"))}
            {GROUPS.map((g) => (
              <div key={g.title} className="border-t border-sage-100 mt-1 pt-1">
                <p className="px-3 pt-1 text-[10px] font-semibold uppercase tracking-wide text-crate-800/40">{g.title}</p>
                {g.options.map((f) => option(filter === f, FILTER_LABELS[f], () => onFilter(filter === f ? undefined : f)))}
              </div>
            ))}
            {active && (
              <div className="border-t border-sage-100 mt-1 pt-1">
                {option(false, "Clear filter & sort", () => {
                  onFilter(undefined);
                  onSort(undefined);
                })}
              </div>
            )}
          </div>,
          document.body
        )}
    </>
  );
}
