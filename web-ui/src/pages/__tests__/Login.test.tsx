import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import Login from '../Login';
import * as client from '../../api/client';

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client');
  return {
    ...actual,
    fetchAvailableUsers: vi.fn(() =>
      Promise.resolve({
        users: [
          {
            user_id: 'user-1',
            display_name: 'Alice',
            platforms: ['telegram'],
            identities: [{ platform: 'telegram', platform_user: '@alice:telegram' }],
          },
          {
            user_id: 'user-2',
            display_name: 'Bob',
            platforms: ['telegram', 'matrix'],
            identities: [
              { platform: 'telegram', platform_user: '@bob:telegram' },
              { platform: 'matrix', platform_user: '@bob:matrix' },
            ],
          },
        ],
      })
    ),
    requestCode: vi.fn(() => Promise.resolve({ status: 'sent', expires_in: 300 })),
    verifyCode: vi.fn(() => Promise.resolve({ token: 'test_token' })),
  };
});

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    auth: {
      authenticated: false,
      authEnabled: true,
      platform: null,
      platformUser: null,
      userId: null,
      availablePlatforms: [],
    },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
  }),
}));

describe('Login', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('passes correct platform_user when selecting second identity', async () => {
    render(<Login />);

    await waitFor(() => expect(screen.getByText('Bob')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Bob'));

    await waitFor(() =>
      expect(screen.getByText('Send code via telegram')).toBeInTheDocument()
    );

    fireEvent.click(screen.getByText('Send code via telegram'));

    await waitFor(() => {
      expect(client.requestCode).toHaveBeenCalledWith('telegram', '@bob:telegram');
    });
  });
});
