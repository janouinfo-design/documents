import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { authLogin, authLogout, authMe, clearFileToken, getToken, refreshFileToken, setToken } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined);

  useEffect(() => {
    if (!getToken()) {
      setUser(null);
      return;
    }
    authMe()
      .then(async (u) => {
        await refreshFileToken().catch(() => {});
        setUser(u);
      })
      .catch(() => {
        setToken(null);
        setUser(null);
      });
  }, []);

  useEffect(() => {
    if (!user) return undefined;
    const iv = setInterval(() => refreshFileToken().catch(() => {}), 8 * 60 * 1000);
    const onFocus = () => refreshFileToken().catch(() => {});
    window.addEventListener("focus", onFocus);
    return () => {
      clearInterval(iv);
      window.removeEventListener("focus", onFocus);
    };
  }, [user]);

  const login = useCallback(async (email, password) => {
    const data = await authLogin(email, password);
    setToken(data.token);
    await refreshFileToken().catch(() => {});
    setUser(data.user);
    return data.user;
  }, []);

  const logout = useCallback(() => {
    authLogout()
      .catch(() => {})
      .finally(() => {
        clearFileToken();
        setToken(null);
        setUser(null);
        window.location.assign("/login");
      });
  }, []);

  return <AuthContext.Provider value={{ user, login, logout }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
