import React, { createContext, useContext, useMemo, useState } from "react";
import { api } from "./api";

type User = {
  id: string;
  email: string;
  name: string;
  role: string;
  is_active: boolean;
};

type AuthState = {
  token: string | null;
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

const TOKEN_KEY = "ai_admin_access";
const REFRESH_KEY = "ai_admin_refresh";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState<User | null>(null);

  React.useEffect(() => {
    if (!token) {
      setUser(null);
      return;
    }
    api<User>("/api/auth/me", {}, token)
      .then((u) => {
        if (u.role !== "admin") {
          localStorage.removeItem(TOKEN_KEY);
          localStorage.removeItem(REFRESH_KEY);
          setToken(null);
          setUser(null);
          return;
        }
        setUser(u);
      })
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
        setUser(null);
      });
  }, [token]);

  const value = useMemo<AuthState>(
    () => ({
      token,
      user,
      async login(email, password) {
        const pair = await api<{ access_token: string; refresh_token: string }>("/api/auth/login", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        localStorage.setItem(TOKEN_KEY, pair.access_token);
        localStorage.setItem(REFRESH_KEY, pair.refresh_token);
        setToken(pair.access_token);
      },
      logout() {
        const refresh = localStorage.getItem(REFRESH_KEY);
        if (refresh) {
          void api("/api/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: refresh }) });
        }
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(REFRESH_KEY);
        setToken(null);
        setUser(null);
      },
    }),
    [token, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside provider");
  return ctx;
}
