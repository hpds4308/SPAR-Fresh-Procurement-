import { PromotionType } from "../../../api/promotions";

/**
 * The three fruit & veg promotion types, in display order, each with its
 * own color — blue, green, yellow — used both on the admin Promotions
 * page and on the labels branches see next to product names.
 */
export const PROMOTION_TYPES: {
  id: PromotionType;
  label: string;
  badge: string;
  dot: string;
}[] = [
  { id: "FRESH_CHOICE", label: "Fresh Choice", badge: "bg-blue-100 text-blue-700", dot: "bg-blue-500" },
  { id: "SPECIAL_WEEKEND", label: "Special Weekend Promotion", badge: "bg-green-100 text-green-700", dot: "bg-green-500" },
  { id: "SPECIAL", label: "Special Promotion", badge: "bg-yellow-100 text-yellow-800", dot: "bg-yellow-400" },
];

export function PromotionBadge({ type, endDate, className = "" }: { type: PromotionType; endDate?: string; className?: string }) {
  const t = PROMOTION_TYPES.find((p) => p.id === type);
  if (!t) return null;
  return (
    <span
      title={endDate ? `${t.label} — until ${endDate}` : t.label}
      className={`inline-block text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${t.badge} ${className}`}
    >
      {t.label}
    </span>
  );
}
