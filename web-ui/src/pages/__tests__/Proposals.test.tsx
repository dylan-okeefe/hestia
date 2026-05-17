import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import Proposals from '../Proposals';
import * as client from '../../api/client';

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client');
  return {
    ...actual,
    fetchProposals: vi.fn(() =>
      Promise.resolve({
        proposals: [
          {
            id: 'p1',
            type: 'action',
            summary: 'Approve deployment',
            confidence: 0.9,
            evidence: [],
            action: {},
            status: 'pending',
            created_at: '2024-01-01T12:00:00Z',
            expires_at: null,
          },
          {
            id: 'p2',
            type: 'action',
            summary: 'Restart server',
            confidence: 0.8,
            evidence: [],
            action: {},
            status: 'accepted',
            created_at: '2024-01-01T10:00:00Z',
            expires_at: null,
          },
        ],
      })
    ),
    acceptProposal: vi.fn(() => Promise.resolve({})),
    rejectProposal: vi.fn(() => Promise.resolve({})),
  };
});

describe('Proposals', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders pending tab with approve/reject buttons', async () => {
    render(<Proposals />);

    await waitFor(() => expect(screen.getByText('Approve deployment')).toBeInTheDocument());
    expect(screen.getByText('Approve')).toBeInTheDocument();
    expect(screen.getByText('Reject')).toBeInTheDocument();
  });

  it('switches to history tab and shows outcome badge', async () => {
    render(<Proposals />);

    await waitFor(() => expect(screen.getByText('Approve deployment')).toBeInTheDocument());
    fireEvent.click(screen.getByText('History'));

    await waitFor(() => expect(screen.getByText('accepted')).toBeInTheDocument());
  });

  it('shows empty state when no proposals', async () => {
    vi.mocked(client.fetchProposals).mockResolvedValueOnce({ proposals: [] });
    render(<Proposals />);

    await waitFor(() =>
      expect(screen.getByText('No pending proposals')).toBeInTheDocument()
    );
  });
});
