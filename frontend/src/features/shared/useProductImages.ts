import { useEffect, useState } from "react";
import { ProductImageRef, fetchProductImageRefs, productImageUrl } from "../../api/products";

// Every product's photo info (product_id -> code + uploaded-photo
// version), shared by every photo on the page so a screen full of
// products makes one request, not one per row. Same pattern as
// useActivePromotions: refetched when older than STALE_MS, or right away
// after Admin changes a photo. Photos are informational only, so a failed
// fetch just means no photos — it never blocks the page.
//
// A photo Admin uploaded always wins. Products without one fall back to
// the older photo files shipped with the site (/images/products/<code>.png),
// which only some products have.

type Refs = Record<number, ProductImageRef>;

const STALE_MS = 60_000;

let current: Refs = {};
let fetchedAt = 0;
let inFlight: Promise<void> | null = null;
const listeners = new Set<(next: Refs) => void>();

function load() {
  if (inFlight) return;
  inFlight = fetchProductImageRefs()
    .then((list) => {
      const next: Refs = {};
      for (const r of list) next[r.product_id] = r;
      current = next;
      fetchedAt = Date.now();
      listeners.forEach((l) => l(current));
    })
    .catch(() => {})
    .finally(() => {
      inFlight = null;
    });
}

// Call after Admin uploads or removes a photo so every photo updates at once.
export function refreshProductImages() {
  fetchedAt = 0;
  load();
}

export function useProductImages(): Refs {
  const [refs, setRefs] = useState<Refs>(current);
  useEffect(() => {
    listeners.add(setRefs);
    setRefs(current);
    if (Date.now() - fetchedAt > STALE_MS) load();
    return () => {
      listeners.delete(setRefs);
    };
  }, []);
  return refs;
}

// Whether each older photo file exists, checked once per page load.
const legacyChecks = new Map<string, Promise<string | null>>();

function legacyPhotoUrl(code: string): Promise<string | null> {
  let check = legacyChecks.get(code);
  if (!check) {
    const url = `/images/products/${encodeURIComponent(code)}.png`;
    check = new Promise((resolve) => {
      const img = new Image();
      img.onload = () => resolve(url);
      img.onerror = () => resolve(null);
      img.src = url;
    });
    legacyChecks.set(code, check);
  }
  return check;
}

/** A URL for the product's photo, or null when it has none. */
export function resolveProductPhoto(ref: ProductImageRef | undefined, size: "thumb" | "full"): Promise<string | null> {
  if (!ref) return Promise.resolve(null);
  if (ref.version) return productImageUrl(ref.product_id, ref.version, size).catch(() => null);
  return legacyPhotoUrl(ref.product_code);
}

/**
 * Photo URLs for many products at once (product_id -> url), filled in as
 * each resolves; products without a photo never appear in the map.
 */
export function useProductPhotos(productIds: number[], size: "thumb" | "full"): Record<number, string> {
  const refs = useProductImages();
  const [urls, setUrls] = useState<Record<number, string>>({});
  const key = productIds.join(",");
  useEffect(() => {
    let cancelled = false;
    setUrls({});
    for (const id of productIds) {
      resolveProductPhoto(refs[id], size).then((url) => {
        if (url && !cancelled) setUrls((prev) => (prev[id] === url ? prev : { ...prev, [id]: url }));
      });
    }
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, refs, size]);
  return urls;
}
