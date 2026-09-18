import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth, ApiError } from "./AuthContext";
import { useSupportPhone } from "../shared/useSupportPhone";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [shakeError, setShakeError] = useState(false);
  const [showForgotHelp, setShowForgotHelp] = useState(false);
  const { number: supportNumber, tel: supportTel } = useSupportPhone();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const redirectTo = await login(username, password);
      navigate(redirectTo, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Could not reach the server. Please try again.");
      }
      setShakeError(true);
      setTimeout(() => setShakeError(false), 500);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative h-screen overflow-hidden font-body flex items-center justify-center px-4 py-4">
      {/* full-bleed ambient produce video background */}
      <video
        aria-hidden
        autoPlay
        loop
        muted
        playsInline
        className="pointer-events-none absolute inset-0 w-full h-full object-cover z-0"
      >
        <source src="/videos/login-produce-1080p.mp4" type="video/mp4" />
      </video>

      <div className="relative z-10 w-full max-w-md motion-safe:animate-fade-up">
        {/* card, scaled down 10% as a unit */}
        <form
          onSubmit={handleSubmit}
          className="relative z-0 bg-white rounded-[2rem] shadow-[0_30px_60px_-15px_rgba(21,56,38,0.25)] overflow-hidden pb-6 px-8 md:px-10"
          style={{ transform: "scale(0.9)", transformOrigin: "center" }}
        >
          <div className="-mx-8 md:-mx-10 mb-3">
            <img src="/images/spar-fresh-procurement-logo.png" alt="SPAR Fresh Procurement" className="w-full h-auto block" />
          </div>

          <p className="text-center text-sm mt-1.5 mb-4" style={{ color: "#5B6E5F" }}>
            Sign in to source fresh, simplified.
          </p>

          <label htmlFor="username" className="block text-xs font-semibold uppercase tracking-wide text-crate-800/70 mb-1.5 ml-1">
            Username
          </label>
          <div className="relative mb-3 group">
            <span className="absolute left-4 top-1/2 -translate-y-1/2 text-crate-700 transition-transform duration-300 group-focus-within:scale-110">
              <LeafIcon />
            </span>
            <input
              id="username"
              className="w-full border border-sage-300 bg-sage-50/60 rounded-full pl-11 pr-4 py-3 text-sm text-crate-950 placeholder:text-crate-950/35 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-200"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. branch.kandy"
              autoFocus
              required
            />
          </div>

          <label htmlFor="password" className="block text-xs font-semibold uppercase tracking-wide text-crate-800/70 mb-1.5 ml-1">
            Password
          </label>
          <div className="relative mb-2 group">
            <span className="absolute left-4 top-1/2 -translate-y-1/2 text-crate-700 transition-transform duration-300 group-focus-within:scale-110">
              <CarrotIcon />
            </span>
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              className="w-full border border-sage-300 bg-sage-50/60 rounded-full pl-11 pr-14 py-3 text-sm text-crate-950 placeholder:text-crate-950/35 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-200"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
            <button
              type="button"
              onClick={() => setShowPassword((s) => !s)}
              className="absolute right-4 top-1/2 -translate-y-1/2 text-xs font-semibold text-crate-700 hover:text-crate-800 transition-colors duration-200"
              tabIndex={-1}
            >
              {showPassword ? "Hide" : "Show"}
            </button>
          </div>

          <div className="flex justify-end mb-1 mt-1">
            <button
              type="button"
              onClick={() => setShowForgotHelp((s) => !s)}
              className="text-xs font-medium text-crate-700 hover:text-crate-800 transition-colors duration-200"
            >
              Forgot password?
            </button>
          </div>

          {showForgotHelp && (
            <div className="mb-5 rounded-2xl bg-sage-100 px-4 py-2.5 text-xs text-crate-800/80 motion-safe:animate-pop-in">
              These are shared branch/supplier logins, so resets go through your administrator — call{" "}
              <a href={`tel:${supportTel}`} className="font-semibold text-crate-700 hover:underline">
                {supportNumber}
              </a>{" "}
              and they can reset it for you from the Admin dashboard.
              <p className="mt-2 pt-2 border-t border-sage-200">
                Administrator locked out with no one else to ask?{" "}
                <button
                  type="button"
                  onClick={() => navigate("/recover")}
                  className="font-semibold text-crate-700 hover:underline"
                >
                  Recover account access
                </button>{" "}
                with a token from your server operator.
              </p>
            </div>
          )}

          {error && (
            <div
              className={`mb-5 rounded-2xl bg-tomato-500/10 border border-tomato-500/25 px-4 py-2.5 text-sm text-tomato-600 motion-safe:animate-pop-in ${
                shakeError ? "motion-safe:animate-shake" : ""
              }`}
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="relative w-full bg-gradient-to-b from-crate-700 to-crate-800 text-white rounded-full py-3.5 text-sm font-semibold tracking-wide overflow-hidden hover:brightness-110 active:scale-[0.98] disabled:opacity-70 disabled:active:scale-100 transition-all duration-200 shadow-lg shadow-crate-800/25"
          >
            <span className={`inline-flex items-center justify-center gap-2 transition-opacity duration-150 ${submitting ? "opacity-0" : "opacity-100"}`}>
              Sign in
            </span>
            {submitting && (
              <span className="absolute inset-0 flex items-center justify-center gap-2">
                <Spinner />
                Signing in…
              </span>
            )}
          </button>

          <p className="mt-4 text-center text-xs text-crate-950/35">
            Fresh sourcing, sorted. Internal access only.
          </p>
        </form>
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
      <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
    </svg>
  );
}

function LeafIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <path
        d="M20 4C10 4 4 10 4 18c0 1.1.9 2 2 2 8 0 14-6 14-16 0-.6-.4-1-1-1-.9 0-1.7.2-2.4.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M6 18c3-3 7-7 12-12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function CarrotIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <path d="M3 21l7-7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path
        d="M9 15c-2-2-2-6 3-10 5-3 9-3 9-3s0 4-3 9c-4 5-8 5-9 4z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M14 5l2 2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

