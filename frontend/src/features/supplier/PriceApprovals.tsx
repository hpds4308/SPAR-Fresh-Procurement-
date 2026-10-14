import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import {
  ItemDecision,
  PriceSheet,
  PriceSheetItem,
  PriceSheetSummary,
  fetchMySheet,
  fetchMySheets,
  respondToSheet,
} from "../../api/priceApprovals";
import EmptyState from "../shared/EmptyState";
import { IconShield } from "../shared/Icons";
import {
  PriceSheetDocument,
  SheetStatusBadge,
  formatDateTime,
  formatLongDate,
  formatSignDeadline,
  FinalOfferTag,
  rs,
} from "../shared/PriceSheetParts";
import { ProductPromotion } from "../shared/ui/PromotionBadge";
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
        description="When SPAR adjusts any of your prices, they'll send them here for you to approve or reject, item by item."
      />
    );
  }

  const pending = sheets.filter((s) => s.status === "PENDING");
  const others = sheets.filter((s) => s.status !== "PENDING");

  return (
    <div className="space-y-5">
      {pending.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60">Waiting for your response</h3>
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
              <span className="text-sm font-semibold text-crate-700">Review &amp; respond →</span>
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

  useEffect(() => {
    fetchMySheet(id)
      .then(setSheet)
      .catch((err) => setError(errorText(err, "Could not load this price sheet.")));
  }, [id]);

  function done(updated: PriceSheet) {
    setSheet(updated);
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

      {sheet && sheet.status === "PENDING" && <ResponseForm sheet={sheet} onDone={done} />}

      {sheet && sheet.status !== "PENDING" && (
        <div className={`${card} p-5 sm:p-6 space-y-4`}>
          <div className="no-print flex flex-wrap items-center gap-3 justify-between">
            <SheetStatusBadge status={sheet.status} />
            {(sheet.status === "APPROVED" || sheet.status === "PARTIAL") && (
              <Button variant="secondary" size="sm" onClick={() => window.print()}>
                Print / Save as PDF
              </Button>
            )}
          </div>
          <PriceSheetDocument sheet={sheet} priceLabel="Your price" />
          <StatusNote sheet={sheet} />
        </div>
      )}
    </div>
  );
}

function StatusNote({ sheet }: { sheet: PriceSheet }) {
  const note =
    sheet.status === "PARTIAL"
      ? `You approved ${sheet.approved_count} item${sheet.approved_count === 1 ? "" : "s"} and rejected ${sheet.rejected_count}${
          sheet.responded_at ? ` on ${formatDateTime(sheet.responded_at)}` : ""
        }. For a rejected item, the new price you gave applies (or your own submitted price if you didn't give one). SPAR may send a new sheet for those items.`
      : sheet.status === "REJECTED"
      ? `You rejected these prices${sheet.responded_at ? ` on ${formatDateTime(sheet.responded_at)}` : ""}. The new prices you gave apply (or your own submitted prices). SPAR will review and may send a new sheet.`
      : sheet.status === "EXPIRED"
      ? "This sheet expired without a response, so your own submitted prices applied."
      : sheet.status === "VOIDED" || sheet.status === "WITHDRAWN"
      ? `This sheet was cancelled by SPAR${sheet.closed_reason ? ` — ${sheet.closed_reason}` : "."} Nothing on it applies.`
      : null;
  if (!note) return null;
  return <p className="no-print text-sm text-crate-800/70 bg-sage-50 rounded-xl px-4 py-3">{note}</p>;
}

type Answer = { decision: ItemDecision | null; counter: string };

function parsePrice(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const n = Number(trimmed);
  return Number.isFinite(n) && n > 0 && n < 10_000_000 ? Math.round(n * 100) / 100 : NaN;
}

/**
 * The supplier answers each item: approve SPAR's price, or reject it and
 * (optionally) give their own final price. Approving anything needs the
 * agreement tick and a drawn signature.
 */
function ResponseForm({ sheet, onDone }: { sheet: PriceSheet; onDone: (s: PriceSheet) => void }) {
  const padRef = useRef<SignaturePadHandle>(null);
  const [answers, setAnswers] = useState<Record<number, Answer>>({});
  const [note, setNote] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [hasInk, setHasInk] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const answerOf = (spid: number): Answer => answers[spid] ?? { decision: null, counter: "" };
  const approved = sheet.items.filter((i) => answerOf(i.supplier_price_id).decision === "APPROVED");
  const rejected = sheet.items.filter((i) => answerOf(i.supplier_price_id).decision === "REJECTED");
  const unanswered = sheet.items.length - approved.length - rejected.length;

  function counterProblem(item: PriceSheetItem): string | null {
    const a = answerOf(item.supplier_price_id);
    if (a.decision !== "REJECTED" || item.final_offer) return null;
    const value = parsePrice(a.counter);
    if (value === null) return null;
    if (Number.isNaN(value)) return "Enter a valid price";
    if (value === Math.round(item.adjusted_price * 100) / 100) return "Same as SPAR's price — approve instead";
    return null;
  }
  const hasCounterProblem = sheet.items.some((i) => counterProblem(i) !== null);
  const ready = unanswered === 0 && !hasCounterProblem && (approved.length === 0 || (agreed && hasInk));

  function setDecision(spid: number, decision: ItemDecision) {
    setAnswers((prev) => ({ ...prev, [spid]: { counter: prev[spid]?.counter ?? "", decision } }));
  }

  function setAll(decision: ItemDecision) {
    setAnswers((prev) => {
      const next: Record<number, Answer> = {};
      for (const item of sheet.items) {
        next[item.supplier_price_id] = { counter: prev[item.supplier_price_id]?.counter ?? "", decision };
      }
      return next;
    });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!ready) return;
    const image = approved.length > 0 ? padRef.current?.toDataURL() : null;
    if (approved.length > 0 && !image) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await respondToSheet(sheet.id, {
        snapshot_hash: sheet.snapshot_hash,
        items: sheet.items.map((item) => {
          const a = answerOf(item.supplier_price_id);
          return {
            supplier_price_id: item.supplier_price_id,
            decision: a.decision!,
            counter_price: a.decision === "REJECTED" && !item.final_offer ? parsePrice(a.counter) : null,
          };
        }),
        note: rejected.length > 0 ? note.trim() || null : null,
        agreed: approved.length > 0 && agreed,
        signature_image: image,
      });
      onDone(updated);
    } catch (err) {
      setError(errorText(err, "Could not send your response. Please try again."));
    } finally {
      setSubmitting(false);
    }
  }

  const toggle = (active: boolean, tone: "approve" | "reject") =>
    `rounded-full px-3 py-1.5 text-xs font-semibold border transition-colors duration-150 ${
      active
        ? tone === "approve"
          ? "bg-crate-700 border-crate-700 text-white"
          : "bg-tomato-600 border-tomato-600 text-white"
        : tone === "approve"
        ? "bg-white border-sage-300 text-crate-700 hover:border-crate-700"
        : "bg-white border-sage-300 text-tomato-600 hover:border-tomato-500"
    }`;

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className={`${card} p-5 sm:p-6 space-y-4`}>
        <div className="flex flex-wrap items-start gap-3 justify-between">
          <div>
            <p className="text-xs uppercase tracking-wide text-crate-800/40 font-semibold">SPAR price sheet #{sheet.id}</p>
            <h3 className="font-display text-lg font-semibold text-crate-950 mt-0.5">{sheet.supplier_name}</h3>
            <p className="text-sm text-crate-800/60 mt-1">
              Delivery on {formatLongDate(sheet.delivery_date)} · sent {formatDateTime(sheet.sent_at)}
              {sheet.sent_by_name ? ` by ${sheet.sent_by_name}` : ""}
            </p>
          </div>
          <SheetStatusBadge status={sheet.status} />
        </div>

        <p className="text-sm text-crate-800/70 bg-sage-50 rounded-xl px-4 py-3">
          Approve or reject each price. If you reject one, you can enter your own final price for it. Please respond
          by {formatSignDeadline(sheet.delivery_date)}, or your own submitted prices apply.
          {sheet.items.some((i) => i.final_offer) && (
            <>
              {" "}
              Items marked <strong>Final price</strong> are SPAR's last offer after your earlier rejection: approve or
              reject only.
            </>
          )}
        </p>

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-crate-800/50 mr-1">All items:</span>
          <button type="button" onClick={() => setAll("APPROVED")} className={toggle(false, "approve")}>
            ✓ Approve all
          </button>
          <button type="button" onClick={() => setAll("REJECTED")} className={toggle(false, "reject")}>
            ✗ Reject all
          </button>
        </div>

        <ul className="divide-y divide-sage-100 border-y border-sage-100">
          {sheet.items.map((item) => {
            const a = answerOf(item.supplier_price_id);
            const problem = counterProblem(item);
            return (
              <li
                key={item.supplier_price_id}
                className={`py-3 flex flex-wrap items-center gap-x-4 gap-y-2 ${
                  a.decision === "REJECTED" ? "bg-tomato-500/[0.03]" : a.decision === "APPROVED" ? "bg-crate-700/[0.03]" : ""
                }`}
              >
                <div className="flex-1 min-w-[13rem]">
                  <p className="text-sm text-crate-950">
                    {item.product_description}
                    <span className="text-crate-800/35 text-xs ml-1.5">{item.product_code}</span>
                    <ProductPromotion productId={item.product_id} className="ml-1.5" />
                    {item.final_offer && <FinalOfferTag className="ml-1.5" />}
                  </p>
                  <p className="text-sm mt-0.5 flex flex-wrap gap-x-3">
                    <span className="text-crate-800/60">
                      Your price: <span className="tabular-nums">{rs(item.supplier_price)}</span>
                    </span>
                    {item.final_offer && item.previous_price !== null && (
                      <span className="text-crate-800/60">
                        Your last offer: <span className="tabular-nums">{rs(item.previous_price)}</span>
                      </span>
                    )}
                    <span className="text-crate-800/60">
                      SPAR: <span className="font-semibold text-crate-950 tabular-nums">{rs(item.adjusted_price)}</span>
                      <span className="text-crate-800/40"> /{item.unit_code}</span>
                    </span>
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    aria-pressed={a.decision === "APPROVED"}
                    onClick={() => setDecision(item.supplier_price_id, "APPROVED")}
                    className={toggle(a.decision === "APPROVED", "approve")}
                  >
                    ✓ Approve
                  </button>
                  <button
                    type="button"
                    aria-pressed={a.decision === "REJECTED"}
                    onClick={() => setDecision(item.supplier_price_id, "REJECTED")}
                    className={toggle(a.decision === "REJECTED", "reject")}
                  >
                    ✗ Reject
                  </button>
                </div>
                {a.decision === "REJECTED" && item.final_offer && (
                  <p className="basis-full text-xs text-crate-800/60">
                    This is SPAR's final price, so there's no new price this time. If you reject it,{" "}
                    {item.previous_price !== null
                      ? `your last offer of ${rs(item.previous_price)} applies.`
                      : `your own price of ${rs(item.supplier_price)} applies.`}
                  </p>
                )}
                {a.decision === "REJECTED" && !item.final_offer && (
                  <div className="basis-full">
                    <label className="flex flex-wrap items-center gap-2 text-sm text-crate-800/80">
                      <span>Your new final price (Rs.)</span>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        inputMode="decimal"
                        value={a.counter}
                        onChange={(e) =>
                          setAnswers((prev) => ({
                            ...prev,
                            [item.supplier_price_id]: { decision: "REJECTED", counter: e.target.value },
                          }))
                        }
                        placeholder={item.supplier_price.toFixed(2)}
                        className={`w-28 border rounded-lg px-2 py-1 text-right text-sm bg-white focus:outline-none focus:ring-2 focus:ring-crate-700/30 ${
                          problem ? "border-tomato-500" : "border-sage-300"
                        }`}
                      />
                      <span className="text-xs text-crate-800/45">
                        {problem ?? `/${item.unit_code} · leave blank to keep your price ${rs(item.supplier_price)}`}
                      </span>
                    </label>
                  </div>
                )}
              </li>
            );
          })}
        </ul>

        <p className="text-xs text-crate-800/50">
          {approved.length} approved · {rejected.length} rejected
          {unanswered > 0 ? ` · ${unanswered} still to answer` : ""}
        </p>
      </div>

      {rejected.length > 0 && (
        <div className={`${card} p-5 sm:p-6 space-y-2`}>
          <label className="block text-xs font-semibold text-crate-800/50 uppercase tracking-wide">
            Note to SPAR (optional)
          </label>
          <textarea
            className={`${input} min-h-[4.5rem]`}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={1000}
            placeholder="e.g. why you can't supply at SPAR's price"
          />
        </div>
      )}

      {approved.length > 0 && (
        <div className={`${card} p-5 sm:p-6 space-y-5`}>
          <div>
            <h3 className="font-display font-semibold text-crate-950">Sign for the approved prices</h3>
            <p className="text-sm text-crate-800/60 mt-1">
              Your signature and the exact prices are saved together as a record of this agreement.
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
              I agree, on behalf of <strong>{sheet.supplier_name}</strong>, to supply the {approved.length} approved item
              {approved.length === 1 ? "" : "s"} at the SPAR prices shown for delivery on{" "}
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
        </div>
      )}

      {error && <p className="text-sm text-tomato-600">{error}</p>}

      <div className="no-print flex flex-wrap items-center gap-3">
        <Button type="submit" variant={approved.length === 0 && rejected.length > 0 ? "danger" : "primary"} disabled={!ready} loading={submitting}>
          {approved.length > 0 ? "Sign and send response" : rejected.length > 0 ? "Send rejection" : "Send response"}
        </Button>
        {!ready && (
          <span className="text-xs text-crate-800/50">
            {unanswered > 0
              ? "Approve or reject every item first."
              : hasCounterProblem
              ? "Fix the new prices marked in red."
              : "Tick the box and sign to approve."}
          </span>
        )}
      </div>
    </form>
  );
}
