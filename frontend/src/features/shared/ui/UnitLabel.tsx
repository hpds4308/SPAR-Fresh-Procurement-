import { useProductImages } from "../useProductImages";

// Imported items are counted in cases, and every product's case holds a
// different weight (Admin sets it on the Product List). Wherever a unit
// is shown, a case reads "case (12 kg)" so branches and suppliers always
// know how much one case is.

export function isCaseUnit(unit: string | null | undefined): boolean {
  return (unit ?? "").trim().toLowerCase() === "case";
}

/** "case (12 kg)" for a case with a known size, otherwise the unit as-is. */
export function formatUnit(unit: string, caseKg: number | null | undefined): string {
  return isCaseUnit(unit) && caseKg ? `${unit} (${caseKg} kg)` : unit;
}

/** kg in `quantity` of the product's unit: cases times their size, kg as-is, else null. */
export function quantityInKg(quantity: number, unit: string, caseKg: number | null | undefined): number | null {
  if (isCaseUnit(unit)) return caseKg ? quantity * caseKg : null;
  return unit.trim().toLowerCase() === "kg" ? quantity : null;
}

/** Each product's case size (product_id -> kg), for pages that show many products. */
export function useCaseSizes(): Record<number, number> {
  const refs = useProductImages();
  const sizes: Record<number, number> = {};
  for (const r of Object.values(refs)) if (r.case_kg) sizes[r.product_id] = r.case_kg;
  return sizes;
}

/** The product's unit, with the case size for Imported items. */
export function UnitLabel({ productId, unit }: { productId: number; unit: string }) {
  const refs = useProductImages();
  return <>{formatUnit(unit, refs[productId]?.case_kg)}</>;
}

/** "3 case (36 kg)" for cases with a known size, otherwise "3 kg". */
export function formatQuantity(quantity: number, unit: string, caseKg: number | null | undefined): string {
  if (isCaseUnit(unit) && caseKg) return `${quantity} ${unit} (${parseFloat((quantity * caseKg).toFixed(2))} kg)`;
  return `${quantity} ${unit}`;
}

/** A small "1 case = 12 kg" pill beside an Imported product's name; nothing for other items. */
export function CaseSizeTag({ productId, className = "" }: { productId: number; className?: string }) {
  const refs = useProductImages();
  const kg = refs[productId]?.case_kg;
  if (!kg) return null;
  return (
    <span
      className={`inline-block text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap bg-sky-50 text-sky-700 border border-sky-200 ${className}`}
    >
      1 case = {kg} kg
    </span>
  );
}

/** "3 case (36 kg)" for one product, looked up by id. */
export function QuantityLabel({ productId, quantity, unit }: { productId: number; quantity: number; unit: string }) {
  const refs = useProductImages();
  return <>{formatQuantity(quantity, unit, refs[productId]?.case_kg)}</>;
}
