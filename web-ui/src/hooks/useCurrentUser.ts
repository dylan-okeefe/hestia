import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { fetchUser } from '../api/client';

interface Identity {
  platform: string;
  platform_user: string;
  verified: boolean;
}

export interface UserDetail {
  id: string;
  display_name: string;
  role: string;
  trust_preset: string | null;
  notes: string | null;
  created_at: string;
  identities: Identity[];
}

export function useCurrentUser() {
  const { auth } = useAuth();
  const [user, setUser] = useState<UserDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const userId = auth.userId;
      if (!userId) {
        setError('Not authenticated. Please log in again.');
        setUser(null);
        return;
      }
      const detail = await fetchUser(userId);
      setUser(detail);
    } catch (err: any) {
      setError(err.message);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, [auth.userId]);

  useEffect(() => {
    load();
  }, [load]);

  const refetch = useCallback(() => {
    load();
  }, [load]);

  return { user, isLoading, error, refetch };
}
