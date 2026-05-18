import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import AdminUsers from '../AdminUsers';
import * as client from '../../api/client';
import * as useCurrentUser from '../../hooks/useCurrentUser';

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client');
  return {
    ...actual,
    fetchUsers: vi.fn(),
    createUser: vi.fn(),
    updateUser: vi.fn(),
    deleteUser: vi.fn(),
    addIdentity: vi.fn(),
  };
});

vi.mock('../../hooks/useCurrentUser', () => ({
  useCurrentUser: vi.fn(),
}));

const mockAdminUser = {
  user: { id: 'u1', display_name: 'Admin', role: 'admin', trust_preset: 'developer', notes: null, created_at: '2024-01-01T00:00:00Z', identities: [] },
  isLoading: false,
  error: null,
  refetch: vi.fn(),
};

const mockNonAdminUser = {
  user: { id: 'u2', display_name: 'User', role: 'user', trust_preset: 'household', notes: null, created_at: '2024-01-01T00:00:00Z', identities: [] },
  isLoading: false,
  error: null,
  refetch: vi.fn(),
};

describe('AdminUsers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useCurrentUser.useCurrentUser).mockReturnValue(mockAdminUser as any);
    vi.mocked(client.fetchUsers).mockResolvedValue({
      users: [
        { id: 'u1', display_name: 'Alice', role: 'admin', trust_preset: 'developer', notes: 'Admin user', created_at: '2024-01-01T00:00:00Z', identity_count: 2, room_count: 1 },
        { id: 'u2', display_name: 'Bob', role: 'user', trust_preset: 'household', notes: null, created_at: '2024-02-01T00:00:00Z', identity_count: 1, room_count: 0 },
      ],
    });
  });

  it('shows access denied for non-admin', async () => {
    vi.mocked(useCurrentUser.useCurrentUser).mockReturnValue(mockNonAdminUser as any);
    render(<AdminUsers />);
    await waitFor(() => expect(screen.getByText('Administrator access required')).toBeInTheDocument());
  });

  it('renders user list with role badges', async () => {
    render(<AdminUsers />);
    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument());
    expect(screen.getByText('Bob')).toBeInTheDocument();
    expect(screen.getAllByText('Administrator').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('User').length).toBeGreaterThanOrEqual(1);
    // identity count and room count cells
    const cells = screen.getAllByText('2');
    expect(cells.length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('1').length).toBeGreaterThanOrEqual(1);
  });

  it('filters by role', async () => {
    render(<AdminUsers />);
    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'User' }));
    await waitFor(() => expect(screen.queryByText('Alice')).not.toBeInTheDocument());
    expect(screen.getByText('Bob')).toBeInTheDocument();
  });

  it('opens create modal and submits', async () => {
    vi.mocked(client.createUser).mockResolvedValue({ id: 'u3', display_name: 'Charlie', role: 'user', trust_preset: 'household', notes: null, created_at: '2024-03-01T00:00:00Z' });
    render(<AdminUsers />);
    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument());
    fireEvent.click(screen.getByText('+ New User'));

    await waitFor(() => expect(screen.getByText('New User')).toBeInTheDocument());
    const nameInput = screen.getByPlaceholderText('Jane Doe');
    fireEvent.change(nameInput, { target: { value: 'Charlie' } });
    fireEvent.click(screen.getByText('Create'));

    await waitFor(() => expect(client.createUser).toHaveBeenCalled());
  });

  it('opens edit modal and saves', async () => {
    vi.mocked(client.updateUser).mockResolvedValue({ id: 'u1', display_name: 'Alice Updated', role: 'admin', trust_preset: 'developer', notes: 'Admin user' });
    render(<AdminUsers />);
    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText('Edit')[0]);

    await waitFor(() => expect(screen.getByText('Edit User')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => expect(client.updateUser).toHaveBeenCalled());
  });

  it('deletes user with confirmation', async () => {
    vi.mocked(client.deleteUser).mockResolvedValue({ deleted: true });
    render(<AdminUsers />);
    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText('Delete')[0]);

    await waitFor(() => expect(screen.getByText('Delete user?')).toBeInTheDocument());
    const deleteButtons = screen.getAllByText('Delete');
    fireEvent.click(deleteButtons[deleteButtons.length - 1]);

    await waitFor(() => expect(client.deleteUser).toHaveBeenCalledWith('u1'));
  });

  it('shows empty state when no users', async () => {
    vi.mocked(client.fetchUsers).mockResolvedValue({ users: [] });
    render(<AdminUsers />);
    await waitFor(() => expect(screen.getByText('No users found')).toBeInTheDocument());
  });
});
