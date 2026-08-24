import { createContext, useContext, useState, useEffect, useCallback, type ReactNode , useRef } from 'react';
import { fetchAuthStatus, setAuthToken, clearAuthToken, logout as clientLogout } from '../api/client';

interface AuthState {
  authenticated: boolean;
  authEnabled: boolean;
  debugLogin: boolean;
  platform: string | null;
  platformUser: string | null;
  userId: string | null;
  availablePlatforms: string[];
}

interface AuthContextValue {
  auth: AuthState;
  loading: boolean;
  login: (token: string) => void;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<AuthState>({
    authenticated: false,
    authEnabled: true,
    debugLogin: false,
    platform: null,
    platformUser: null,
    userId: null,
    availablePlatforms: [],
  });
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchAuthStatus();
      if (!data.auth_enabled) {
        setAuth({
          authenticated: true,
          authEnabled: false,
          debugLogin: false,
          platform: null,
          platformUser: null,
          userId: null,
          availablePlatforms: [],
        });
        return;
      }
      if (!data.authenticated) {
        clientLogout().catch(() => {});
        clearAuthToken();
        setAuth({
          authenticated: false,
          authEnabled: true,
          debugLogin: data.debug_login || false,
          platform: null,
          platformUser: null,
          userId: null,
          availablePlatforms: data.available_platforms || [],
        });
        return;
      }
      setAuth({
        authenticated: true,
        authEnabled: true,
        debugLogin: data.debug_login || false,
        platform: data.platform || null,
        platformUser: data.platform_user || null,
        userId: data.user_id || null,
        availablePlatforms: data.available_platforms || [],
      });
    } catch {
      // BUG-055: a failed status check after retries must not log the user
      // out. Preserve current state; the token remains valid or the next
      // real API call will surface a definitive 401.
    }
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  const login = useCallback((token: string) => {
    setAuthToken(token);
    refresh();
  }, [refresh]);

  const authRef = useRef(auth);
  useEffect(() => {
    authRef.current = auth;
  }, [auth]);

  const logout = useCallback(() => {
    clientLogout().catch(() => {});
    clearAuthToken();
    // BUG-086: read through a ref so this callback never sees stale state.
    setAuth({
      authenticated: false,
      authEnabled: true,
      debugLogin: authRef.current.debugLogin,
      platform: null,
      platformUser: null,
      userId: null,
      availablePlatforms: authRef.current.availablePlatforms,
    });
  }, []);

  useEffect(() => {
    const handler = () => logout();
    window.addEventListener('auth:unauthorized', handler);
    return () => window.removeEventListener('auth:unauthorized', handler);
  }, [logout]);

  return (
    <AuthContext.Provider value={{ auth, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}
