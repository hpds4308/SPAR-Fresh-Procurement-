import { KeellsExcelPreview } from "../../api/pricing";

// Shows what an uploaded Keells price file will import before anything is
// saved. All or nothing: a single row with a problem blocks the import.
export default function KeellsExcelPreviewModal({
  fileName,
  preview,
  dateLabel,
  importing,
  error,
  onImport,
  onClose,
}: {
  fileName: string;
  preview: KeellsExcelPreview;
  dateLabel: string;
  importing: boolean;
  error: string | null;
  onImport: () => void;
  onClose: () => void;
}) {
  const valid = preview.valid_count;
  const blocked = preview.error_count > 0 || valid === 0;
  // Problem rows first, so they're not missed in a 60-row list.
  const lines = [...preview.lines].sort((a, b) => Number(!a.error) - Number(!b.error) || a.row_number - b.row_number);
  return (
    <div
      className="fixed inset-0 bg-crate-950/40 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={() => !importing && onClose()}
    >
      <div
        className="bg-white rounded-[1.75rem] shadow-[0_30px_60px_-15px_rgba(21,56,38,0.35)] w-full max-w-2xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-6 border-b border-sage-100">
          <h3 className="text-lg font-semibold text-crate-950">Review Keells prices</h3>
          <p className="text-xs text-crate-800/50 mt-0.5 truncate">{fileName}</p>
          <p className="text-sm text-crate-800 mt-2">
            Price date: <span className="font-semibold">{dateLabel}</span>
          </p>
          <div className="flex flex-wrap gap-2 mt-3 text-xs">
            <span className="rounded-full bg-crate-700/10 text-crate-800 px-3 py-1 font-medium">
              {valid} price{valid === 1 ? "" : "s"} OK
            </span>
            {preview.error_count > 0 && (
              <span className="rounded-full bg-tomato-600/10 text-tomato-600 px-3 py-1 font-medium">
                {preview.error_count} row{preview.error_count === 1 ? "" : "s"} with problems
              </span>
            )}
            {preview.not_in_file.length > 0 && (
              <span
                className="rounded-full bg-mango-500/20 text-[#8A5A0D] px-3 py-1"
                title={preview.not_in_file.map((m) => m.system_name).join(", ")}
              >
                {preview.not_in_file.length} Keells product{preview.not_in_file.length === 1 ? "" : "s"} not in this file
              </span>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {lines.length === 0 ? (
            <p className="p-6 text-sm text-center text-tomato-600">This file has no price rows.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-sage-50 text-xs text-crate-800/60">
                <tr>
                  <th className="text-left font-medium px-4 py-2 w-12">Row</th>
                  <th className="text-left font-medium px-4 py-2">Product</th>
                  <th className="text-right font-medium px-4 py-2">Keells Price</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-sage-100">
                {lines.map((l) => (
                  <tr key={l.row_number} className={l.error ? "bg-tomato-600/5" : ""}>
                    <td className="px-4 py-2 text-crate-800/40 align-top">{l.row_number}</td>
                    <td className="px-4 py-2 align-top">
                      <p className="text-crate-950">{l.product_description ?? l.system_name ?? "—"}</p>
                      <p className="text-xs text-crate-800/40">
                        {l.dc_code || "no DC code"}
                        {l.keells_name ? ` · Keells: ${l.keells_name}` : ""}
                      </p>
                      {l.error && <p className="text-xs text-tomato-600 mt-0.5">{l.error}</p>}
                    </td>
                    <td className="px-4 py-2 text-right align-top whitespace-nowrap">
                      {l.price !== null ? (
                        <span className={l.error ? "text-crate-800/40" : "text-crate-950"}>
                          Rs. {l.price.toFixed(2)}
                          {l.unit && <span className="text-xs text-crate-800/40"> /{l.unit}</span>}
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
          <p className="text-xs text-crate-800/60 mb-3">
            {blocked
              ? "Nothing can be imported until every row is fixed. Correct the file and upload it again."
              : `Importing replaces every Keells price for ${dateLabel}` +
                (preview.existing_count > 0 ? ` (${preview.existing_count} saved now)` : "") +
                ". Other dates aren't changed."}
            {!blocked && preview.not_in_file.length > 0 && (
              <> Products not in this file will have no Keells price for this date.</>
            )}
          </p>
          <div className="flex flex-wrap items-center justify-end gap-3">
            {error && <p className="text-tomato-600 text-sm mr-auto">{error}</p>}
            <button
              onClick={onClose}
              disabled={importing}
              className="border border-sage-300 text-crate-800/70 rounded-full px-4 py-2.5 text-sm font-medium hover:bg-sage-50 active:scale-[0.98] disabled:opacity-40 transition-all duration-150"
            >
              Cancel
            </button>
            <button
              onClick={onImport}
              disabled={importing || blocked}
              className="bg-gradient-to-b from-crate-700 to-crate-800 text-white rounded-full px-5 py-2.5 text-sm font-semibold hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100 shadow-md shadow-crate-800/20 transition-all duration-150"
            >
              {importing ? "Importing…" : `Import ${valid} price${valid === 1 ? "" : "s"}`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
