import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import StyleProfile from '../StyleProfile';
import * as client from '../../api/client';
import { TEXT } from '../../lib/text';

const authState = vi.hoisted(() => ({
  value: {
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
  },
}));

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client');
  return {
    ...actual,
    fetchUser: vi.fn(() =>
      Promise.resolve({
        id: 'user-1',
        display_name: 'Alice',
        role: 'user',
        trust_preset: 'household',
        notes: null,
        created_at: '2024-01-01T12:00:00Z',
        identities: [
          { platform: 'telegram', platform_user: '@alice:telegram', verified: true },
          { platform: 'matrix', platform_user: '@alice:matrix', verified: true },
        ],
      })
    ),
    fetchStyleProfile: vi.fn(() => Promise.resolve({ profile: { formality: 0.8, preferred_length: 'short' } })),
    deleteStyleMetric: vi.fn(() => Promise.resolve({ ok: true })),
  };
});

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => authState.value,
}));

describe('StyleProfile', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('auto-populates platform and user from first identity', async () => {
    render(<StyleProfile />);

    await waitFor(() => expect(screen.getByText('telegram')).toBeInTheDocument());
    expect(screen.getByText('@alice:telegram')).toBeInTheDocument();
  });

  it('shows identity switcher when multiple identities exist', async () => {
    render(<StyleProfile />);

    await waitFor(() => expect(screen.getByText('telegram')).toBeInTheDocument());
    const select = screen.getByRole('combobox');
    expect(select).toBeInTheDocument();

    fireEvent.change(select, { target: { value: '1' } });
    await waitFor(() => expect(screen.getByText('matrix')).toBeInTheDocument());
  });

  it('renders metric cards', async () => {
    render(<StyleProfile />);

    await waitFor(() => expect(screen.getByText('0.8')).toBeInTheDocument());
    expect(screen.getByText('short')).toBeInTheDocument();
  });

  it('shows empty state when no metrics', async () => {
    vi.mocked(client.fetchStyleProfile).mockResolvedValueOnce({ profile: {} });
    render(<StyleProfile />);

    await waitFor(() =>
      expect(
        screen.getByText(TEXT.styleProfile.emptyDescription)
      ).toBeInTheDocument()
    );
  });
});
