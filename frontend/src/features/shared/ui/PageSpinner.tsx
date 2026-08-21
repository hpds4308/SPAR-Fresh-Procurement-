/** Full-page loading state (auth check, initial route resolution) — a
 * branded spinner instead of bare "Loading…" text. */
export function PageSpinner() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-gray-50 font-body motion-safe:animate-fade-up">
      <span className="w-9 h-9 rounded-full bg-crate-700 flex items-center justify-center text-white text-sm font-display font-bold animate-pulse">
        S
      </span>
      <svg className="animate-spin h-5 w-5 text-crate-700/50" viewBox="0 0 24 24" fill="none">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
        <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
      </svg>
    </div>
  );
}
