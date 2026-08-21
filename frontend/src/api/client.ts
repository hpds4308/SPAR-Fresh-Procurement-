const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const API_V1 = `${API_BASE}/api/v1`;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function getStoredTokens() {
  return {
    access: localStorage.getItem("spar_access_token"),
    refresh: localStorage.getItem("spar_refresh_token"),
  };
}

export function setStoredTokens(access: string, refresh: string) {
  localStorage.setItem("spar_access_token", access);
  localStorage.setItem("spar_refresh_token", refresh);
}

export function clearStoredTokens() {
  localStorage.removeItem("spar_access_token");
  localStorage.removeItem("spar_refresh_token");
}

async function tryRefresh(): Promise<string | null> {
  const { refresh } = getStoredTokens();
  if (!refresh) return null;
  const res = await fetch(`${API_V1}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!res.ok) return null;
  const data = await res.json();
  setStoredTokens(data.access_token, data.refresh_token);
  return data.access_token as string;
}

export async function apiFetch(path: string, options: RequestInit = {}, retry = true): Promise<any> {
  const { access } = getStoredTokens();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (access) headers["Authorization"] = `Bearer ${access}`;

  let res: Response;
  try {
    res = await fetch(`${API_V1}${path}`, { ...options, headers });
  } catch (err) {
    // The request never got a response at all — network down, DNS/host
    // unreachable, CORS rejected it outright, mixed content blocked, etc.
    // Surface the browser's own message instead of a generic fallback so
    // this is diagnosable from the UI alone.
    const reason = err instanceof Error ? err.message : String(err);
    console.error(`apiFetch: network error calling ${path}:`, err);
    throw new ApiError(0, `Network error reaching the server (${reason}). Check your connection and that the API is reachable.`);
  }

  if (res.status === 401 && retry) {
    const newAccess = await tryRefresh();
    if (newAccess) {
      return apiFetch(path, options, false);
    }
    clearStoredTokens();
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: `Request failed with status ${res.status}.` }));
    throw new ApiError(res.status, body.detail ?? `Request failed with status ${res.status}.`);
  }

  if (res.status === 204) return null;

  try {
    return await res.json();
  } catch (err) {
    console.error(`apiFetch: could not parse JSON response from ${path}:`, err);
    throw new ApiError(res.status, "The server's response could not be read. Please try again.");
  }
}
