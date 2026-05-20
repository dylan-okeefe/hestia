import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import SessionDetail from '../SessionDetail';
import * as client from '../../api/client';
import { TEXT } from '../../lib/text';

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client');
  return {
    ...actual,
    fetchSessionMessages: vi.fn(() =>
      Promise.resolve({
        session: {
          id: 's1',
          platform: 'cli',
          platform_user: 'u1',
          started_at: '2024-01-01T12:00:00Z',
        },
        turns: [
          {
            id: 't1',
            state: 'done',
            started_at: '2024-01-01T12:01:00Z',
            iterations: 1,
            error: null,
          },
          {
            id: 't2',
            state: 'failed',
            started_at: '2024-01-01T12:02:00Z',
            iterations: 3,
            error: 'Something went wrong',
          },
        ],
        messages: [
          { role: 'user', content: 'Hello', created_at: '2024-01-01T12:00:00Z' },
          { role: 'assistant', content: 'Hi there!', created_at: '2024-01-01T12:00:05Z' },
        ],
      })
    ),
  };
});

function renderWithParams(sessionId: string) {
  return render(
    <MemoryRouter initialEntries={[`/sessions/${sessionId}`]}>
      <Routes>
        <Route path="/sessions/:id" element={<SessionDetail />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('SessionDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders session metadata and turns', async () => {
    renderWithParams('s1');

    await waitFor(() =>
      expect(screen.getByText(TEXT.sessionDetail.metadataTitle)).toBeInTheDocument()
    );

    expect(screen.getByText('s1')).toBeInTheDocument();
    expect(screen.getByText('cli')).toBeInTheDocument();
    expect(screen.getByText('u1')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();

    expect(screen.getByText('done')).toBeInTheDocument();
    expect(screen.getByText('failed')).toBeInTheDocument();
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('shows back link to Knowledge', async () => {
    renderWithParams('s1');

    await waitFor(() =>
      expect(screen.getByText(TEXT.sessionDetail.backToKnowledge)).toBeInTheDocument()
    );
  });

  it('shows error state on fetch failure', async () => {
    vi.mocked(client.fetchSessionMessages).mockRejectedValue(new Error('Network error'));

    renderWithParams('s1');

    await waitFor(() =>
      expect(screen.getByText('Network error')).toBeInTheDocument()
    );
  });

  it('shows empty state when no turns', async () => {
    vi.mocked(client.fetchSessionMessages).mockResolvedValue({
      session: {
        id: 's2',
        platform: 'matrix',
        platform_user: 'u2',
        started_at: '2024-01-01T12:00:00Z',
      },
      turns: [],
      messages: [],
    });

    renderWithParams('s2');

    await waitFor(() =>
      expect(screen.getAllByText(TEXT.sessionDetail.emptyTitle).length).toBeGreaterThanOrEqual(1)
    );
  });
});
