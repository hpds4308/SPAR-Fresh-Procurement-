// Supplier prices and branch order quantities use one decimal place only:
// the second decimal is always 0 (5.70 is fine, 5.71 isn't). The backend
// refuses anything else — see one_decimal_error in backend/app/schemas/_limits.py.

/** For the input's `step`: the arrows move 5.60 -> 5.70, not 5.61. */
export const ONE_DECIMAL_STEP = "0.1";

/** Whether a (partly) typed value is allowed: "5", "5.", "5.7", "5.70" — not "5.71". */
export function isOneDecimal(value: string): boolean {
  return /^\d*(\.\d?0?)?$/.test(value);
}

/** Shown once the field loses focus: "5.7" -> "5.70"; whole numbers stay as typed. */
export function formatOneDecimal(value: string): string {
  return value.includes(".") && value !== "." ? Number(value).toFixed(2) : value;
}
