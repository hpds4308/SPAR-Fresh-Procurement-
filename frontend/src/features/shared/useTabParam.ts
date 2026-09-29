import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

// Keeps a dashboard's active tab in the URL (?tab=...) instead of plain
// component state, so refreshing the page reopens the tab the user was on
// rather than dropping them back on the first one. Unknown or missing
// values fall back to `fallback`. Tab switches replace the history entry,
// so Back still leaves the dashboard instead of stepping through tabs.
export function useTabParam<T extends string>(tabs: readonly T[], fallback: T): [T, (tab: T) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get("tab");
  const tab = raw !== null && (tabs as readonly string[]).includes(raw) ? (raw as T) : fallback;

  const setTab = useCallback(
    (next: T) => {
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev);
          params.set("tab", next);
          return params;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  return [tab, setTab];
}
