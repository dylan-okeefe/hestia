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
            role: 'user',
            platforms: ['telegram'],
            identities: [{ platform: 'telegram', platform_user: '@alice:telegram' }],
          },
          {
            user_id: 'user-2',
            display_name: 'Bob',
            role: 'admin',
            platforms: ['telegram', 'matrix'],
            identities: [
              { platform: 'telegram', platform_user: '@bob:telegram' },
              { platform: 'matrix', platform_user: '@bob:matrix' },
            ],
          },
          {
            user_id: 'user-3',
            display_name: '!room-id',
            role: 'user',
            platforms: ['matrix'],
            identities: [{ platform: 'matrix', platform_user: '@room:matrix' }],
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

  it('filters out users with display_name starting with !', async () => {
    render(<Login />);

    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument());
    expect(screen.getByText('Bob')).toBeInTheDocument();
    expect(screen.queryByText('!room-id')).not.toBeInTheDocument();
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

  it('shows step 3 after requesting code and allows verify', async () => {
    render(<Login />);

    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Alice'));

    await waitFor(() =>
      expect(screen.getByText('Send code via telegram')).toBeInTheDocument()
    );

    fireEvent.click(screen.getByText('Send code via telegram'));

    await waitFor(() => {
      expect(screen.getByPlaceholderText('000000')).toBeInTheDocument();
    });

    const codeInput = screen.getByPlaceholderText('000000');
    fireEvent.change(codeInput, { target: { value: '123456' } });
    fireEvent.click(screen.getByText('Verify'));

    await waitFor(() => {
      expect(client.verifyCode).toHaveBeenCalledWith('123456');
    });
  });

  it('shows back button on step 2 and returns to step 1', async () => {
    render(<Login />);

    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Alice'));

    await waitFor(() =>
      expect(screen.getByText('Send code via telegram')).toBeInTheDocument()
    );

    fireEvent.click(screen.getByText('← Back to user selection'));

    await waitFor(() =>
      expect(screen.getByText('Alice')).toBeInTheDocument()
    );
  });
});
