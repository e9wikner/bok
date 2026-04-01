"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
} from "react";

export interface AuthUser {
  username: string;
}

export interface AuthContextType {
  user: AuthUser | null;
  token: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

export const AuthContext = createContext<AuthContextType>({
  user: null,
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
  const { user, loading } = useAuth();
  return { user, loading };
}

export function useAuthState(): AuthContextType {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Restore session from localStorage on mount
  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = localStorage.getItem("auth_token");
    if (stored) {
      fetchMe(stored)
        .then((fetchedUser) => {
          setUser(fetchedUser);
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

  const login = useCallback(async (username: string, password: string) => {
    const res = await fetch(`${API_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
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
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("auth_token");
    setToken(null);
    setUser(null);
    // Navigate to login (soft redirect)
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  }, []);

  return {
    user,
    token,
    loading,
    login,
    logout,
    isAuthenticated: !!user,
  };
}

async function fetchMe(token: string): Promise<AuthUser> {
  const res = await fetch(`${API_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Unauthorized");
  const data = await res.json();
  return { username: data.username };
}
