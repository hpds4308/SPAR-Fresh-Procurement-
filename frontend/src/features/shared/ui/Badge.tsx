type Tone = "neutral" | "success" | "warning" | "danger" | "info";

const toneClasses: Record<Tone, string> = {
  neutral: "bg-sage-100 text-crate-800/70",
  success: "bg-crate-700/10 text-crate-800",
  warning: "bg-mango-500/15 text-[#8A5A0D]",
  danger: "bg-tomato-500/10 text-tomato-600",
  info: "bg-crate-700/5 text-crate-700",
};

/** A small pill for status words — "Sent", "Pending", "Submitted", etc. */
export function StatusBadge({ tone = "neutral", children }: { tone?: Tone; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center text-xs px-2.5 py-1 rounded-full font-semibold ${toneClasses[tone]}`}>
      {children}
    </span>
  );
}

/** A small circular count badge — unread messages, pending items, etc. */
export function CountBadge({ count, max = 99 }: { count: number; max?: number }) {
  if (!count) return null;
  return (
    <span className="inline-flex items-center justify-center min-w-[1.1rem] h-[1.1rem] px-1 rounded-full bg-tomato-500 text-white text-[10px] font-bold leading-none">
      {count > max ? `${max}+` : count}
    </span>
  );
}
