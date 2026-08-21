import { ButtonHTMLAttributes, forwardRef } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-gradient-to-b from-crate-700 to-crate-800 text-white shadow-sm hover:brightness-110 disabled:hover:brightness-100",
  secondary:
    "border border-sage-300 text-crate-800 bg-white hover:bg-sage-50 disabled:hover:bg-white",
  ghost: "text-crate-700 hover:bg-sage-100 disabled:hover:bg-transparent",
  danger:
    "border border-tomato-500/30 text-tomato-600 bg-white hover:bg-tomato-500/5 disabled:hover:bg-white",
};

const sizeClasses: Record<Size, string> = {
  sm: "text-xs px-3.5 py-1.5",
  md: "text-sm px-5 py-2",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

/**
 * Shared button primitive — one visual treatment per intent (primary /
 * secondary / ghost / danger), used consistently instead of each page
 * hand-rolling its own button classes. `loading` disables the button and
 * swaps in an ellipsis rather than the caller managing that separately.
 */
const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading = false, disabled, className = "", children, ...rest },
  ref
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-1.5 rounded-full font-semibold transition-all duration-150 active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100 disabled:cursor-not-allowed ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
      {...rest}
    >
      {loading ? "…" : children}
    </button>
  );
});

export default Button;
