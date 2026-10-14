import { FormEvent, useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import { compareProductDisplayOrder } from "../../api/orders";
import {
  AdminProduct,
  ProductOptions,
  createProduct,
  fetchAllProducts,
  fetchProductOptions,
  removeProduct,
  restoreProduct,
} from "../../api/products";
import { CategoryBadge } from "../shared/ui/CategoryBadge";
import { Modal } from "../shared/ui/Modal";
import Button from "../shared/ui/Button";
import { IconPlus } from "../shared/Icons";
import { ProductPromotion } from "../shared/ui/PromotionBadge";

type Show = "ACTIVE" | "INACTIVE" | "ALL";

const fieldClass =
  "border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm text-crate-950 placeholder:text-crate-950/35 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150";

const EMPTY_FORM = { product_code: "", pos_code: "", description: "", category_id: "", subcategory: "", unit_id: "" };

// The whole fruit & veg catalogue. Admin adds new items (branches can order
// them straight away) and removes ones no longer stocked. Removing never
// deletes a product — past orders and prices still point at it — it just
// stops appearing for branches, suppliers and the Master Data Sheet, and
// can be restored from here.
export default function AdminProductList() {
  const [products, setProducts] = useState<AdminProduct[]>([]);
  const [options, setOptions] = useState<ProductOptions>({ categories: [], units: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("ALL");
  const [show, setShow] = useState<Show>("ACTIVE");

  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [added, setAdded] = useState<string | null>(null);

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
    setAdded(null);
    setProducts((prev) => prev.map((p) => (p.id === row.id ? row : p)));
  }

  function openAdd() {
    setForm({
      ...EMPTY_FORM,
      category_id: category !== "ALL" ? String(options.categories.find((c) => c.name === category)?.id ?? "") : "",
      unit_id: String(options.units.find((u) => u.name.toUpperCase() === "KG")?.id ?? ""),
    });
    setFormError(null);
    setAdded(null);
    setAdding(true);
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!form.product_code.trim() || !form.description.trim()) {
      setFormError("Enter the product code and description.");
      return;
    }
    if (!form.category_id || !form.unit_id) {
      setFormError("Choose a category and a unit.");
      return;
    }
    setFormError(null);
    setCreating(true);
    try {
      const row = await createProduct({
        product_code: form.product_code.trim(),
        pos_code: form.pos_code.trim() || null,
        description: form.description.trim(),
        category_id: Number(form.category_id),
        subcategory: form.subcategory.trim() || null,
        unit_id: Number(form.unit_id),
      });
      setProducts((prev) => [...prev, row]);
      setAdding(false);
      setAdded(row.description);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not add the product. Please try again.");
    } finally {
      setCreating(false);
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

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-hidden">
        <div className="p-6 border-b border-sage-100">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="font-display font-semibold text-crate-950">Product list</p>
              <p className="text-sm text-crate-800/60 mt-1">
                Every fruit &amp; vegetable item. New items show up for branches and suppliers straight away. Removing
                an item hides it everywhere but keeps its order and price history, and you can restore it later.
              </p>
            </div>
            <Button onClick={openAdd} className="inline-flex items-center gap-1.5">
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
          {added && <p className="text-crate-700 text-sm mt-3">✓ {added} added.</p>}
          {error && <p className="text-tomato-600 text-sm mt-3">{error}</p>}
        </div>

        <div className="hidden lg:grid grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.1fr)_4rem_8rem] gap-4 px-6 py-2 bg-sage-50/60 border-b border-sage-100 text-[11px] uppercase tracking-wide text-crate-800/50 font-semibold">
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
                className={`grid grid-cols-2 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.1fr)_4rem_8rem] gap-x-4 gap-y-1 lg:items-center px-6 py-3 hover:bg-sage-50/50 transition-colors duration-100 ${
                  removed ? "bg-sage-50/40" : ""
                }`}
              >
                <div className="min-w-0 col-span-2 lg:col-span-1">
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
                <span className="col-span-2 lg:col-span-1 lg:text-right">
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
        open={adding}
        onClose={() => !creating && setAdding(false)}
        title="Add a product"
        actions={
          <>
            <Button variant="secondary" size="sm" onClick={() => setAdding(false)} disabled={creating}>
              Cancel
            </Button>
            <Button size="sm" type="submit" form="add-product-form" loading={creating}>
              Add Product
            </Button>
          </>
        }
      >
        <form id="add-product-form" onSubmit={handleCreate} className="space-y-3">
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
