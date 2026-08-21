import type { CSSProperties } from "react";

/**
 * Shimmering placeholder — replaces the "Loading…" text that was
 * scattered across ~20 pages with something that actually looks like
 * the content about to arrive, so the page doesn't visually "pop" once
 * data loads. Uses the app's own sage palette rather than generic gray.
 */
export function Skeleton({
  className = "",
  style,
}: {
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div
      className={`bg-gradient-to-r from-sage-100 via-sage-50 to-sage-100 bg-[length:200%_100%] animate-shimmer rounded-lg ${className}`}
      style={style}
      aria-hidden="true"
    />
  );
}

/** A handful of text-line-shaped skeletons, for card/detail-style loading. */
export function SkeletonLines({ count = 3, className = "" }: { count?: number; className?: string }) {
  return (
    <div className={`space-y-2.5 ${className}`}>
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className={`h-4 ${i === count - 1 ? "w-2/3" : "w-full"}`} />
      ))}
    </div>
  );
}

/** Mimics a chat thread's alternating message bubbles while it loads. */
export function SkeletonChat({ className = "" }: { className?: string }) {
  const widths = ["w-2/5", "w-1/2", "w-1/3", "w-2/5"];
  return (
    <div className={`px-4 py-4 space-y-3 ${className}`}>
      {widths.map((w, i) => (
        <div key={i} className={`flex ${i % 2 === 0 ? "justify-start" : "justify-end"}`}>
          <Skeleton className={`h-9 ${w} rounded-2xl`} />
        </div>
      ))}
    </div>
  );
}

/** Mimics a data table's row shape while the real rows are still loading. */
export function SkeletonTable({
  rows = 6,
  columns = 4,
  className = "",
}: {
  rows?: number;
  columns?: number;
  className?: string;
}) {
  return (
    <div className={`divide-y divide-sage-100 ${className}`}>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex items-center gap-4 px-5 py-3.5">
          {Array.from({ length: columns }).map((_, c) => (
            <Skeleton
              key={c}
              className="h-4"
              style={{ width: c === 0 ? "40%" : `${Math.max(10, 100 / columns - 5)}%` }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
