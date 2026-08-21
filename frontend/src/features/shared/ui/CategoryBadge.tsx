/**
 * Color-codes a product category so it's scannable at a glance across
 * Branch/Supplier/Admin product lists — previously always plain text.
 * Hand-picked per the 4 known categories (not a hash function) so each
 * choice is intentional; anything unrecognized falls back to the
 * existing sage/crate brand neutral rather than breaking.
 */
const CATEGORY_COLORS: Record<string, string> = {
  Fruit: "bg-amber-100 text-amber-700",
  "Vege Low": "bg-teal-100 text-teal-700",
  "Vege Pola": "bg-lime-100 text-lime-700",
  "Vege Up": "bg-emerald-100 text-emerald-700",
};

const FALLBACK_COLOR = "bg-sage-100 text-crate-700";

export function CategoryBadge({ name, className = "" }: { name: string; className?: string }) {
  const color = CATEGORY_COLORS[name] ?? FALLBACK_COLOR;
  return (
    <span
      className={`inline-block text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${color} ${className}`}
    >
      {name}
    </span>
  );
}
