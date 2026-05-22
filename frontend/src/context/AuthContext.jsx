// eslint-disable-next-line react-refresh/only-export-components
import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { authApi, tokenStore } from '../services/auth';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser]     = useState(null);   // { profile, stats }
  const [loading, setLoading] = useState(true);  // initial token check

  // On mount: validate stored token
  useEffect(() => {
    if (!tokenStore.get()) { setLoading(false); return; }
    authApi.me()
      .then(data => setUser(data))
      .catch(() => { tokenStore.clear(); })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email, password) => {
    const tokens = await authApi.login(email, password);
    tokenStore.set(tokens.access_token);
    tokenStore.setRefresh(tokens.refresh_token);
    const me = await authApi.me();
    setUser(me);
    return me;
  }, []);

  const register = useCallback(async (email, username, password, full_name) => {
    const tokens = await authApi.register(email, username, password, full_name);
    tokenStore.set(tokens.access_token);
    tokenStore.setRefresh(tokens.refresh_token);
    const me = await authApi.me();
    setUser(me);
    return me;
  }, []);

  const logout = useCallback(async () => {
    try {
      const refresh = tokenStore.getRefresh();
      if (refresh) await authApi.logout(refresh);
    } catch { /* ignore — clear tokens regardless */ }
    tokenStore.clear();
    setUser(null);
  }, []);

  const refreshUser = useCallback(async () => {
    const me = await authApi.me();
    setUser(me);
    return me;
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
};
