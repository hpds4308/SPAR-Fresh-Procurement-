import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { IconBell, IconChevronDown, IconLogout, IconMenu, IconUser } from "./Icons";
import { CountBadge } from "./ui/Badge";
import { ConfirmDialog } from "./ui/Modal";

const ROLE_LABELS: Record<string, string> = {
  ADMIN: "Admin",
  BRANCH: "Branch",
  SUPPLIER: "Supplier",
};

export default function Header({
  title,
  subtitle,
  unreadCount,
  onBellClick,
  onMenuClick,
}: {
  title: string;
  subtitle: string;
  unreadCount?: number;
  onBellClick?: () => void;
  onMenuClick?: () => void;
}) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  async function handleLogout() {
    setLoggingOut(true);
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <header className="sticky top-0 z-30 bg-white/90 backdrop-blur border-b border-sage-200">
      <div className="px-4 md:px-6 py-3.5 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={onMenuClick}
            className="md:hidden shrink-0 text-crate-800/60 hover:text-crate-800 -ml-1 p-1"
            aria-label="Open navigation"
          >
            <IconMenu width={20} height={20} />
          </button>
          <div className="min-w-0">
            <h1 className="font-display font-bold text-base text-crate-950 leading-tight truncate">{title}</h1>
            <p className="text-xs mt-0.5 truncate" style={{ color: "#5B6E5F" }}>
              {subtitle}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {unreadCount !== undefined && (
            <button
              onClick={onBellClick}
              className="relative w-9 h-9 flex items-center justify-center rounded-full text-crate-800/50 hover:text-crate-700 hover:bg-sage-100 transition-colors duration-150"
              aria-label={`Notifications${unreadCount > 0 ? `, ${unreadCount} unread` : ""}`}
            >
              <IconBell width={18} height={18} />
              {unreadCount > 0 && (
                <span className="absolute top-1 right-1">
                  <CountBadge count={unreadCount} />
                </span>
              )}
            </button>
          )}

          <div className="relative">
            <button
              onClick={() => setMenuOpen((v) => !v)}
              className="flex items-center gap-2 rounded-full pl-1.5 pr-2.5 py-1.5 hover:bg-sage-100 transition-colors duration-150"
            >
              <span className="w-6 h-6 rounded-full bg-sage-200 flex items-center justify-center text-crate-800/60">
                <IconUser width={13} height={13} />
              </span>
              <span className="hidden sm:inline text-sm text-crate-800/80">{user?.username}</span>
              <IconChevronDown width={12} height={12} className="text-crate-800/35" />
            </button>

            {menuOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                <div className="absolute right-0 mt-1.5 w-48 bg-white rounded-xl border border-sage-100 shadow-dropdown py-1.5 z-20">
                  <div className="px-3.5 py-2 border-b border-sage-100">
                    <p className="text-sm font-semibold text-crate-950 truncate">{user?.username}</p>
                    <p className="text-xs text-crate-800/40">{ROLE_LABELS[user?.role ?? ""] ?? user?.role}</p>
                  </div>
                  <button
                    onClick={() => {
                      setMenuOpen(false);
                      setConfirmOpen(true);
                    }}
                    className="w-full flex items-center gap-2 text-left text-sm text-crate-800/70 hover:bg-sage-50 px-3.5 py-2 transition-colors duration-150"
                  >
                    <IconLogout width={15} height={15} />
                    Logout
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Signature crate-slat accent: three planks of decreasing width, a
          quiet nod to the produce crate this whole app is named for. */}
      <div className="px-4 md:px-6 flex gap-1.5 pb-2.5" aria-hidden="true">
        <span className="h-[3px] w-10 rounded-full bg-crate-700" />
        <span className="h-[3px] w-6 rounded-full bg-mango-500" />
        <span className="h-[3px] w-3.5 rounded-full bg-tomato-500" />
      </div>

      <ConfirmDialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        onConfirm={handleLogout}
        title="Log out?"
        description="You'll need to sign in again to access your dashboard."
        confirmLabel="Log out"
        danger
        loading={loggingOut}
      />
    </header>
  );
}
