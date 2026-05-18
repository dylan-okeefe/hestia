import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import Knowledge from '../Knowledge';
import * as client from '../../api/client';
import { TEXT } from '../../lib/text';

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
        notes: 'Some notes',
        created_at: '2024-01-01T12:00:00Z',
        identities: [{ platform: 'telegram', platform_user: '12345', verified: true }],
      })
    ),
    fetchUserSessions: vi.fn(() => Promise.resolve({ sessions: [] })),
    fetchStyleProfile: vi.fn(() => Promise.resolve({ profile: {} })),
    fetchMemoriesForUser: vi.fn(() => Promise.resolve({
      memories: [
        { id: 'mem-1', content: 'Alice likes pizza', tags: ['food'], created_at: '2026-05-10T14:00:00Z' },
        { id: 'mem-2', content: 'Bob plays guitar', tags: ['music'], created_at: '2026-05-11T14:00:00Z' },
      ],
    })),
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
    deleteMemory: vi.fn(() => Promise.resolve({ deleted: true })),
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

    expect(client.fetchHandoffs).toHaveBeenCalledWith('user-1');
  });

  it('shows empty state when no handoffs exist', async () => {
    vi.mocked(client.fetchHandoffs).mockResolvedValue({ handoffs: [] });

    render(<Knowledge />);

    await waitFor(() =>
      expect(
        screen.getByText(TEXT.knowledge.handoffsEmptyTitle)
      ).toBeInTheDocument()
    );
  });

  it('renders memories and allows deletion', async () => {
    render(<Knowledge />);

    await waitFor(() =>
      expect(screen.getByText('Alice likes pizza')).toBeInTheDocument()
    );

    window.confirm = vi.fn(() => true);
    const deleteButtons = screen.getAllByText(TEXT.common.delete);
    fireEvent.click(deleteButtons[0]);

    await waitFor(() =>
      expect(client.deleteMemory).toHaveBeenCalledWith('mem-1')
    );
  });

  it('shows user notes as read-only with link to profile', async () => {
    render(<Knowledge />);

    await waitFor(() =>
      expect(screen.getByText('Some notes')).toBeInTheDocument()
    );
    expect(screen.getByText(TEXT.knowledge.editNotesLink)).toBeInTheDocument();
  });

  it('shows empty state for style profile when no metrics', async () => {
    render(<Knowledge />);

    await waitFor(() =>
      expect(screen.getByText(TEXT.knowledge.styleEmptyTitle)).toBeInTheDocument()
    );
  });

  it('filters memories by tag clicks', async () => {
    render(<Knowledge />);

    await waitFor(() =>
      expect(screen.getByText('Alice likes pizza')).toBeInTheDocument()
    );
    expect(screen.getByText('Bob plays guitar')).toBeInTheDocument();

    const foodButton = screen.getAllByText('food').find((el) => el.tagName === 'BUTTON');
    expect(foodButton).toBeDefined();
    fireEvent.click(foodButton!);

    await waitFor(() =>
      expect(screen.queryByText('Bob plays guitar')).not.toBeInTheDocument()
    );
    expect(screen.getByText('Alice likes pizza')).toBeInTheDocument();

    fireEvent.click(screen.getByText(TEXT.knowledge.tagFilterClear));

    await waitFor(() =>
      expect(screen.getByText('Bob plays guitar')).toBeInTheDocument()
    );
  });

  it('renders clickable session rows linking to session detail', async () => {
    vi.mocked(client.fetchUserSessions).mockResolvedValue({
      sessions: [
        {
          id: 'cli_alice_20240101120000_abc12345',
          platform: 'cli',
          platform_user: 'alice',
          started_at: '2024-01-01T12:00:00Z',
          message_count: 5,
        },
      ],
    });

    render(<Knowledge />);

    await waitFor(() =>
      expect(screen.getByText('cli')).toBeInTheDocument()
    );

    const link = screen.getByText('cli_alic…');
    expect(link.closest('a')).toHaveAttribute('href', '/sessions/cli_alice_20240101120000_abc12345');
  });
});
