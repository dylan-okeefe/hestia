import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import Profile from '../Profile';
import * as client from '../../api/client';

interface AuthMockValue {
  auth: {
    authenticated: boolean;
    authEnabled: boolean;
    platform: string | null;
    platformUser: string | null;
    userId: string | null;
    availablePlatforms: string[];
  };
  loading: boolean;
  login: ReturnType<typeof vi.fn>;
  logout: ReturnType<typeof vi.fn>;
  refresh: ReturnType<typeof vi.fn>;
}

const authState = vi.hoisted(() => ({
  value: {
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
  } as AuthMockValue,
}));

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
    fetchConfig: vi.fn(() => Promise.resolve({ trust: { preset: 'developer' } })),
  };
});

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => authState.value,
}));

describe('Profile', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.value = {
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
    };
  });

  it('renders user from session user_id instead of users list', async () => {
    render(<Profile />);

    await waitFor(() => expect(screen.getByText('Dylan')).toBeInTheDocument());
    expect(screen.getByText(/administrator/i)).toBeInTheDocument();
    expect(client.fetchUser).toHaveBeenCalledWith('user-2');
  });

  it('shows re-login prompt when auth.userId is missing', async () => {
    authState.value = {
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
    };

    render(<Profile />);

    await waitFor(() =>
      expect(screen.getByText('Not authenticated. Please log in again.')).toBeInTheDocument()
    );
  });

  it('shows empty state for rooms when no rooms exist', async () => {
    render(<Profile />);
    await waitFor(() => expect(screen.getByText('Dylan')).toBeInTheDocument());
    expect(screen.getByText('No rooms yet')).toBeInTheDocument();
    expect(screen.getByText(/Telegram and Matrix group chats are registered automatically/i)).toBeInTheDocument();
  });

  it('fires updateUser when saving display name', async () => {
    render(<Profile />);
    await waitFor(() => expect(screen.getByText('Dylan')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Edit name'));
    const nameInput = screen.getByDisplayValue('Dylan');
    fireEvent.change(nameInput, { target: { value: 'Dylan Updated' } });
    fireEvent.click(screen.getByText('Save'));

    await waitFor(() =>
      expect(client.updateUser).toHaveBeenCalledWith('user-2', { display_name: 'Dylan Updated' })
    );
  });

  it('fires updateUser when saving notes', async () => {
    render(<Profile />);
    await waitFor(() => expect(screen.getByText('Dylan')).toBeInTheDocument());

    const notesInput = screen.getByDisplayValue('Test notes');
    fireEvent.change(notesInput, { target: { value: 'Updated notes' } });
    fireEvent.click(screen.getByText('Save Notes'));

    await waitFor(() =>
      expect(client.updateUser).toHaveBeenCalledWith('user-2', { notes: 'Updated notes' })
    );
  });

  it('shows personal trust override label and effective badge', async () => {
    render(<Profile />);
    await waitFor(() => expect(screen.getByText('Dylan')).toBeInTheDocument());

    expect(screen.getByText(/Personal trust override/i)).toBeInTheDocument();
    expect(screen.getByText(/Effective:/i)).toBeInTheDocument();
    expect(screen.getByText(/Overrides the global trust level/i)).toBeInTheDocument();
  });

  it('surfaces errors instead of swallowing', async () => {
    vi.mocked(client.updateUser).mockRejectedValueOnce(new Error('Save failed'));
    render(<Profile />);
    await waitFor(() => expect(screen.getByText('Dylan')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Edit name'));
    const nameInput = screen.getByDisplayValue('Dylan');
    fireEvent.change(nameInput, { target: { value: 'Dylan Updated' } });
    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => expect(screen.getByText('Save failed')).toBeInTheDocument());
  });
});
