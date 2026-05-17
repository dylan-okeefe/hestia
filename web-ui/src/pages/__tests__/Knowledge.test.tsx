import { render, screen, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import Knowledge from '../Knowledge';
import * as client from '../../api/client';

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
    fetchUserSessions: vi.fn(() => Promise.resolve({ sessions: [] })),
    fetchStyleProfile: vi.fn(() => Promise.resolve({ profile: {} })),
    fetchMemoriesForUser: vi.fn(() => Promise.resolve({ memories: [] })),
    fetchHandoffs: vi.fn(() =>
      Promise.resolve({
        handoffs: [
          {
            session_id: 'sess_1',
            summary: 'User asked about weather...',
            created_at: '2026-05-10T14:00:00Z',
          },
          {
            session_id: 'sess_2',
            summary: 'Discussed project planning',
            created_at: '2026-05-09T10:00:00Z',
          },
        ],
      })
    ),
    updateUser: vi.fn(() => Promise.resolve({})),
  };
});

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
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
  }),
}));

describe('Knowledge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders handoff summaries with formatted dates', async () => {
    render(<Knowledge />);

    await waitFor(() =>
      expect(screen.getByText('User asked about weather...')).toBeInTheDocument()
    );
    expect(screen.getByText('Discussed project planning')).toBeInTheDocument();

    // Verify fetchHandoffs was called with the session user id
    expect(client.fetchHandoffs).toHaveBeenCalledWith('user-1');
  });

  it('shows empty state when no handoffs exist', async () => {
    vi.mocked(client.fetchHandoffs).mockResolvedValue({ handoffs: [] });

    render(<Knowledge />);

    await waitFor(() =>
      expect(
        screen.getByText('No handoff summaries yet — these appear when Hestia carries context across sessions.')
      ).toBeInTheDocument()
    );
  });
});
