import { renderHook, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { useCurrentUser } from '../useCurrentUser';

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client');
  return {
    ...actual,
    fetchUser: vi.fn(() =>
      Promise.resolve({
        id: 'user-1',
        display_name: 'Alice',
        role: 'user',
        trust_preset: null,
        notes: '',
        created_at: '2024-01-01T12:00:00Z',
        identities: [{ platform: 'telegram', platform_user: '12345', verified: true }],
      })
    ),
  };
});

vi.mock('../../context/AuthContext', () => ({
  useAuth: vi.fn(() => ({
    auth: {
      authenticated: true,
      authEnabled: true,
      platform: 'telegram',
      platformUser: '12345',
      userId: 'user-1',
      availablePlatforms: [],
    },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
  })),
}));

describe('useCurrentUser', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns user data after loading', async () => {
    const { result } = renderHook(() => useCurrentUser());

    expect(result.current.isLoading).toBe(true);
    expect(result.current.user).toBeNull();

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.user).toEqual({
      id: 'user-1',
      display_name: 'Alice',
      role: 'user',
      trust_preset: null,
      notes: '',
      created_at: '2024-01-01T12:00:00Z',
      identities: [{ platform: 'telegram', platform_user: '12345', verified: true }],
    });
    expect(result.current.error).toBeNull();
  });

  it('returns error when auth.userId is missing', async () => {
    const { useAuth } = await import('../../context/AuthContext');
    vi.mocked(useAuth).mockReturnValue({
      auth: {
        authenticated: true,
        authEnabled: true,
        platform: 'telegram',
        platformUser: '12345',
        userId: null,
        availablePlatforms: [],
      },
      loading: false,
      login: vi.fn(),
      logout: vi.fn(),
      refresh: vi.fn(),
    });

    const { result } = renderHook(() => useCurrentUser());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.user).toBeNull();
    expect(result.current.error).toBe('Not authenticated. Please log in again.');
  });
});
