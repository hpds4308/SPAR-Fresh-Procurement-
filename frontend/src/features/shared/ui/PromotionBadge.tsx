import { PromotionColor } from "../../../api/promotions";
import { useActivePromotions } from "../useActivePromotions";

/**
 * The label colors Admin can give a promotion, in picker order. Class
 * names are spelled out in full so Tailwind keeps them in the build. Used
 * both on the admin Promotions page and on the labels branches see next
 * to product names.
 */
export const PROMOTION_COLORS: {
  id: PromotionColor;
  label: string;
  badge: string;
  dot: string;
}[] = [
  { id: "blue", label: "Blue", badge: "bg-blue-100 text-blue-700", dot: "bg-blue-500" },
  { id: "green", label: "Green", badge: "bg-green-100 text-green-700", dot: "bg-green-500" },
  { id: "yellow", label: "Yellow", badge: "bg-yellow-100 text-yellow-800", dot: "bg-yellow-400" },
  { id: "red", label: "Red", badge: "bg-red-100 text-red-700", dot: "bg-red-500" },
  { id: "purple", label: "Purple", badge: "bg-purple-100 text-purple-700", dot: "bg-purple-500" },
  { id: "orange", label: "Orange", badge: "bg-orange-100 text-orange-700", dot: "bg-orange-500" },
  { id: "pink", label: "Pink", badge: "bg-pink-100 text-pink-700", dot: "bg-pink-500" },
  { id: "teal", label: "Teal", badge: "bg-teal-100 text-teal-700", dot: "bg-teal-500" },
];

export function promotionColor(color: PromotionColor) {
  return PROMOTION_COLORS.find((c) => c.id === color) ?? PROMOTION_COLORS[0];
}

export function PromotionBadge({
  name,
  color,
  endDate,
  className = "",
}: {
  name: string;
  color: PromotionColor;
  endDate?: string;
  className?: string;
}) {
  return (
    <span
      title={endDate ? `${name} — until ${endDate}` : name}
      className={`inline-block text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${promotionColor(color).badge} ${className}`}
    >
      {name}
    </span>
  );
}

/**
 * The promotion label for one product, if a promotion is running on it
 * today; renders nothing otherwise. Drop it next to a product name on any
 * page — all labels on a page share one fetch.
 */
export function ProductPromotion({ productId, className = "" }: { productId: number | null; className?: string }) {
  const promotions = useActivePromotions();
  const promo = productId !== null ? promotions[productId] : undefined;
  if (!promo) return null;
  return (
    <PromotionBadge name={promo.promotion_name} color={promo.color} endDate={promo.end_date} className={className} />
  );
}
