import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { apiFetch, setStoredTokens, clearStoredTokens, ApiError } from "../../api/client";

export type CurrentUser = {
  id: number;
  username: string;
  role: "ADMIN" | "BRANCH" | "SUPPLIER" | string;
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
      await apiFetch("/auth/logout", { method: "POST" });
    } catch (e) {
      // Even if the call fails (e.g. token already expired), still clear locally.
    }
    clearStoredTokens();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export { ApiError };
