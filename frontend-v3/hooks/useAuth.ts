"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  ReactNode,
} from "react";

export interface AuthUser {
  id: string;
  email: string;
  full_name?: string;
}

export interface AuthTenant {
  id: string;
  role: string;
  name?: string;
  org_number?: string;
}

export interface AuthContextType {
  user: AuthUser | null;
  tenants: AuthTenant[];
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

export const AuthContext = createContext<AuthContextType>({
  user: null,
  tenants: [],
  token: null,
  loading: true,
  login: async () => {},
  logout: () => {},
  isAuthenticated: false,
});

export function useAuth() {
  return useContext(AuthContext);
}

export function useMe() {
  const { user, tenants, loading } = useAuth();
  return { user, tenants, loading };
}

export function useAuthState(): AuthContextType {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [tenants, setTenants] = useState<AuthTenant[]>([]);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Restore session from localStorage on mount
  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = localStorage.getItem("auth_token");
    if (stored) {
      fetchMe(stored)
        .then(({ user, tenants }) => {
          setUser(user);
          setTenants(tenants);
          setToken(stored);
        })
        .catch(() => {
          localStorage.removeItem("auth_token");
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch(`${API_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Inloggning misslyckades");
    }
    const data = await res.json();
    const newToken: string = data.access_token;
    localStorage.setItem("auth_token", newToken);
    setToken(newToken);
    setUser(data.user);
    setTenants(data.tenants ?? []);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("auth_token");
    setToken(null);
    setUser(null);
    setTenants([]);
    // Navigate to login (soft redirect)
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  }, []);

  return {
    user,
    tenants,
    token,
    loading,
    login,
    logout,
    isAuthenticated: !!user,
  };
}

async function fetchMe(
  token: string
): Promise<{ user: AuthUser; tenants: AuthTenant[] }> {
  const res = await fetch(`${API_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Unauthorized");
  const data = await res.json();
  return {
    user: { id: data.id, email: data.email, full_name: data.full_name },
    tenants: data.tenants ?? [],
  };
}

// Register helper (used on register page, no hook needed)
export async function registerUser(
  email: string,
  password: string,
  fullName?: string
): Promise<void> {
  const res = await fetch(`${API_URL}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: fullName }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Registrering misslyckades");
  }
}
