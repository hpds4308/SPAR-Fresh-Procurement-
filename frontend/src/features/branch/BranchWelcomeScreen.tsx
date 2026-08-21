import { useEffect } from "react";

// Safety net only — continues automatically even if the video fails to
// load/play (e.g. autoplay blocked). The normal path is the video's own
// onEnded firing well before this, since the clip is ~10s.
const FALLBACK_CONTINUE_MS = 20000;

export default function BranchWelcomeScreen({
  branchName,
  onContinue,
}: {
  branchName: string;
  onContinue: () => void;
}) {
  useEffect(() => {
    const t = setTimeout(onContinue, FALLBACK_CONTINUE_MS);
    return () => clearTimeout(t);
  }, [onContinue]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4 bg-crate-950 overflow-hidden">
      <video
        aria-hidden
        autoPlay
        muted
        playsInline
        onEnded={onContinue}
        className="absolute inset-0 w-full h-full object-cover"
      >
        <source src="/videos/branch-welcome-bg.mp4" type="video/mp4" />
      </video>
      <div className="absolute inset-0 bg-crate-950/45" aria-hidden="true" />

      <div className="relative text-center motion-safe:animate-fade-up">
        <span className="inline-flex items-center gap-1.5 bg-white/10 text-white text-xs font-semibold px-3 py-1.5 rounded-full mb-7">
          <span className="w-4 h-4 rounded-full bg-white flex items-center justify-center text-crate-800 text-[10px] font-display font-bold">
            S
          </span>
          SPAR Sri Lanka · Procurement
        </span>

        <h1 className="font-display font-extrabold text-3xl md:text-4xl text-white leading-tight">
          ආයුබෝවන්, {branchName}!
        </h1>
        <p className="text-white/70 text-sm md:text-base mt-3 tracking-wide uppercase">
          SPAR Sri Lanka Fresh Department
        </p>

        <button
          onClick={onContinue}
          className="mt-9 bg-white text-crate-800 rounded-full px-6 py-2.5 text-sm font-semibold hover:brightness-95 active:scale-[0.98] transition-all duration-200"
        >
          Continue to Dashboard
        </button>
      </div>
    </div>
  );
}
