import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { resolveProductPhoto, useProductImages } from "../useProductImages";

const SIZES = { sm: "w-8 h-8", md: "w-10 h-10", lg: "w-14 h-14" };

function usePhotoUrl(productId: number | null, size: "thumb" | "full") {
  const refs = useProductImages();
  const ref = productId !== null ? refs[productId] : undefined;
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    setUrl(null);
    let cancelled = false;
    resolveProductPhoto(ref, size).then((u) => !cancelled && setUrl(u));
    return () => {
      cancelled = true;
    };
  }, [ref, size]);
  return url;
}

/**
 * A product's photo as a small square thumbnail; click it to see it full
 * size. Renders nothing when the product has no photo (unless
 * `placeholder`, which keeps an empty square so a list stays aligned).
 * Drop it next to a product name on any page — all thumbnails share one
 * fetch of which products have photos.
 */
export function ProductThumb({
  productId,
  name,
  size = "sm",
  placeholder = false,
  className = "",
}: {
  productId: number | null;
  name?: string;
  size?: keyof typeof SIZES;
  placeholder?: boolean;
  className?: string;
}) {
  const url = usePhotoUrl(productId, "thumb");
  const [open, setOpen] = useState(false);

  if (!url) {
    if (!placeholder) return null;
    return (
      <span
        aria-hidden="true"
        className={`inline-block shrink-0 rounded-lg border border-dashed border-sage-300 bg-sage-50/60 ${SIZES[size]} ${className}`}
      />
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen(true);
        }}
        title={name ? `View photo of ${name}` : "View photo"}
        aria-label={name ? `View photo of ${name}` : "View photo"}
        className={`inline-block shrink-0 align-middle rounded-lg overflow-hidden border border-sage-200 bg-sage-50 hover:ring-2 hover:ring-crate-700/30 transition ${SIZES[size]} ${className}`}
      >
        <img src={url} alt="" className="w-full h-full object-cover" />
      </button>
      {open && <ProductPhotoViewer productId={productId} name={name} onClose={() => setOpen(false)} />}
    </>
  );
}

function ProductPhotoViewer({
  productId,
  name,
  onClose,
}: {
  productId: number | null;
  name?: string;
  onClose: () => void;
}) {
  const url = usePhotoUrl(productId, "full");
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-crate-950/60" aria-hidden="true" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={name ? `Photo of ${name}` : "Product photo"}
        className="relative bg-white rounded-2xl shadow-modal p-3 w-full max-w-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="aspect-square w-full rounded-xl overflow-hidden bg-sage-50 flex items-center justify-center">
          {url ? (
            <img src={url} alt={name ?? "Product photo"} className="w-full h-full object-contain" />
          ) : (
            <span className="text-sm text-crate-800/50">Loading photo…</span>
          )}
        </div>
        <div className="flex items-center justify-between gap-3 mt-3 px-1">
          <p className="text-sm font-medium text-crate-950 truncate">{name}</p>
          <button
            type="button"
            onClick={onClose}
            className="text-sm text-crate-700 hover:text-crate-950 px-3 py-1 rounded-full hover:bg-sage-50"
          >
            Close
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
