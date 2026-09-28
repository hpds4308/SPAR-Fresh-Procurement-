import { StatusBadge } from "./ui/Badge";
import { PriceSheet, PriceSheetItem, RowApprovalStatus, SheetStatus } from "../../api/priceApprovals";

type Tone = "neutral" | "success" | "warning" | "danger" | "info";

const SHEET_STATUS: Record<SheetStatus, { label: string; tone: Tone }> = {
  PENDING: { label: "Awaiting signature", tone: "warning" },
  APPROVED: { label: "Approved", tone: "success" },
  REJECTED: { label: "Rejected", tone: "danger" },
  EXPIRED: { label: "Expired", tone: "neutral" },
  VOIDED: { label: "Cancelled", tone: "neutral" },
  WITHDRAWN: { label: "Withdrawn", tone: "neutral" },
};

export function SheetStatusBadge({ status }: { status: SheetStatus }) {
  const meta = SHEET_STATUS[status];
  return <StatusBadge tone={meta.tone}>{meta.label}</StatusBadge>;
}

/** Compact pill for one cell on the price tables. */
export function RowApprovalBadge({ status }: { status: RowApprovalStatus }) {
  if (!status) return null;
  const meta =
    status === "DRAFT"
      ? { label: "Draft", cls: "bg-white text-crate-800/50 border border-sage-300" }
      : status === "PENDING"
      ? { label: "Awaiting signature", cls: "bg-mango-500/20 text-[#8A5A0D]" }
      : status === "APPROVED"
      ? { label: "Approved", cls: "bg-crate-700 text-white" }
      : status === "REJECTED"
      ? { label: "Rejected", cls: "bg-tomato-500/15 text-tomato-600" }
      : { label: "Expired", cls: "bg-sage-100 text-crate-800/50" };
  return (
    <span className={`text-[10px] uppercase tracking-wide rounded-full px-2 py-0.5 font-semibold whitespace-nowrap ${meta.cls}`}>
      {meta.label}
    </span>
  );
}

export function formatLongDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * A sheet can be signed until its delivery date starts (midnight, Colombo
 * time) — phrased as "the end of <day before>", since "12:00 AM on the
 * delivery date" is easy to misread as a day later.
 */
export function formatSignDeadline(deliveryDateIso: string): string {
  const d = new Date(deliveryDateIso + "T00:00:00");
  d.setDate(d.getDate() - 1);
  return `the end of ${d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}`;
}

function rs(n: number): string {
  return `Rs. ${n.toFixed(2)}`;
}

export function PriceSheetItemsTable({ items, priceLabel }: { items: PriceSheetItem[]; priceLabel: string }) {
  return (
    <>
      {/* Phones: one stacked row per item, so the SPAR price is never scrolled off-screen. */}
      <ul className="sm:hidden divide-y divide-sage-100 border-y border-sage-100">
        {items.map((item) => (
          <li key={item.supplier_price_id} className="py-2.5">
            <p className="text-crate-950 text-sm">
              {item.product_description}
              <span className="text-crate-800/35 text-xs ml-1.5">{item.product_code}</span>
            </p>
            <p className="text-sm mt-0.5 flex flex-wrap gap-x-3">
              <span className="text-crate-800/60">
                {priceLabel}: <span className="tabular-nums">{rs(item.supplier_price)}</span>
              </span>
              <span className="text-crate-800/60">
                SPAR: <span className="font-semibold text-crate-950 tabular-nums">{rs(item.adjusted_price)}</span>
                <span className="text-crate-800/40"> /{item.unit_code}</span>
              </span>
            </p>
          </li>
        ))}
      </ul>
      <ItemsTable items={items} priceLabel={priceLabel} />
    </>
  );
}

function ItemsTable({ items, priceLabel }: { items: PriceSheetItem[]; priceLabel: string }) {
  return (
    <div className="hidden sm:block overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-crate-800/40 text-left text-xs uppercase tracking-wide border-b border-sage-100">
            <th className="py-2 pr-3 font-medium">Item</th>
            <th className="py-2 px-3 font-medium text-right">Unit</th>
            <th className="py-2 px-3 font-medium text-right">{priceLabel}</th>
            <th className="py-2 px-3 font-medium text-right">SPAR price</th>
            <th className="py-2 pl-3 font-medium text-right">Difference</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-sage-100">
          {items.map((item) => {
            const diff = item.adjusted_price - item.supplier_price;
            return (
              <tr key={item.supplier_price_id}>
                <td className="py-2 pr-3 text-crate-950">
                  {item.product_description}
                  <span className="text-crate-800/35 text-xs ml-1.5">{item.product_code}</span>
                </td>
                <td className="py-2 px-3 text-right text-crate-800/50">{item.unit_code}</td>
                <td className="py-2 px-3 text-right text-crate-800/70 tabular-nums">{rs(item.supplier_price)}</td>
                <td className="py-2 px-3 text-right font-semibold text-crate-950 tabular-nums">{rs(item.adjusted_price)}</td>
                <td className={`py-2 pl-3 text-right tabular-nums ${diff === 0 ? "text-crate-800/40" : "text-crate-800/70"}`}>
                  {diff === 0 ? "—" : `${diff > 0 ? "+" : "−"}${Math.abs(diff).toFixed(2)}`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** The signed record: who signed, when, the drawn signature and the sheet's fingerprint. */
export function SignatureRecord({ sheet }: { sheet: PriceSheet }) {
  if (sheet.status !== "APPROVED" && !sheet.signature_image) return null;
  return (
    <div className="rounded-xl border border-crate-700/20 bg-sage-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-crate-800/50 mb-3">Electronic signature</p>
      <div className="flex flex-wrap gap-6 items-end">
        {sheet.signature_image && (
          <div className="bg-white border border-sage-200 rounded-lg p-2">
            <img src={sheet.signature_image} alt={`Signature of ${sheet.signer_name ?? "supplier"}`} className="h-20 w-auto" />
          </div>
        )}
        <dl className="text-sm grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <dt className="text-crate-800/50">Signed by</dt>
          <dd className="text-crate-950 font-medium">{sheet.signer_name}</dd>
          <dt className="text-crate-800/50">Account</dt>
          <dd className="text-crate-950">{sheet.responded_by_name ?? "—"}</dd>
          <dt className="text-crate-800/50">Signed at</dt>
          <dd className="text-crate-950">{sheet.responded_at ? formatDateTime(sheet.responded_at) : "—"}</dd>
          {sheet.signer_ip && (
            <>
              <dt className="text-crate-800/50">IP address</dt>
              <dd className="text-crate-950 break-all">{sheet.signer_ip}</dd>
            </>
          )}
        </dl>
      </div>
      <p className="text-[11px] text-crate-800/40 mt-3 break-all">
        Sheet fingerprint (SHA-256): <span className="font-mono">{sheet.snapshot_hash}</span>
      </p>
    </div>
  );
}

/**
 * Printable agreement: the items plus the signature record, wrapped in
 * .print-area so window.print() (Save as PDF) outputs just this.
 */
export function PriceSheetDocument({ sheet, priceLabel }: { sheet: PriceSheet; priceLabel: string }) {
  return (
    <div className="print-area space-y-5">
      <div>
        <p className="text-xs uppercase tracking-wide text-crate-800/40 font-semibold">
          SPAR price sheet #{sheet.id}
        </p>
        <h3 className="font-display text-lg font-semibold text-crate-950 mt-0.5">{sheet.supplier_name}</h3>
        <p className="text-sm text-crate-800/60 mt-1">
          Delivery on {formatLongDate(sheet.delivery_date)} · sent {formatDateTime(sheet.sent_at)}
          {sheet.sent_by_name ? ` by ${sheet.sent_by_name}` : ""}
        </p>
      </div>
      <PriceSheetItemsTable items={sheet.items} priceLabel={priceLabel} />
      {sheet.status === "APPROVED" && (
        <p className="text-sm text-crate-800/80">
          {sheet.signer_name} agreed on behalf of {sheet.supplier_name} to supply the items above at the SPAR prices
          shown for delivery on {formatLongDate(sheet.delivery_date)}.
        </p>
      )}
      <SignatureRecord sheet={sheet} />
    </div>
  );
}
