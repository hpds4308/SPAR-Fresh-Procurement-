import { FormEvent, useState } from "react";
import { ApiError, useAuth } from "./AuthContext";

const MIN_LENGTH = 8;

// Shown instead of the dashboard while users.must_change_password is set: the account still has the
// seeded starting password (or a temporary one an administrator issued), which other people know. The
// API refuses every other request until this succeeds (see get_current_user), so this screen is the
// only way forward besides signing out.
export default function ForcedPasswordChange() {
  const { user, changePassword, logout } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (newPassword.length < MIN_LENGTH) {
      setError(`New password must be at least ${MIN_LENGTH} characters.`);
      return;
    }
    if (newPassword === currentPassword) {
      setError("Choose a password different from the current one.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("The two new passwords don't match.");
      return;
    }
    setSubmitting(true);
    try {
      await changePassword(currentPassword, newPassword);
      // On success the auth context reloads the user (must_change_password is now false) and the route
      // renders the dashboard - nothing more to do here.
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server. Please try again.");
      setSubmitting(false);
    }
  }

  const inputClass =
    "w-full border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2.5 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150";
  const labelClass = "block text-xs font-semibold uppercase tracking-wide text-crate-800/70 mb-1.5";

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-8 bg-gray-50 font-body">
      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-[2rem] shadow-[0_30px_60px_-15px_rgba(21,56,38,0.25)] p-8 max-w-md w-full motion-safe:animate-fade-up"
      >
        <h1 className="font-display font-bold text-xl text-crate-950">Choose your own password</h1>
        <p className="text-sm text-crate-800/60 mt-1.5 mb-6">
          {user ? <>Signed in as <strong>{user.username}</strong>. </> : null}
          This account is still using a starting password that other people know. Pick a new one to
          continue — you'll use it from now on.
        </p>

        <label htmlFor="currentPassword" className={labelClass}>
          Current password
        </label>
        <input
          id="currentPassword"
          type="password"
          autoComplete="current-password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          required
          autoFocus
          className={inputClass}
        />

        <label htmlFor="newPassword" className={labelClass}>
          New password
        </label>
        <input
          id="newPassword"
          type="password"
          autoComplete="new-password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          required
          minLength={MIN_LENGTH}
          placeholder={`At least ${MIN_LENGTH} characters`}
          className={inputClass}
        />

        <label htmlFor="confirmPassword" className={labelClass}>
          Confirm new password
        </label>
        <input
          id="confirmPassword"
          type="password"
          autoComplete="new-password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          required
          minLength={MIN_LENGTH}
          className={`${inputClass} mb-5`}
        />

        {error && (
          <p role="alert" className="text-tomato-600 text-sm mb-4">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full bg-gradient-to-b from-crate-700 to-crate-800 text-white rounded-full py-3 text-sm font-semibold hover:brightness-110 active:scale-[0.98] disabled:opacity-70 disabled:active:scale-100 transition-all duration-200"
        >
          {submitting ? "Saving…" : "Save new password"}
        </button>

        <button
          type="button"
          onClick={() => void logout()}
          className="w-full text-center text-xs text-crate-800/50 hover:text-crate-700 mt-4 transition-colors duration-150"
        >
          Sign out instead
        </button>
      </form>
    </div>
  );
}
