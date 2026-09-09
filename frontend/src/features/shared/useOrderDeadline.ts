import { useEffect, useState } from "react";
import { fetchSettings, type Settings } from "../../api/settings";

// Same fix as useSupportPhone: both Guidelines pages used to hardcode
// their cutoff time directly in the page copy ("2:00 PM" / "දහවල් 2.00"
// for branches, "12:00 noon" / "දවල් 12.00" for suppliers). That silently
// went stale the moment Admin changed the real cutoff via Settings, and
// on this deployment both actually have — telling users the wrong time.
// These read the same Admin-editable settings everything else already
// enforces against, so the two can never drift apart again.

function useDeadlineSetting(key: keyof Settings, fallback24h: string) {
  const [deadline24h, setDeadline24h] = useState(fallback24h);

  useEffect(() => {
    fetchSettings()
      .then((s) => setDeadline24h(s[key]))
      .catch(() => {
        // Non-critical — the fallback deadline still displays.
      });
  }, [key]);

  return { deadline24h, english: formatEnglish(deadline24h), sinhala: formatSinhala(deadline24h) };
}

export function useOrderDeadline() {
  return useDeadlineSetting("branch_order_deadline", "14:00");
}

export function useSupplierPriceDeadline() {
  return useDeadlineSetting("supplier_price_deadline", "12:00");
}

function parse(deadline24h: string): { hour: number; minute: number } {
  const [h, m] = deadline24h.split(":").map(Number);
  return { hour: Number.isFinite(h) ? h : 14, minute: Number.isFinite(m) ? m : 0 };
}

function formatEnglish(deadline24h: string): string {
  const { hour, minute } = parse(deadline24h);
  const period = hour >= 12 ? "PM" : "AM";
  const hour12 = hour % 12 === 0 ? 12 : hour % 12;
  return `${hour12}:${String(minute).padStart(2, "0")} ${period}`;
}

// Sinhala expresses time-of-day with a leading period word rather than a
// trailing AM/PM marker. Bucketed by common usage rather than a strict
// 12-hour split, since දහවල්/සවස don't map onto AM/PM boundaries.
function sinhalaPeriodWord(hour: number): string {
  if (hour >= 5 && hour < 12) return "උදේ"; // morning
  if (hour >= 12 && hour < 17) return "දහවල්"; // midday/afternoon
  if (hour >= 17 && hour < 20) return "සවස"; // evening
  return "රාත්‍රී"; // night
}

function formatSinhala(deadline24h: string): string {
  const { hour, minute } = parse(deadline24h);
  const hour12 = hour % 12 === 0 ? 12 : hour % 12;
  return `${sinhalaPeriodWord(hour)} ${hour12}.${String(minute).padStart(2, "0")}`;
}
