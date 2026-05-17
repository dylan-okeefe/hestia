import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import Dashboard from '../Dashboard';

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
    fetchDashboard: vi.fn(() =>
      Promise.resolve({
        active_workflow_count: 3,
        recent_executions: [],
        pending_proposal_count: 2,
        platforms_connected: ['telegram'],
      })
    ),
    fetchSchedulerTasks: vi.fn(() => Promise.resolve({ tasks: [{ id: 't1' }] })),
    fetchUser: vi.fn(() =>
      Promise.resolve({
        id: 'user-1',
        display_name: 'Alice',
        role: 'user',
        trust_preset: 'household',
        notes: null,
        created_at: '2024-01-01T12:00:00Z',
        identities: [{ platform: 'telegram', platform_user: '12345', verified: true }],
      })
    ),
  };
});

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => authState.value,
}));

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows greeting with display name', async () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText(/Alice/)).toBeInTheDocument());
    expect(screen.getByText(/Good/i)).toBeInTheDocument();
  });

  it('renders stats cards', async () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText('3')).toBeInTheDocument());
    expect(screen.getByText('Active Workflows')).toBeInTheDocument();
    expect(screen.getByText('Scheduled Tasks')).toBeInTheDocument();
    expect(screen.getByText('Pending Proposals')).toBeInTheDocument();
  });

  it('shows quick action buttons', async () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText('Go to Workflows')).toBeInTheDocument());
    expect(screen.getByText('View Profile')).toBeInTheDocument();
    expect(screen.getByText('Run Health Check')).toBeInTheDocument();
  });
});
