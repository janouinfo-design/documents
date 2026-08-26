import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { authLogin, authLogout, authMe, clearFileToken, exchangeNavixy, getToken, refreshFileToken, setToken } from "@/lib/api";

const AuthContext = createContext(null);

// session_key Navixy conservé UNIQUEMENT en mémoire (jamais localStorage/sessionStorage/cookie)
let ssoSessionKey = null;

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined);
  const [ssoPending, setSsoPending] = useState(false);
  const [ssoError, setSsoError] = useState(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const key = params.get("session_key") || params.get("hash");
    if (key) {
      params.delete("session_key");
      params.delete("hash");
      const qs = params.toString();
      window.history.replaceState({}, document.title,
        window.location.pathname + (qs ? `?${qs}` : "") + window.location.hash);
      setSsoPending(true);
      exchangeNavixy(key)
        .then(async (data) => {
          ssoSessionKey = key;
          setToken(data.token);
          await refreshFileToken().catch(() => {});
          setSsoError(null);
          setUser(data.user);
        })
        .catch((err) => {
          setToken(null);
          setSsoError(String(err?.response?.data?.detail
            || "Session Navixy invalide — reconnectez-vous au hub LOGITRAK."));
          setUser(null);
        })
        .finally(() => setSsoPending(false));
      return;
    }
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

  const logout = useCallback(() => {
    ssoSessionKey = null;
    authLogout()
      .catch(() => {})
      .finally(() => {
        clearFileToken();
        setToken(null);
        setUser(null);
        window.location.assign("/login");
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

  // Heartbeat SSO : re-validation silencieuse de la session Navixy toutes les 10 min.
  // 401/403 (session hub expirée/invalidée) → déconnexion. Erreur réseau → on garde la session.
  useEffect(() => {
    if (!user || !ssoSessionKey) return undefined;
    const iv = setInterval(() => {
      exchangeNavixy(ssoSessionKey)
        .then((d) => setToken(d.token))
        .catch((err) => {
          const status = err?.response?.status;
          if (status === 401 || status === 403) logout();
        });
    }, 10 * 60 * 1000);
    return () => clearInterval(iv);
  }, [user, logout]);

  const login = useCallback(async (email, password) => {
    const data = await authLogin(email, password);
    setToken(data.token);
    await refreshFileToken().catch(() => {});
    setSsoError(null);
    setUser(data.user);
    return data.user;
  }, []);

  return (
    <AuthContext.Provider value={{ user, login, logout, ssoPending, ssoError }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
