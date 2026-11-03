import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { compareProductDisplayOrder } from "../../api/orders";
import {
  AdminProduct,
  MAX_PRODUCT_IMAGE_BYTES,
  PRODUCT_IMAGE_ACCEPT,
  PRODUCT_IMAGE_SIZE,
  ProductOptions,
  createProduct,
  fetchAllProducts,
  fetchProductOptions,
  productImageUrl,
  removeProduct,
  removeProductImage,
  restoreProduct,
  updateProduct,
  uploadProductImage,
} from "../../api/products";
import { CategoryBadge } from "../shared/ui/CategoryBadge";
import { Modal } from "../shared/ui/Modal";
import Button from "../shared/ui/Button";
import { IconPlus } from "../shared/Icons";
import { ProductPromotion } from "../shared/ui/PromotionBadge";
import { ProductThumb } from "../shared/ui/ProductThumb";
import { refreshProductImages, resolveProductPhoto } from "../shared/useProductImages";

type Show = "ACTIVE" | "INACTIVE" | "ALL";

const fieldClass =
  "border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm text-crate-950 placeholder:text-crate-950/35 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150";

const EMPTY_FORM = { product_code: "", pos_code: "", description: "", category_id: "", subcategory: "", unit_id: "" };

const THUMB_SIZE = 240;

// What the photo picker holds: the product's current photo, a new one to
// upload on save, or "remove the current one on save".
type Photo =
  | { kind: "none" }
  | { kind: "current"; url: string | null }
  | { kind: "new"; file: File; thumb: Blob; url: string }
  | { kind: "remove" };

function loadImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("unreadable"));
    img.src = URL.createObjectURL(file);
  });
}

// Checks the chosen file is a 1080x1080 photo and draws the small JPEG
// thumbnail lists show (the server has no image library to make one).
async function readPhoto(file: File): Promise<{ thumb: Blob; url: string }> {
  if (!/\.(jpe?g|png|webp)$/i.test(file.name)) throw new Error("Choose a JPG, PNG or WebP photo.");
  if (file.size > MAX_PRODUCT_IMAGE_BYTES) throw new Error("That photo is too large. Use one under 5 MB.");
  let img: HTMLImageElement;
  try {
    img = await loadImage(file);
  } catch {
    throw new Error("That file couldn't be opened as a photo.");
  }
  if (img.naturalWidth !== PRODUCT_IMAGE_SIZE || img.naturalHeight !== PRODUCT_IMAGE_SIZE) {
    URL.revokeObjectURL(img.src);
    throw new Error(
      `The photo must be exactly ${PRODUCT_IMAGE_SIZE} x ${PRODUCT_IMAGE_SIZE} pixels (this one is ${img.naturalWidth} x ${img.naturalHeight}).`
    );
  }
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = THUMB_SIZE;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#fff"; // transparent PNGs get a white background, not black, as JPEG
  ctx.fillRect(0, 0, THUMB_SIZE, THUMB_SIZE);
  ctx.drawImage(img, 0, 0, THUMB_SIZE, THUMB_SIZE);
  const thumb = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
  if (!thumb) throw new Error("Could not prepare the photo. Please try again.");
  return { thumb, url: img.src };
}

// The whole fruit & veg catalogue. Admin adds new items (branches can order
// them straight away), edits them (code, POS code, name, category, unit,
// photo — every page shows the change at once) and removes ones no longer
// stocked. Removing never deletes a product — past orders and prices still
// point at it — it just stops appearing for branches, suppliers and the
// Master Data Sheet, and can be restored from here.
export default function AdminProductList() {
  const [products, setProducts] = useState<AdminProduct[]>([]);
  const [options, setOptions] = useState<ProductOptions>({ categories: [], units: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("ALL");
  const [show, setShow] = useState<Show>("ACTIVE");

  // null = closed, "new" = adding, otherwise the product being edited.
  const [editing, setEditing] = useState<AdminProduct | "new" | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [photo, setPhoto] = useState<Photo>({ kind: "none" });
  // The older photo file shipped with the site for this product's code, if
  // any — shown until Admin uploads one (it can't be removed from here).
  const [legacyUrl, setLegacyUrl] = useState<string | null>(null);
  const openSeq = useRef(0);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const [toRemove, setToRemove] = useState<AdminProduct | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchAllProducts(), fetchProductOptions()])
      .then(([p, o]) => {
        if (cancelled) return;
        setProducts(p);
        setOptions(o);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load the product list.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const sorted = useMemo(() => [...products].sort(compareProductDisplayOrder), [products]);

  const categories = useMemo(() => {
    const set = new Set(products.map((p) => p.category_name));
    return ["ALL", ...Array.from(set).sort()];
  }, [products]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return sorted.filter((p) => {
      if (show !== "ALL" && p.status !== show) return false;
      if (category !== "ALL" && p.category_name !== category) return false;
      if (
        q &&
        !p.description.toLowerCase().includes(q) &&
        !p.product_code.toLowerCase().includes(q) &&
        !(p.pos_code ?? "").toLowerCase().includes(q)
      )
        return false;
      return true;
    });
  }, [sorted, show, category, search]);

  const activeCount = products.filter((p) => p.status === "ACTIVE").length;
  const removedCount = products.length - activeCount;

  function replace(row: AdminProduct) {
    setNotice(null);
    setProducts((prev) => prev.map((p) => (p.id === row.id ? row : p)));
  }

  function openForm(p: AdminProduct | "new") {
    const seq = ++openSeq.current;
    setLegacyUrl(null);
    if (p === "new") {
      setForm({
        ...EMPTY_FORM,
        category_id: category !== "ALL" ? String(options.categories.find((c) => c.name === category)?.id ?? "") : "",
        unit_id: String(options.units.find((u) => u.name.toUpperCase() === "KG")?.id ?? ""),
      });
      setPhoto({ kind: "none" });
    } else {
      setForm({
        product_code: p.product_code,
        pos_code: p.pos_code ?? "",
        description: p.description,
        category_id: String(p.category_id),
        subcategory: p.subcategory ?? "",
        unit_id: String(p.unit_id),
      });
      if (p.image_version) {
        setPhoto({ kind: "current", url: null });
        const version = p.image_version;
        productImageUrl(p.id, version, "full")
          .then((url) => seq === openSeq.current && setPhoto((cur) => (cur.kind === "current" ? { kind: "current", url } : cur)))
          .catch(() => {});
      } else {
        setPhoto({ kind: "none" });
        resolveProductPhoto({ product_id: p.id, product_code: p.product_code, version: null }, "full").then(
          (url) => seq === openSeq.current && setLegacyUrl(url)
        );
      }
    }
    setPhotoError(null);
    setFormError(null);
    setNotice(null);
    setEditing(p);
  }

  async function handlePhotoChosen(file: File | undefined) {
    if (fileInput.current) fileInput.current.value = "";
    if (!file) return;
    setPhotoError(null);
    try {
      const { thumb, url } = await readPhoto(file);
      setPhoto({ kind: "new", file, thumb, url });
    } catch (err) {
      setPhotoError(err instanceof Error ? err.message : "That photo can't be used.");
    }
  }

  function handlePhotoRemoved() {
    setPhotoError(null);
    const original = editing !== "new" && editing?.image_version;
    setPhoto(original ? { kind: "remove" } : { kind: "none" });
  }

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    if (!editing) return;
    if (!form.product_code.trim() || !form.description.trim()) {
      setFormError("Enter the product code and description.");
      return;
    }
    if (!form.category_id || !form.unit_id) {
      setFormError("Choose a category and a unit.");
      return;
    }
    setFormError(null);
    setSaving(true);
    const body = {
      product_code: form.product_code.trim(),
      pos_code: form.pos_code.trim() || null,
      description: form.description.trim(),
      category_id: Number(form.category_id),
      subcategory: form.subcategory.trim() || null,
      unit_id: Number(form.unit_id),
    };
    const isNew = editing === "new";
    let row: AdminProduct | null = null;
    try {
      row = isNew ? await createProduct(body) : await updateProduct(editing.id, body);
      if (photo.kind === "new") row = await uploadProductImage(row.id, photo.file, photo.thumb);
      else if (photo.kind === "remove") row = await removeProductImage(row.id);
      if (photo.kind === "new" || photo.kind === "remove") refreshProductImages();
      const saved = row;
      setProducts((prev) => (isNew ? [...prev, saved] : prev.map((p) => (p.id === saved.id ? saved : p))));
      setEditing(null);
      setNotice(isNew ? `${saved.description} added.` : `${saved.description} saved.`);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not save the product. Please try again.";
      if (row) {
        // The details saved but the photo didn't — keep the form open on
        // the saved product so Admin can pick another photo.
        const saved = row;
        setProducts((prev) => (isNew ? [...prev, saved] : prev.map((p) => (p.id === saved.id ? saved : p))));
        setEditing(saved);
        setPhotoError(`The details were saved, but not the photo: ${message}`);
      } else {
        setFormError(message);
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleRemove() {
    if (!toRemove) return;
    setError(null);
    setBusyId(toRemove.id);
    try {
      replace(await removeProduct(toRemove.id));
      setToRemove(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not remove the product. Please try again.");
      setToRemove(null);
    } finally {
      setBusyId(null);
    }
  }

  async function handleRestore(p: AdminProduct) {
    setError(null);
    setBusyId(p.id);
    try {
      replace(await restoreProduct(p.id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not restore the product. Please try again.");
    } finally {
      setBusyId(null);
    }
  }

  if (loading) {
    return <p className="text-sm text-crate-800/50 p-6">Loading products…</p>;
  }

  const isNew = editing === "new";
  const uploaded = photo.kind === "new" || photo.kind === "current";
  const showingLegacy = photo.kind === "none" && legacyUrl !== null;
  const photoUrl = uploaded ? photo.url : showingLegacy ? legacyUrl : null;
  const hasPhoto = uploaded || showingLegacy;

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-hidden">
        <div className="p-6 border-b border-sage-100">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="font-display font-semibold text-crate-950">Product list</p>
              <p className="text-sm text-crate-800/60 mt-1">
                Every fruit &amp; vegetable item. Click a product to edit its details or photo — changes show on every
                page straight away. Removing an item hides it everywhere but keeps its order and price history, and you
                can restore it later.
              </p>
            </div>
            <Button onClick={() => openForm("new")} className="inline-flex items-center gap-1.5">
              <IconPlus className="w-4 h-4" />
              Add Product
            </Button>
          </div>

          <div className="flex flex-col sm:flex-row gap-3 mt-4">
            <input
              placeholder="Search by name, product code or POS code…"
              aria-label="Search products"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className={`flex-1 ${fieldClass}`}
            />
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              aria-label="Category"
              className={fieldClass}
            >
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c === "ALL" ? "All categories" : c}
                </option>
              ))}
            </select>
            <div role="radiogroup" aria-label="Show" className="flex rounded-full border border-sage-300 p-0.5 text-sm">
              {(
                [
                  ["ACTIVE", `Active (${activeCount})`],
                  ["INACTIVE", `Removed (${removedCount})`],
                  ["ALL", "All"],
                ] as [Show, string][]
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  role="radio"
                  aria-checked={show === id}
                  onClick={() => setShow(id)}
                  className={`px-3 py-1.5 rounded-full whitespace-nowrap transition-colors duration-100 ${
                    show === id ? "bg-crate-700 text-white" : "text-crate-800/70 hover:bg-sage-50"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          {notice && <p className="text-crate-700 text-sm mt-3">✓ {notice}</p>}
          {error && <p className="text-tomato-600 text-sm mt-3">{error}</p>}
        </div>

        <div className="hidden lg:grid grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.1fr)_4rem_11rem] gap-4 px-6 py-2 bg-sage-50/60 border-b border-sage-100 text-[11px] uppercase tracking-wide text-crate-800/50 font-semibold">
          <span>Description</span>
          <span>Product Code</span>
          <span>POS Code</span>
          <span>Category</span>
          <span>Unit</span>
          <span className="text-right">Action</span>
        </div>

        <div className="max-h-[36rem] overflow-y-auto divide-y divide-sage-100">
          {filtered.length === 0 && (
            <p className="p-6 text-sm text-crate-800/35 text-center">No products match your search.</p>
          )}
          {filtered.map((p) => {
            const removed = p.status !== "ACTIVE";
            return (
              <div
                key={p.id}
                onClick={() => openForm(p)}
                className={`grid grid-cols-2 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.1fr)_4rem_11rem] gap-x-4 gap-y-1 lg:items-center px-6 py-3 cursor-pointer hover:bg-sage-50/50 transition-colors duration-100 ${
                  removed ? "bg-sage-50/40" : ""
                }`}
              >
                <div className="min-w-0 col-span-2 lg:col-span-1 flex items-center gap-3">
                  <ProductThumb productId={p.id} name={p.description} size="md" placeholder />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 min-w-0">
                      <p className={`text-sm truncate ${removed ? "text-crate-800/45 line-through" : "text-crate-950"}`}>
                        {p.description}
                      </p>
                      {!removed && <ProductPromotion productId={p.id} className="shrink-0" />}
                    </div>
                    {(p.subcategory || removed) && (
                      <p className="text-xs text-crate-800/40 truncate">
                        {p.subcategory}
                        {p.subcategory && removed && " · "}
                        {removed && <span className="text-tomato-600/80">Removed</span>}
                      </p>
                    )}
                  </div>
                </div>
                <span className="text-sm text-crate-800/70 tabular-nums">
                  <span className="lg:hidden text-xs text-crate-800/40">Code </span>
                  {p.product_code}
                </span>
                <span className="text-sm text-crate-800/70 tabular-nums">
                  <span className="lg:hidden text-xs text-crate-800/40">POS </span>
                  {p.pos_code ?? <span className="text-crate-800/35">—</span>}
                </span>
                <span>
                  <CategoryBadge name={p.category_name} />
                </span>
                <span className="text-sm text-crate-800/70">{p.unit_code}</span>
                <span
                  className="col-span-2 lg:col-span-1 flex gap-2 lg:justify-end"
                  onClick={(e) => e.stopPropagation()}
                >
                  <Button variant="secondary" size="sm" onClick={() => openForm(p)} disabled={busyId === p.id}>
                    Edit
                  </Button>
                  {removed ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => handleRestore(p)}
                      loading={busyId === p.id}
                    >
                      Restore
                    </Button>
                  ) : (
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => setToRemove(p)}
                      disabled={busyId === p.id}
                    >
                      Remove
                    </Button>
                  )}
                </span>
              </div>
            );
          })}
        </div>

        <div className="px-6 py-4 border-t border-sage-100 text-sm text-crate-800/60">
          Showing {filtered.length} of {products.length} product{products.length === 1 ? "" : "s"}
        </div>
      </div>

      <Modal
        open={editing !== null}
        onClose={() => !saving && setEditing(null)}
        title={isNew ? "Add a product" : "Edit product"}
        actions={
          <>
            <Button variant="secondary" size="sm" onClick={() => setEditing(null)} disabled={saving}>
              Cancel
            </Button>
            <Button size="sm" type="submit" form="product-form" loading={saving}>
              {isNew ? "Add Product" : "Save Changes"}
            </Button>
          </>
        }
      >
        <form id="product-form" onSubmit={handleSave} className="space-y-3 max-h-[70vh] overflow-y-auto -mx-1 px-1">
          <div className="flex items-center gap-4">
            <div className="w-24 h-24 shrink-0 rounded-xl overflow-hidden border border-sage-200 bg-sage-50 flex items-center justify-center">
              {photoUrl ? (
                <img src={photoUrl} alt="Product photo" className="w-full h-full object-cover" />
              ) : (
                <span className="text-[11px] text-crate-800/40 text-center px-2">
                  {photo.kind === "current" ? "Loading…" : "No photo"}
                </span>
              )}
            </div>
            <div className="min-w-0 space-y-2">
              <p className="text-xs text-crate-800/50">
                Photo <span className="text-crate-800/40">(optional)</span> — JPG, PNG or WebP, exactly{" "}
                {PRODUCT_IMAGE_SIZE} x {PRODUCT_IMAGE_SIZE} pixels.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => fileInput.current?.click()}
                  disabled={saving}
                >
                  {hasPhoto ? "Change Photo" : "Upload Photo"}
                </Button>
                {uploaded && (
                  <Button type="button" variant="secondary" size="sm" onClick={handlePhotoRemoved} disabled={saving}>
                    Remove Photo
                  </Button>
                )}
              </div>
              {showingLegacy && (
                <p className="text-xs text-crate-800/45">This is the older photo on file. Upload one to replace it.</p>
              )}
              {photo.kind === "remove" && (
                <p className="text-xs text-tomato-600/80">The photo will be removed when you save.</p>
              )}
              <input
                ref={fileInput}
                type="file"
                accept={PRODUCT_IMAGE_ACCEPT}
                className="hidden"
                onChange={(e) => handlePhotoChosen(e.target.files?.[0])}
              />
            </div>
          </div>
          {photoError && <p className="text-tomato-600 text-sm">{photoError}</p>}
          <label className="block text-sm text-crate-800/70">
            Description
            <input
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              maxLength={200}
              placeholder="e.g. RAMBUTAN"
              autoFocus
              className={`mt-1 w-full ${fieldClass}`}
            />
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="block text-sm text-crate-800/70">
              Product code
              <input
                value={form.product_code}
                onChange={(e) => setForm({ ...form, product_code: e.target.value })}
                maxLength={30}
                placeholder="e.g. 4503300"
                className={`mt-1 w-full ${fieldClass}`}
              />
            </label>
            <label className="block text-sm text-crate-800/70">
              POS code <span className="text-crate-800/40">(optional)</span>
              <input
                value={form.pos_code}
                onChange={(e) => setForm({ ...form, pos_code: e.target.value })}
                maxLength={30}
                placeholder="e.g. 00000500"
                className={`mt-1 w-full ${fieldClass}`}
              />
            </label>
            <label className="block text-sm text-crate-800/70">
              Category
              <select
                value={form.category_id}
                onChange={(e) => setForm({ ...form, category_id: e.target.value })}
                className={`mt-1 w-full ${fieldClass}`}
              >
                <option value="">Choose…</option>
                {options.categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm text-crate-800/70">
              Unit
              <select
                value={form.unit_id}
                onChange={(e) => setForm({ ...form, unit_id: e.target.value })}
                className={`mt-1 w-full ${fieldClass}`}
              >
                <option value="">Choose…</option>
                {options.units.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="block text-sm text-crate-800/70">
            Subcategory <span className="text-crate-800/40">(optional)</span>
            <input
              value={form.subcategory}
              onChange={(e) => setForm({ ...form, subcategory: e.target.value })}
              maxLength={100}
              className={`mt-1 w-full ${fieldClass}`}
            />
          </label>
          {!isNew && (
            <p className="text-xs text-crate-800/45">
              Orders, prices and purchase orders for this product keep pointing at it, so they show the new details
              too.
            </p>
          )}
          {formError && <p className="text-tomato-600 text-sm">{formError}</p>}
        </form>
      </Modal>

      <Modal
        open={toRemove !== null}
        onClose={() => busyId === null && setToRemove(null)}
        title={toRemove ? `Remove "${toRemove.description}"?` : "Remove product?"}
        actions={
          <>
            <Button variant="secondary" size="sm" onClick={() => setToRemove(null)} disabled={busyId !== null}>
              Cancel
            </Button>
            <Button variant="danger" size="sm" onClick={handleRemove} loading={busyId !== null}>
              Remove Product
            </Button>
          </>
        }
      >
        <p className="text-sm text-crate-800/70">
          Branches won't be able to order it and suppliers won't see it on their price sheets. Past orders and prices
          for it are kept, and you can restore it any time from the Removed list.
        </p>
      </Modal>
    </div>
  );
}
