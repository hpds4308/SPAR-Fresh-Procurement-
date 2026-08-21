import { ReactNode } from "react";

/**
 * Wraps a dashboard's active-tab content so switching tabs fades/lifts
 * the new content in, instead of instantly swapping. `tabKey` forces a
 * fresh DOM node per tab (via React's `key`), which re-triggers the CSS
 * animation on every switch — no animation library needed for this.
 */
export function FadeSwitch({ tabKey, children }: { tabKey: string; children: ReactNode }) {
  return (
    <div key={tabKey} className="motion-safe:animate-fade-up" style={{ animationDuration: "0.35s" }}>
      {children}
    </div>
  );
}
