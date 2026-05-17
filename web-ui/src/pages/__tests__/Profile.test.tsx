import { render, screen, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import Profile from '../Profile';
import * as client from '../../api/client';

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client');
  return {
    ...actual,
    fetchUser: vi.fn(() =>
      Promise.resolve({
        id: 'user-2',
        display_name: 'Dylan',
        role: 'admin',
        trust_preset: 'household',
        notes: 'Test notes',
        created_at: '2024-01-01T12:00:00Z',
        identities: [{ platform: 'telegram', platform_user: '12345', verified: true }],
      })
    ),
    fetchRooms: vi.fn(() => Promise.resolve({ rooms: [] })),
    updateUser: vi.fn(() => Promise.resolve({})),
    addIdentity: vi.fn(() => Promise.resolve({})),
    removeIdentity: vi.fn(() => Promise.resolve({})),
  };
});

vi.mock('../../context/AuthContext', () => ({
  useAuth: vi.fn(() => ({
    auth: {
      authenticated: true,
      authEnabled: true,
      platform: 'telegram',
      platformUser: '12345',
      userId: 'user-2',
      availablePlatforms: [],
    },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
  })),
}));

describe('Profile', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders user from session user_id instead of users list', async () => {
    render(<Profile />);

    await waitFor(() => expect(screen.getByText('Dylan')).toBeInTheDocument());
    expect(screen.getByText(/admin/i)).toBeInTheDocument();
    expect(client.fetchUser).toHaveBeenCalledWith('user-2');
  });

  it('shows re-login prompt when auth.userId is missing', async () => {
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

    render(<Profile />);

    await waitFor(() =>
      expect(screen.getByText('Not authenticated. Please log in again.')).toBeInTheDocument()
    );
  });
});
