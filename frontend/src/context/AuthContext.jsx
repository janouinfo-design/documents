import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { authLogin, authMe, getToken, setToken } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined);

  useEffect(() => {
    if (!getToken()) {
      setUser(null);
      return;
    }
    authMe()
      .then(setUser)
      .catch(() => {
        setToken(null);
        setUser(null);
      });
  }, []);

  const login = useCallback(async (email, password) => {
    const data = await authLogin(email, password);
    setToken(data.token);
    setUser(data.user);
    return data.user;
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    window.location.assign("/login");
  }, []);

  return <AuthContext.Provider value={{ user, login, logout }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
