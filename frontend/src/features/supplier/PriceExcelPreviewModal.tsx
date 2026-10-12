import { ExcelPricePreview } from "../../api/pricing";

// Shows what an uploaded price Excel will submit before anything is saved.
// Rows with an error are listed but never sent.
export default function PriceExcelPreviewModal({
  fileName,
  preview,
  deliveryDateLabel,
  submitting,
  error,
  onSubmit,
  onLoadIntoForm,
  onClose,
}: {
  fileName: string;
  preview: ExcelPricePreview;
  deliveryDateLabel: string | null;
  submitting: boolean;
  error: string | null;
  onSubmit: () => void;
  onLoadIntoForm: () => void;
  onClose: () => void;
}) {
  const valid = preview.valid_line_count;
  return (
    <div
      className="fixed inset-0 bg-crate-950/40 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={() => !submitting && onClose()}
    >
      <div
        className="bg-white rounded-[1.75rem] shadow-[0_30px_60px_-15px_rgba(21,56,38,0.35)] w-full max-w-2xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-6 border-b border-sage-100">
          <h3 className="text-lg font-semibold text-crate-950">Review uploaded prices</h3>
          <p className="text-xs text-crate-800/50 mt-0.5 truncate">{fileName}</p>
          <div className="flex flex-wrap gap-2 mt-3 text-xs">
            <span className="rounded-full bg-crate-700/10 text-crate-800 px-3 py-1 font-medium">
              {valid} price{valid === 1 ? "" : "s"} ready
            </span>
            {preview.error_count > 0 && (
              <span className="rounded-full bg-tomato-600/10 text-tomato-600 px-3 py-1 font-medium">
                {preview.error_count} row{preview.error_count === 1 ? "" : "s"} with problems (skipped)
              </span>
            )}
            {preview.blank_price_count > 0 && (
              <span className="rounded-full bg-sage-100 text-crate-800/60 px-3 py-1">
                {preview.blank_price_count} product{preview.blank_price_count === 1 ? "" : "s"} left blank
              </span>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {preview.lines.length === 0 ? (
            <p className="p-6 text-sm text-crate-800/50 text-center">
              No prices were found in this file. Fill in the Price column of the template and upload it again.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-sage-50 text-xs text-crate-800/60">
                <tr>
                  <th className="text-left font-medium px-4 py-2 w-12">Row</th>
                  <th className="text-left font-medium px-4 py-2">Product</th>
                  <th className="text-right font-medium px-4 py-2">Price</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-sage-100">
                {preview.lines.map((l) => (
                  <tr key={l.row_number} className={l.error ? "bg-tomato-600/5" : ""}>
                    <td className="px-4 py-2 text-crate-800/40 align-top">{l.row_number}</td>
                    <td className="px-4 py-2 align-top">
                      <p className="text-crate-950">{l.description ?? "—"}</p>
                      <p className="text-xs text-crate-800/40">{l.product_code}</p>
                      {l.error && <p className="text-xs text-tomato-600 mt-0.5">{l.error}</p>}
                    </td>
                    <td className="px-4 py-2 text-right align-top whitespace-nowrap">
                      {l.price !== null ? (
                        <span className={l.error ? "text-crate-800/40 line-through" : "text-crate-950"}>
                          Rs. {l.price.toFixed(2)}
                          {l.unit_code && <span className="text-xs text-crate-800/40"> /{l.unit_code}</span>}
                        </span>
                      ) : (
                        <span className="text-crate-800/30">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="p-6 border-t border-sage-100">
          {valid > 0 && (
            <p className="text-xs text-crate-800/60 mb-3">
              Submitting replaces your price list
              {deliveryDateLabel ? ` for delivery on ${deliveryDateLabel}` : ""} — any product without a price in
              this file will be removed from it.
            </p>
          )}
          <div className="flex flex-wrap items-center justify-end gap-3">
            {error && <p className="text-tomato-600 text-sm mr-auto">{error}</p>}
            <button
              onClick={onClose}
              disabled={submitting}
              className="border border-sage-300 text-crate-800/70 rounded-full px-4 py-2.5 text-sm font-medium hover:bg-sage-50 active:scale-[0.98] disabled:opacity-40 transition-all duration-150"
            >
              Cancel
            </button>
            <button
              onClick={onLoadIntoForm}
              disabled={submitting || valid === 0}
              title="Put these prices into the form so you can check or edit them before submitting."
              className="border border-sage-300 text-crate-800 rounded-full px-4 py-2.5 text-sm font-medium hover:bg-sage-50 active:scale-[0.98] disabled:opacity-40 transition-all duration-150"
            >
              Edit in form first
            </button>
            <button
              onClick={onSubmit}
              disabled={submitting || valid === 0}
              className="bg-gradient-to-b from-crate-700 to-crate-800 text-white rounded-full px-5 py-2.5 text-sm font-semibold hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100 shadow-md shadow-crate-800/20 transition-all duration-150"
            >
              {submitting ? "Submitting…" : `Submit ${valid} price${valid === 1 ? "" : "s"}`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
