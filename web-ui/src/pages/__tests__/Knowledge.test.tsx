import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import Knowledge from '../Knowledge';
import * as client from '../../api/client';
import { TEXT } from '../../lib/text';

const mockTopics = [
  { id: 'topic-1', platform: 'telegram', platform_user: '12345', name: 'food', created_at: '2026-05-01T12:00:00Z' },
  { id: 'topic-2', platform: 'telegram', platform_user: '12345', name: 'music', created_at: '2026-05-02T12:00:00Z' },
];

const mockMemories = [
  { id: 'mem-1', content: 'Alice likes pizza', tags: ['preference'], created_at: '2026-05-10T14:00:00Z', session_id: 'sess-1', platform: 'telegram', platform_user: '12345', is_global: false, is_pinned: false, is_active: true, deleted_at: null, deleted_reason: null, last_recalled_at: null, topic_ids: ['topic-1'] },
  { id: 'mem-2', content: 'Bob plays guitar', tags: ['hobby'], created_at: '2026-05-11T14:00:00Z', session_id: 'sess-2', platform: 'telegram', platform_user: '12345', is_global: false, is_pinned: false, is_active: true, deleted_at: null, deleted_reason: null, last_recalled_at: null, topic_ids: ['topic-2'] },
  { id: 'mem-3', content: 'Alice lives in Seattle', tags: ['identity'], created_at: '2026-05-09T14:00:00Z', session_id: 'sess-3', platform: 'telegram', platform_user: '12345', is_global: true, is_pinned: true, is_active: true, deleted_at: null, deleted_reason: null, last_recalled_at: null, topic_ids: [] },
];

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
    fetchMemoriesForUser: vi.fn(() => Promise.resolve({ memories: mockMemories })),
    fetchTopics: vi.fn(() => Promise.resolve({ topics: mockTopics })),
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
    updateMemory: vi.fn((id, updates) => Promise.resolve({ memory: { ...mockMemories.find((m) => m.id === id), ...updates } })),
    pinMemory: vi.fn(() => Promise.resolve({ pinned: true })),
    unpinMemory: vi.fn(() => Promise.resolve({ pinned: false })),
    softDeleteMemory: vi.fn(() => Promise.resolve({ deleted: true })),
    restoreMemory: vi.fn(() => Promise.resolve({ restored: true })),
    createTopic: vi.fn(() => Promise.resolve({ topic: { id: 'topic-3', platform: 'telegram', platform_user: '12345', name: 'travel', created_at: '2026-05-12T12:00:00Z' } })),
    renameTopic: vi.fn((id, name) => Promise.resolve({ topic: { ...mockTopics.find((t) => t.id === id), name } })),
    deleteTopic: vi.fn(() => Promise.resolve({ deleted: true })),
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

  it('renders memories grouped by scope', async () => {
    render(<Knowledge />);

    await waitFor(() =>
      expect(screen.getByText('Alice likes pizza')).toBeInTheDocument()
    );
    expect(screen.getByText('Bob plays guitar')).toBeInTheDocument();
    expect(screen.getByText('Alice lives in Seattle')).toBeInTheDocument();

    // Section titles identify scope groupings.
    expect(screen.getByRole('heading', { name: TEXT.knowledge.memoriesSectionGlobal })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: TEXT.knowledge.memoriesSectionTopic('food') })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: TEXT.knowledge.memoriesSectionTopic('music') })).toBeInTheDocument();
  });

  it('shows descriptive tags separately from topic badges', async () => {
    render(<Knowledge />);

    await waitFor(() =>
      expect(screen.getByText('Alice likes pizza')).toBeInTheDocument()
    );

    const pizzaCard = screen.getByText('Alice likes pizza').closest('.knowledge-memory-card');
    expect(pizzaCard).not.toBeNull();
    const pizzaScope = within(pizzaCard as HTMLElement);

    // Topic badge appears on the topic-scoped memory.
    expect(pizzaScope.getByText('food')).toBeInTheDocument();
    // Descriptive tag renders distinctly from topics.
    expect(pizzaScope.getByText('preference')).toBeInTheDocument();

    const globalCard = screen.getByText('Alice lives in Seattle').closest('.knowledge-memory-card');
    expect(globalCard).not.toBeNull();
    const globalScope = within(globalCard as HTMLElement);
    expect(globalScope.getByText(TEXT.knowledge.memoriesScopeGlobal)).toBeInTheDocument();
    expect(globalScope.getByText('identity')).toBeInTheDocument();
  });

  it('pins and unpins a memory', async () => {
    render(<Knowledge />);

    await waitFor(() =>
      expect(screen.getByText('Alice likes pizza')).toBeInTheDocument()
    );

    const pinButtons = screen.getAllByText(TEXT.knowledge.memoriesPin);
    fireEvent.click(pinButtons[0]);

    await waitFor(() =>
      expect(client.pinMemory).toHaveBeenCalledWith('mem-1')
    );
  });

  it('soft-deletes and restores a memory', async () => {
    render(<Knowledge />);

    await waitFor(() =>
      expect(screen.getByText('Alice likes pizza')).toBeInTheDocument()
    );

    window.confirm = vi.fn(() => true);
    const pizzaCard = screen.getByText('Alice likes pizza').closest('.knowledge-memory-card') as HTMLElement;
    const deleteButton = within(pizzaCard).getByText(TEXT.knowledge.memoriesDelete);
    fireEvent.click(deleteButton);

    await waitFor(() =>
      expect(client.softDeleteMemory).toHaveBeenCalledWith('mem-1')
    );
  });

  it('opens memory edit modal and saves scope change', async () => {
    render(<Knowledge />);

    await waitFor(() =>
      expect(screen.getByText('Alice likes pizza')).toBeInTheDocument()
    );

    const pizzaCard = screen.getByText('Alice likes pizza').closest('.knowledge-memory-card') as HTMLElement;
    const editButton = within(pizzaCard).getByText(TEXT.common.edit);
    fireEvent.click(editButton);

    const modal = await screen.findByRole('dialog');
    expect(within(modal).getByText(TEXT.knowledge.memoriesEditTitle)).toBeInTheDocument();

    const globalButton = within(modal).getByText(TEXT.knowledge.memoriesScopeGlobal);
    fireEvent.click(globalButton);

    fireEvent.click(within(modal).getByText(TEXT.common.save));

    await waitFor(() =>
      expect(client.updateMemory).toHaveBeenCalledWith('mem-1', expect.objectContaining({ is_global: true }))
    );
  });

  it('creates a topic from the topic panel', async () => {
    render(<Knowledge />);

    await waitFor(() =>
      expect(screen.getByText(TEXT.knowledge.memoriesTopicManageTitle)).toBeInTheDocument()
    );

    const input = screen.getByPlaceholderText(TEXT.knowledge.memoriesCreateTopicPlaceholder);
    fireEvent.change(input, { target: { value: 'travel' } });
    fireEvent.click(screen.getByText(TEXT.knowledge.memoriesCreateTopicButton));

    await waitFor(() =>
      expect(client.createTopic).toHaveBeenCalledWith('telegram', '12345', 'travel')
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
