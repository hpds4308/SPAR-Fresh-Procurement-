import { useEffect, useState } from "react";
import { fetchSettings } from "../../api/settings";

const FALLBACK_NUMBER = "076 562 2317";

// Used to only be a hardcoded literal duplicated in both Guidelines
// pages — now it's Admin-editable (Settings tab), and the tel: link's
// digits-only form is derived from it instead of kept as a second
// constant that could drift out of sync.
export function useSupportPhone(): { number: string; tel: string } {
  const [number, setNumber] = useState(FALLBACK_NUMBER);

  useEffect(() => {
    fetchSettings()
      .then((s) => setNumber(s.support_phone))
      .catch(() => {
        // Non-critical — the fallback number still displays.
      });
  }, []);

  return { number, tel: number.replace(/\D/g, "") };
}
