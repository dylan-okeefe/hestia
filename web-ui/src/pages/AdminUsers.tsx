import { useState } from 'react';
import { useApiQuery, useApiMutation } from '../hooks/useApi';
import { useCurrentUser } from '../hooks/useCurrentUser';
import {
  fetchUsers,
  createUser,
  updateUser,
  deleteUser,
  addIdentity,
} from '../api/client';
import PageCard from '../components/layout/PageCard';
import LoadingSkeleton from '../components/layout/LoadingSkeleton';
import ErrorState from '../components/layout/ErrorState';
import EmptyState from '../components/layout/EmptyState';
import RoleDropdown from '../components/forms/RoleDropdown';
import TrustPresetDropdown from '../components/forms/TrustPresetDropdown';
import { label, ROLE_LABELS } from '../lib/labels';
import { formatDate } from '../lib/format';

interface User {
  id: string;
  display_name: string;
  role: string;
  trust_preset: string | null;
  notes: string | null;
  created_at: string;
  identity_count: number;
  room_count: number;
}

const ROLE_FILTERS = ['all', 'admin', 'trusted', 'user', 'child'];

export default function AdminUsers() {
  const { user: currentUser, isLoading: userLoading } = useCurrentUser();
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useApiQuery<{ users: User[] }>('users', fetchUsers);

  const users = data?.users ?? [];
  const [roleFilter, setRoleFilter] = useState('all');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [form, setForm] = useState({
    display_name: '',
    role: 'user',
    notes: '',
    trust_preset: 'household',
  });
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [showAddIdentity, setShowAddIdentity] = useState<string | null>(null);
  const [identityForm, setIdentityForm] = useState({ platform: 'telegram', platform_user: '' });

  const createMut = useApiMutation(createUser);
  const updateMut = useApiMutation((args: { id: string; payload: object }) => updateUser(args.id, args.payload));
  const deleteMut = useApiMutation(deleteUser);
  const addIdentityMut = useApiMutation((args: { userId: string; platform: string; platformUser: string }) =>
    addIdentity(args.userId, args.platform, args.platformUser)
  );

  const filteredUsers = roleFilter === 'all' ? users : users.filter((u) => u.role === roleFilter);

  const openCreate = () => {
    setEditingUser(null);
    setForm({ display_name: '', role: 'user', notes: '', trust_preset: 'household' });
    setModalOpen(true);
  };

  const openEdit = (user: User) => {
    setEditingUser(user);
    setForm({
      display_name: user.display_name,
      role: user.role,
      notes: user.notes ?? '',
      trust_preset: user.trust_preset ?? 'household',
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    const payload: Record<string, unknown> = {
      display_name: form.display_name,
      role: form.role,
      notes: form.notes || null,
      trust_preset: form.trust_preset,
    };
    if (editingUser) {
      await updateMut.mutateAsync({ id: editingUser.id, payload });
    } else {
      const created = await createMut.mutateAsync(payload as { display_name: string; role: string; notes?: string; trust_preset?: string });
      setModalOpen(false);
      if (created?.id) {
        setShowAddIdentity(created.id);
      }
      refetch();
      return;
    }
    setModalOpen(false);
    refetch();
  };

  const handleDelete = async (id: string) => {
    await deleteMut.mutateAsync(id);
    setConfirmDelete(null);
    refetch();
  };

  const handleAddIdentity = async () => {
    if (!showAddIdentity) return;
    await addIdentityMut.mutateAsync({
      userId: showAddIdentity,
      platform: identityForm.platform,
      platformUser: identityForm.platform_user,
    });
    setShowAddIdentity(null);
    setIdentityForm({ platform: 'telegram', platform_user: '' });
    refetch();
  };

  if (userLoading) {
    return (
      <div style={{ padding: '1rem' }}>
        <PageCard>
          <LoadingSkeleton lines={3} height="2rem" />
        </PageCard>
      </div>
    );
  }

  if (currentUser?.role !== 'admin') {
    return (
      <div style={{ padding: '1rem' }}>
        <PageCard>
          <EmptyState title="Administrator access required" description="You do not have permission to view this page." />
        </PageCard>
      </div>
    );
  }

  return (
    <div style={{ padding: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h1 style={{ margin: 0 }}>Users</h1>
        <button onClick={openCreate}>+ New User</button>
      </div>

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        {ROLE_FILTERS.map((r) => (
          <button
            key={r}
            onClick={() => setRoleFilter(r)}
            style={{
              padding: '0.35rem 0.75rem',
              borderRadius: '4px',
              border: '1px solid #ccc',
              background: roleFilter === r ? '#333' : '#fff',
              color: roleFilter === r ? '#fff' : '#333',
              cursor: 'pointer',
              fontSize: '0.875rem',
              textTransform: 'capitalize',
            }}
          >
            {r === 'all' ? 'All' : label(ROLE_LABELS, r)}
          </button>
        ))}
      </div>

      {isLoading && (
        <PageCard>
          <LoadingSkeleton lines={4} height="2rem" />
        </PageCard>
      )}

      {isError && (
        <ErrorState message={error?.message ?? 'Failed to load users'} onRetry={refetch} />
      )}

      {!isLoading && !isError && filteredUsers.length === 0 && (
        <EmptyState
          title="No users found"
          description="Create a user to get started."
          action={{ label: 'Create user', onClick: openCreate }}
        />
      )}

      {!isLoading && filteredUsers.length > 0 && (
        <PageCard style={{ padding: 0, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #eee', textAlign: 'left', background: '#fafafa' }}>
                <th style={{ padding: '0.75rem 1rem' }}>Name</th>
                <th style={{ padding: '0.75rem 1rem' }}>Role</th>
                <th style={{ padding: '0.75rem 1rem' }}>Trust</th>
                <th style={{ padding: '0.75rem 1rem' }}>Identities</th>
                <th style={{ padding: '0.75rem 1rem' }}>Rooms</th>
                <th style={{ padding: '0.75rem 1rem' }}>Created</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((u) => (
                <tr key={u.id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                  <td style={{ padding: '0.75rem 1rem' }}>
                    <div style={{ fontWeight: 600 }}>{u.display_name}</div>
                    <div style={{ fontSize: '0.75rem', color: '#888' }}>{u.id.slice(0, 8)}</div>
                  </td>
                  <td style={{ padding: '0.75rem 1rem' }}>
                    <span
                      style={{
                        display: 'inline-block',
                        padding: '0.15rem 0.5rem',
                        borderRadius: '12px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        background:
                          u.role === 'admin'
                            ? '#fee2e2'
                            : u.role === 'trusted'
                            ? '#dcfce7'
                            : u.role === 'child'
                            ? '#fef3c7'
                            : '#f3f4f6',
                        color:
                          u.role === 'admin'
                            ? '#991b1b'
                            : u.role === 'trusted'
                            ? '#166534'
                            : u.role === 'child'
                            ? '#92400e'
                            : '#374151',
                      }}
                    >
                      {label(ROLE_LABELS, u.role)}
                    </span>
                  </td>
                  <td style={{ padding: '0.75rem 1rem' }}>{u.trust_preset ?? '—'}</td>
                  <td style={{ padding: '0.75rem 1rem' }}>{u.identity_count}</td>
                  <td style={{ padding: '0.75rem 1rem' }}>{u.room_count}</td>
                  <td style={{ padding: '0.75rem 1rem' }}>{formatDate(u.created_at)}</td>
                  <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                    <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                      <button onClick={() => openEdit(u)}>Edit</button>
                      <button
                        onClick={() => setConfirmDelete(u.id)}
                        style={{ color: '#ef4444', borderColor: '#ef4444' }}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </PageCard>
      )}

      {modalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setModalOpen(false)}
        >
          <div
            style={{ width: '90%', maxWidth: 480, maxHeight: '90vh', overflowY: 'auto', background: '#fff', border: '1px solid #eee', borderRadius: '8px', padding: '1rem' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ marginTop: 0 }}>{editingUser ? 'Edit User' : 'New User'}</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <label>
                Display Name
                <input
                  value={form.display_name}
                  onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
                  placeholder="Jane Doe"
                  style={{ width: '100%', padding: '0.5rem', marginTop: '0.25rem' }}
                />
              </label>
              <label>
                Role
                <div style={{ marginTop: '0.25rem' }}>
                  <RoleDropdown value={form.role} onChange={(v) => setForm((f) => ({ ...f, role: v }))} />
                </div>
              </label>
              <label>
                Trust Preset
                <div style={{ marginTop: '0.25rem' }}>
                  <TrustPresetDropdown value={form.trust_preset} onChange={(v) => setForm((f) => ({ ...f, trust_preset: v }))} />
                </div>
              </label>
              <label>
                Notes
                <textarea
                  rows={3}
                  value={form.notes}
                  onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                  placeholder="Optional notes about this user"
                  style={{ width: '100%', padding: '0.5rem', marginTop: '0.25rem', fontFamily: 'inherit' }}
                />
              </label>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1rem' }}>
              <button onClick={() => setModalOpen(false)}>Cancel</button>
              <button onClick={handleSave} disabled={!form.display_name.trim()}>
                {editingUser ? 'Save' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmDelete && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setConfirmDelete(null)}
        >
          <div style={{ width: 360, textAlign: 'center', background: '#fff', border: '1px solid #eee', borderRadius: '8px', padding: '1rem' }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginTop: 0 }}>Delete user?</h3>
            <p style={{ fontSize: '0.875rem', color: '#666' }}>
              This action cannot be undone.
            </p>
            <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1rem' }}>
              <button onClick={() => setConfirmDelete(null)}>Cancel</button>
              <button onClick={() => handleDelete(confirmDelete)} style={{ color: '#ef4444', borderColor: '#ef4444' }}>
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {showAddIdentity && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setShowAddIdentity(null)}
        >
          <div style={{ width: 360, background: '#fff', border: '1px solid #eee', borderRadius: '8px', padding: '1rem' }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginTop: 0 }}>Add Identity</h3>
            <p style={{ fontSize: '0.875rem', color: '#666' }}>
              User created. Would you like to add a platform identity now?
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.5rem' }}>
              <label>
                Platform
                <input
                  value={identityForm.platform}
                  onChange={(e) => setIdentityForm((f) => ({ ...f, platform: e.target.value }))}
                  style={{ width: '100%', padding: '0.5rem', marginTop: '0.25rem' }}
                />
              </label>
              <label>
                Platform User
                <input
                  value={identityForm.platform_user}
                  onChange={(e) => setIdentityForm((f) => ({ ...f, platform_user: e.target.value }))}
                  style={{ width: '100%', padding: '0.5rem', marginTop: '0.25rem' }}
                />
              </label>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1rem' }}>
              <button onClick={() => setShowAddIdentity(null)}>Skip</button>
              <button onClick={handleAddIdentity} disabled={!identityForm.platform.trim() || !identityForm.platform_user.trim()}>
                Add
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
