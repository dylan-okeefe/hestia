import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { fetchAuthStatus, setAuthToken, clearAuthToken } from '../api/client';

interface AuthState {
  authenticated: boolean;
  authEnabled: boolean;
  platform: string | null;
  platformUser: string | null;
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
    platform: null,
    platformUser: null,
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
          platform: null,
          platformUser: null,
          availablePlatforms: [],
        });
        return;
      }
      setAuth({
        authenticated: data.authenticated,
        authEnabled: true,
        platform: data.platform || null,
        platformUser: data.platform_user || null,
        availablePlatforms: data.available_platforms || [],
      });
    } catch {
      setAuth({
        authenticated: false,
        authEnabled: true,
        platform: null,
        platformUser: null,
        availablePlatforms: [],
      });
    }
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  const login = useCallback((token: string) => {
    setAuthToken(token);
    refresh();
  }, [refresh]);

  const logout = useCallback(() => {
    clearAuthToken();
    setAuth({
      authenticated: false,
      authEnabled: true,
      platform: null,
      platformUser: null,
      availablePlatforms: auth.availablePlatforms,
    });
  }, [auth.availablePlatforms]);

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
