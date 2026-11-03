import { apiFetch, apiFetchBlob } from "./client";

// One row of the admin Product List — includes items that were removed.
export type AdminProduct = {
  id: number;
  product_code: string;
  pos_code: string | null;
  description: string;
  category_id: number;
  category_name: string;
  subcategory: string | null;
  unit_id: number;
  unit_code: string;
  status: "ACTIVE" | "INACTIVE" | string;
  created_at: string | null;
  // Changes whenever the photo is replaced; null = no photo yet.
  image_version: string | null;
};

export type ProductOption = { id: number; name: string };
export type ProductOptions = { categories: ProductOption[]; units: ProductOption[] };

export type NewProduct = {
  product_code: string;
  pos_code: string | null;
  description: string;
  category_id: number;
  subcategory: string | null;
  unit_id: number;
};

// Admin only: every product, active and removed.
export function fetchAllProducts(): Promise<AdminProduct[]> {
  return apiFetch("/products/all");
}

// Admin only: categories and units to pick from when adding a product.
export function fetchProductOptions(): Promise<ProductOptions> {
  return apiFetch("/products/options");
}

// Admin only: adds a new product; branches can order it straight away.
export function createProduct(body: NewProduct): Promise<AdminProduct> {
  return apiFetch("/products", { method: "POST", body: JSON.stringify(body) });
}

// Admin only: takes a product off the list. Its order and price history is kept.
export function removeProduct(id: number): Promise<AdminProduct> {
  return apiFetch(`/products/${id}`, { method: "DELETE" });
}

// Admin only: puts a removed product back on the list.
export function restoreProduct(id: number): Promise<AdminProduct> {
  return apiFetch(`/products/${id}/restore`, { method: "POST" });
}

// Admin only: edits code, POS code, description, category, subcategory and unit.
export function updateProduct(id: number, body: NewProduct): Promise<AdminProduct> {
  return apiFetch(`/products/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

export const PRODUCT_IMAGE_SIZE = 1080;
export const PRODUCT_IMAGE_ACCEPT = ".jpg,.jpeg,.png,.webp";
export const MAX_PRODUCT_IMAGE_BYTES = 5 * 1024 * 1024;

// Admin only: sets (or replaces) the product's 1080x1080 photo plus the
// small thumbnail lists show (made in the browser — see makeThumbnail).
export function uploadProductImage(id: number, file: Blob, thumb: Blob): Promise<AdminProduct> {
  const body = new FormData();
  body.append("file", file, "photo");
  body.append("thumb", thumb, "thumb.jpg");
  return apiFetch(`/products/${id}/image`, { method: "PUT", body });
}

// Admin only: takes the product's photo off.
export function removeProductImage(id: number): Promise<AdminProduct> {
  return apiFetch(`/products/${id}/image`, { method: "DELETE" });
}

// version is set when Admin uploaded a photo; otherwise pages fall back to
// the older photo file named by product_code, if there is one.
export type ProductImageRef = { product_id: number; product_code: string; version: string | null };

// Any signed-in user: every product's code and photo version.
export function fetchProductImageRefs(): Promise<ProductImageRef[]> {
  return apiFetch("/products/images");
}

// Each photo is fetched once per version per page load, then reused.
const blobUrls = new Map<string, Promise<string>>();

/** An object URL for a product photo (the download needs the user's token, so no plain link). */
export function productImageUrl(id: number, version: string, size: "thumb" | "full"): Promise<string> {
  const key = `${id}:${version}:${size}`;
  let url = blobUrls.get(key);
  if (!url) {
    url = apiFetchBlob(`/products/${id}/image?size=${size}&v=${version}`).then((blob) => URL.createObjectURL(blob));
    url.catch(() => blobUrls.delete(key));
    blobUrls.set(key, url);
  }
  return url;
}
