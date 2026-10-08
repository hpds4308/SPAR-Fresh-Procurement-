import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import {
  PriceSheet,
  PriceSheetSummary,
  approveSheet,
  fetchMySheet,
  fetchMySheets,
  rejectSheet,
} from "../../api/priceApprovals";
import EmptyState from "../shared/EmptyState";
import { IconShield } from "../shared/Icons";
import {
  PriceSheetDocument,
  SheetStatusBadge,
  formatDateTime,
  formatLongDate,
  formatSignDeadline,
} from "../shared/PriceSheetParts";
import SignaturePad, { SignaturePadHandle } from "../shared/SignaturePad";
import Button from "../shared/ui/Button";
import { SkeletonTable } from "../shared/ui/Skeleton";

const card = "bg-white rounded-2xl shadow-card border border-sage-100";
const input =
  "w-full border border-sage-300 bg-sage-50/60 rounded-xl px-3.5 py-2 text-sm text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150";

function errorText(err: unknown, fallback: string): string {
  return err instanceof ApiError && typeof err.message === "string" && !err.message.startsWith("[object")
    ? err.message
    : fallback;
}

export default function PriceApprovals({ onChanged }: { onChanged?: () => void }) {
  const [sheets, setSheets] = useState<PriceSheetSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);

  function load() {
    setLoading(true);
    fetchMySheets()
      .then((data) => {
        setSheets(data);
        setError(null);
      })
      .catch((err) => setError(errorText(err, "Could not load price sheets.")))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  if (openId !== null) {
    return (
      <SheetDetail
        id={openId}
        onBack={() => {
          setOpenId(null);
          load();
        }}
        onChanged={onChanged}
      />
    );
  }

  if (loading) {
    return (
      <div className={`${card} overflow-hidden`}>
        <SkeletonTable rows={5} columns={4} />
      </div>
    );
  }
  if (error) {
    return <div className="rounded-2xl bg-tomato-500/10 border border-tomato-500/25 p-6 text-tomato-600 text-sm">{error}</div>;
  }
  if (sheets.length === 0) {
    return (
      <EmptyState
        icon={<IconShield width={20} height={20} />}
        title="No price sheets yet"
        description="When SPAR adjusts any of your prices, they'll send them here for you to approve and sign."
      />
    );
  }

  const pending = sheets.filter((s) => s.status === "PENDING");
  const others = sheets.filter((s) => s.status !== "PENDING");

  return (
    <div className="space-y-5">
      {pending.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60">Waiting for your signature</h3>
          {pending.map((s) => (
            <button
              key={s.id}
              onClick={() => setOpenId(s.id)}
              className={`${card} w-full text-left p-5 flex flex-wrap items-center gap-4 border-mango-500/40 hover:border-mango-500 transition-colors`}
            >
              <div className="flex-1 min-w-[12rem]">
                <p className="font-semibold text-crate-950">
                  {s.item_count} adjusted price{s.item_count === 1 ? "" : "s"} for delivery on {formatLongDate(s.delivery_date)}
                </p>
                <p className="text-xs text-crate-800/50 mt-1">
                  Sent {formatDateTime(s.sent_at)} · respond by {formatSignDeadline(s.delivery_date)}, or your own prices apply
                </p>
              </div>
              <span className="text-sm font-semibold text-crate-700">Review &amp; sign →</span>
            </button>
          ))}
        </div>
      )}

      {others.length > 0 && (
        <div className={`${card} p-5`}>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">History</h3>
          <ul className="divide-y divide-sage-100">
            {others.map((s) => (
              <li key={s.id}>
                <button
                  onClick={() => setOpenId(s.id)}
                  className="w-full text-left py-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 hover:bg-sage-50/60 transition-colors"
                >
                  <span className="flex-1 min-w-[12rem]">
                    <span className="block text-sm text-crate-950">Delivery {formatLongDate(s.delivery_date)}</span>
                    <span className="block text-xs text-crate-800/50 mt-0.5">
                      {s.item_count} item{s.item_count === 1 ? "" : "s"} · sent {formatDateTime(s.sent_at)}
                      {s.responded_at ? ` · responded ${formatDateTime(s.responded_at)}` : ""}
                    </span>
                  </span>
                  <SheetStatusBadge status={s.status} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function SheetDetail({ id, onBack, onChanged }: { id: number; onBack: () => void; onChanged?: () => void }) {
  const [sheet, setSheet] = useState<PriceSheet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"view" | "sign" | "reject">("view");

  useEffect(() => {
    fetchMySheet(id)
      .then(setSheet)
      .catch((err) => setError(errorText(err, "Could not load this price sheet.")));
  }, [id]);

  function done(updated: PriceSheet) {
    setSheet(updated);
    setMode("view");
    onChanged?.();
  }

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="no-print text-sm font-semibold text-crate-700 hover:underline">
        ← All price sheets
      </button>

      {error && <div className="rounded-2xl bg-tomato-500/10 border border-tomato-500/25 p-6 text-tomato-600 text-sm">{error}</div>}
      {!sheet && !error && (
        <div className={`${card} overflow-hidden`}>
          <SkeletonTable rows={5} columns={5} />
        </div>
      )}

      {sheet && (
        <>
          <div className={`${card} p-5 sm:p-6 space-y-4`}>
            <div className="no-print flex flex-wrap items-center gap-3 justify-between">
              <SheetStatusBadge status={sheet.status} />
              {sheet.status === "APPROVED" && (
                <Button variant="secondary" size="sm" onClick={() => window.print()}>
                  Print / Save as PDF
                </Button>
              )}
            </div>
            <PriceSheetDocument sheet={sheet} priceLabel="Your price" />
            <StatusNote sheet={sheet} />
          </div>

          {sheet.status === "PENDING" && mode === "view" && (
            <div className="no-print flex flex-wrap gap-3">
              <Button onClick={() => setMode("sign")}>Approve &amp; sign</Button>
              <Button variant="danger" onClick={() => setMode("reject")}>
                Reject
              </Button>
            </div>
          )}
          {sheet.status === "PENDING" && mode === "sign" && (
            <SignForm sheet={sheet} onCancel={() => setMode("view")} onDone={done} />
          )}
          {sheet.status === "PENDING" && mode === "reject" && (
            <RejectForm sheet={sheet} onCancel={() => setMode("view")} onDone={done} />
          )}
        </>
      )}
    </div>
  );
}

function StatusNote({ sheet }: { sheet: PriceSheet }) {
  const note =
    sheet.status === "PENDING"
      ? `Please approve or reject by ${formatSignDeadline(sheet.delivery_date)}. If you don't respond by then, your own submitted prices apply.`
      : sheet.status === "REJECTED"
      ? `You rejected these prices${sheet.responded_at ? ` on ${formatDateTime(sheet.responded_at)}` : ""}: "${sheet.rejection_reason}". SPAR will review and may send a new sheet.`
      : sheet.status === "EXPIRED"
      ? "This sheet expired without a response, so your own submitted prices applied."
      : sheet.status === "VOIDED" || sheet.status === "WITHDRAWN"
      ? `This sheet was cancelled by SPAR${sheet.closed_reason ? ` — ${sheet.closed_reason}` : "."} Nothing on it applies.`
      : null;
  if (!note) return null;
  return <p className="no-print text-sm text-crate-800/70 bg-sage-50 rounded-xl px-4 py-3">{note}</p>;
}

function SignForm({ sheet, onCancel, onDone }: { sheet: PriceSheet; onCancel: () => void; onDone: (s: PriceSheet) => void }) {
  const padRef = useRef<SignaturePadHandle>(null);
  const [agreed, setAgreed] = useState(false);
  const [hasInk, setHasInk] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ready = agreed && hasInk;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const image = padRef.current?.toDataURL();
    if (!ready || !image) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await approveSheet(sheet.id, {
        snapshot_hash: sheet.snapshot_hash,
        signature_image: image,
        agreed: true,
      });
      onDone(updated);
    } catch (err) {
      setError(errorText(err, "Could not record your signature. Please try again."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className={`no-print ${card} p-5 sm:p-6 space-y-5`}>
      <div>
        <h3 className="font-display font-semibold text-crate-950">Approve and sign</h3>
        <p className="text-sm text-crate-800/60 mt-1">
          Your signature and the exact prices above are saved together as a record of this agreement.
        </p>
      </div>

      <label className="flex gap-3 items-start text-sm text-crate-950 cursor-pointer">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(e) => setAgreed(e.target.checked)}
          className="mt-0.5 h-4 w-4 accent-crate-700"
        />
        <span>
          I agree, on behalf of <strong>{sheet.supplier_name}</strong>, to supply the {sheet.items.length} item
          {sheet.items.length === 1 ? "" : "s"} above at the SPAR prices shown for delivery on{" "}
          <strong>{formatLongDate(sheet.delivery_date)}</strong>.
        </span>
      </label>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="block text-xs font-semibold text-crate-800/50 uppercase tracking-wide">Signature</span>
          <button type="button" onClick={() => padRef.current?.clear()} className="text-xs text-crate-700 hover:underline">
            Clear
          </button>
        </div>
        <SignaturePad ref={padRef} onChange={setHasInk} />
      </div>

      {error && <p className="text-sm text-tomato-600">{error}</p>}

      <div className="flex flex-wrap gap-3">
        <Button type="submit" disabled={!ready} loading={submitting}>
          Sign and approve
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function RejectForm({ sheet, onCancel, onDone }: { sheet: PriceSheet; onCancel: () => void; onDone: (s: PriceSheet) => void }) {
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready = reason.trim().length >= 3;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!ready) return;
    setSubmitting(true);
    setError(null);
    try {
      onDone(await rejectSheet(sheet.id, { snapshot_hash: sheet.snapshot_hash, reason: reason.trim() }));
    } catch (err) {
      setError(errorText(err, "Could not send your response. Please try again."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className={`no-print ${card} p-5 sm:p-6 space-y-4`}>
      <div>
        <h3 className="font-display font-semibold text-crate-950">Reject these prices</h3>
        <p className="text-sm text-crate-800/60 mt-1">Tell SPAR why, e.g. which items you can't supply at their price.</p>
      </div>
      <textarea
        className={`${input} min-h-[6rem]`}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        maxLength={1000}
        placeholder="Reason"
      />
      {error && <p className="text-sm text-tomato-600">{error}</p>}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" variant="danger" disabled={!ready} loading={submitting}>
          Reject prices
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
