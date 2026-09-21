import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { apiFetch, setStoredTokens, clearStoredTokens, ApiError } from "../../api/client";

export type CurrentUser = {
  id: number;
  username: string;
  role: "ADMIN" | "BRANCH" | "SUPPLIER" | string;
  // True while the account still has a starting/temporary password: the API then refuses everything
  // except changing it, and the router shows ForcedPasswordChange instead of the dashboard.
  must_change_password: boolean;
  branch_id: number | null;
  branch_name: string | null;
  supplier_id: number | null;
  supplier_name: string | null;
};

type AuthContextValue = {
  user: CurrentUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<string>; // returns redirect path
  logout: () => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  async function loadCurrentUser(): Promise<CurrentUser | null> {
    try {
      const me = await apiFetch("/auth/me");
      setUser(me);
      return me;
    } catch {
      setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const hasToken = !!localStorage.getItem("spar_access_token");
    if (hasToken) {
      loadCurrentUser();
    } else {
      setLoading(false);
    }
  }, []);

  async function login(username: string, password: string): Promise<string> {
    const data = await apiFetch("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setStoredTokens(data.access_token, data.refresh_token);
    const me = await loadCurrentUser();
    // One-shot flag so Supplier/BranchDashboard can show a welcome screen
    // right after a fresh login, but not on a page refresh —
    // sessionStorage survives the redirect but each dashboard clears it
    // once read.
    if (me?.role === "SUPPLIER" || me?.role === "BRANCH") {
      sessionStorage.setItem("spar_welcome_pending", "1");
    }
    return data.redirect_to as string;
  }

  async function logout() {
    try {
      // Send this session's refresh token so the server revokes it - otherwise it would stay usable for
      // days after "logging out". Other devices sharing the same branch/supplier login are unaffected.
      await apiFetch("/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: localStorage.getItem("spar_refresh_token") }),
      });
    } catch (e) {
      // Even if the call fails (e.g. token already expired), still clear locally.
    }
    clearStoredTokens();
    setUser(null);
  }

  // Changing the password revokes every older token (including this session's), so the API answers with a
  // fresh pair; store it and reload the user so must_change_password clears and the dashboard appears.
  async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
    const data = await apiFetch("/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
    setStoredTokens(data.access_token, data.refresh_token);
    await loadCurrentUser();
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, changePassword }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export { ApiError };
