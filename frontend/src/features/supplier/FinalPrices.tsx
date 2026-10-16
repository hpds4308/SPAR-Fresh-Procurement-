import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import {
  FinalDates,
  FinalPriceList,
  downloadMyFinalPrices,
  fetchMyFinalDates,
  fetchMyFinalPrices,
} from "../../api/finalPrices";
import EmptyState from "../shared/EmptyState";
import { SkeletonTable } from "../shared/ui/Skeleton";
import { IconReceipt } from "../shared/Icons";
import { formatDateTime, formatSignDeadline, formatSubmissionDate, rs, submissionDateIso } from "../shared/PriceSheetParts";
import { ProductPromotion } from "../shared/ui/PromotionBadge";

const CARD = "bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100";

/**
 * The supplier's final (agreed) prices per delivery date. A date appears
 * once SPAR's approval cutoff (2:00 PM on the submission day) has passed —
 * by then every adjustment is settled. Downloads carry SPAR's signature.
 */
export default function FinalPrices() {
  const [dates, setDates] = useState<FinalDates | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [list, setList] = useState<FinalPriceList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<"excel" | "pdf" | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  useEffect(() => {
    fetchMyFinalDates()
      .then((d) => {
        setDates(d);
        setSelected(d.dates[0] ?? null);
        if (d.dates.length === 0) setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Could not load your final prices.");
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDownloadError(null);
    fetchMyFinalPrices(selected)
      .then((l) => !cancelled && setList(l))
      .catch((err) => !cancelled && setError(err instanceof ApiError ? err.message : "Could not load your final prices."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [selected]);

  async function download(format: "excel" | "pdf") {
    if (!list) return;
    setDownloading(format);
    setDownloadError(null);
    try {
      await downloadMyFinalPrices(list.delivery_date, list.supplier_name, format, submissionDateIso(list.delivery_date));
    } catch (err) {
      setDownloadError(err instanceof ApiError ? err.message : "Could not download the price list.");
    } finally {
      setDownloading(null);
    }
  }

  const upcoming =
    dates?.next_delivery_date && dates.next_final_at ? (
      <p className="text-xs text-crate-800/50">
        Your prices for {formatSubmissionDate(dates.next_delivery_date)} become final at{" "}
        {formatSignDeadline(dates.next_final_at)}.
      </p>
    ) : null;

  if (dates && dates.dates.length === 0) {
    return (
      <EmptyState
        icon={<IconReceipt width={20} height={20} />}
        title="No final prices yet"
        description={`Your final prices show here after ${dates.cutoff_label} on the price submission day, once SPAR's adjustments are settled.`}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className={`${CARD} p-5 flex flex-wrap items-end gap-4`}>
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-1.5">
            Date
          </label>
          <select
            value={selected ?? ""}
            onChange={(e) => setSelected(e.target.value)}
            className="border border-sage-300 rounded-full px-4 py-2 text-sm bg-sage-50/60 focus:outline-none focus:ring-2 focus:ring-crate-700/30"
          >
            {dates?.dates.map((d) => (
              <option key={d} value={d}>
                {formatSubmissionDate(d)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-wrap gap-2 ml-auto">
          <button
            onClick={() => download("excel")}
            disabled={!list || !dates?.signature_ready || downloading !== null}
            className="text-sm bg-crate-700 text-white rounded-full px-4 py-2 font-semibold hover:bg-crate-800 disabled:opacity-50"
          >
            {downloading === "excel" ? "Preparing…" : "Download Excel"}
          </button>
          <button
            onClick={() => download("pdf")}
            disabled={!list || !dates?.signature_ready || downloading !== null}
            className="text-sm bg-white text-crate-800 border border-crate-700/40 rounded-full px-4 py-2 font-semibold hover:bg-sage-50 disabled:opacity-50"
          >
            {downloading === "pdf" ? "Preparing…" : "Download PDF"}
          </button>
        </div>
        <div className="basis-full space-y-1">
          {dates && !dates.signature_ready && (
            <p className="text-xs text-[#8A5A0D]">
              SPAR hasn't added its signature to final price lists yet — downloads will be available once it has.
            </p>
          )}
          {downloadError && <p className="text-xs text-tomato-600">{downloadError}</p>}
          {upcoming}
        </div>
      </div>

      {error && (
        <div className="rounded-2xl bg-tomato-500/10 border border-tomato-500/25 p-6 text-tomato-600 text-sm">{error}</div>
      )}
      {loading && (
        <div className={`${CARD} overflow-hidden`}>
          <SkeletonTable rows={6} columns={5} />
        </div>
      )}

      {!loading && !error && list && (
        <div className={`${CARD} p-6`}>
          <div className="flex flex-wrap items-baseline justify-between gap-2 mb-4">
            <div>
              <h2 className="font-display font-semibold text-lg text-crate-950">
                Final prices — Date: {formatSubmissionDate(list.delivery_date)}
              </h2>
              <p className="text-xs text-crate-800/50">
                Final since {formatSignDeadline(list.finalized_at)} · Reference {list.reference}
              </p>
            </div>
          </div>

          <div className="overflow-x-auto -mx-2 px-2">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-crate-800/40 text-left text-xs uppercase tracking-wide">
                  <th className="pb-2 font-medium">Product</th>
                  <th className="pb-2 font-medium text-right">Your Price</th>
                  <th className="pb-2 font-medium text-right">SPAR Adjusted</th>
                  <th className="pb-2 font-medium text-right">Final Price</th>
                  <th className="pb-2 font-medium pl-4">Basis</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-sage-100">
                {list.lines.map((l) => (
                  <tr key={l.product_id}>
                    <td className="py-2 text-crate-950">
                      {l.product_description}
                      <ProductPromotion productId={l.product_id} className="ml-1.5" />
                      <span className="block text-[11px] text-crate-800/40">
                        {l.product_code} · {l.unit_code}
                      </span>
                    </td>
                    <td className="py-2 text-right text-crate-800/70 whitespace-nowrap">{rs(l.your_price)}</td>
                    <td className="py-2 text-right text-crate-800/70 whitespace-nowrap">
                      {l.adjusted_price !== null ? rs(l.adjusted_price) : <span className="text-crate-800/25">—</span>}
                    </td>
                    <td className="py-2 text-right font-semibold text-crate-950 whitespace-nowrap">{rs(l.final_price)}</td>
                    <td className="py-2 pl-4 text-xs text-crate-800/60">{l.basis}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid sm:grid-cols-2 gap-4 mt-6">
            <SignatureBox
              heading="Authorised for SPAR"
              image={list.spar_signature.signature_image}
              lines={[list.spar_signature.signatory_name, list.spar_signature.signatory_title]}
              empty="SPAR's signature hasn't been added yet."
            />
            {list.supplier_signatures.length > 0 ? (
              (() => {
                const s = list.supplier_signatures[list.supplier_signatures.length - 1];
                return (
                  <SignatureBox
                    heading={`Accepted by ${list.supplier_name}`}
                    image={s.signature_image}
                    lines={[
                      s.signer_name,
                      `Price sheet #${s.price_sheet_id}${s.signed_at ? ` · ${formatDateTime(s.signed_at)}` : ""}`,
                    ]}
                  />
                );
              })()
            ) : (
              <SignatureBox
                heading="Supplier"
                image={null}
                lines={[]}
                empty="No SPAR adjustment was approved for this date, so no supplier signature was needed."
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function SignatureBox({
  heading,
  image,
  lines,
  empty,
}: {
  heading: string;
  image: string | null;
  lines: (string | null)[];
  empty?: string;
}) {
  return (
    <div className="rounded-xl border border-crate-700/20 bg-sage-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-crate-800/50 mb-3">{heading}</p>
      {image ? (
        <div className="bg-white border border-sage-200 rounded-lg p-2 inline-block">
          <img src={image} alt={`Signature — ${heading}`} className="h-16 w-auto" />
        </div>
      ) : (
        <p className="text-sm text-crate-800/50">{empty}</p>
      )}
      {lines.filter(Boolean).map((t, i) => (
        <p key={i} className={i === 0 ? "text-sm font-medium text-crate-950 mt-2" : "text-xs text-crate-800/50"}>
          {t}
        </p>
      ))}
    </div>
  );
}
