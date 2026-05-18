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
import { TEXT } from '../lib/text';
import './AdminUsers.css';

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
      <div className="admin-users-page">
        <PageCard>
          <LoadingSkeleton lines={3} height="2rem" />
        </PageCard>
      </div>
    );
  }

  if (currentUser?.role !== 'admin') {
    return (
      <div className="admin-users-page">
        <PageCard>
          <EmptyState title={TEXT.adminUsers.accessDeniedTitle} description={TEXT.adminUsers.accessDeniedDescription} />
        </PageCard>
      </div>
    );
  }

  return (
    <div className="admin-users-page">
      <div className="admin-users-header">
        <h1 className="admin-users-title">{TEXT.adminUsers.title}</h1>
        <button onClick={openCreate}>{TEXT.adminUsers.createButton}</button>
      </div>

      <div className="admin-users-filters">
        {ROLE_FILTERS.map((r) => (
          <button
            key={r}
            onClick={() => setRoleFilter(r)}
            className={roleFilter === r ? 'toggle-btn toggle-btn--active' : 'toggle-btn'}
          >
            {r === 'all' ? TEXT.common.filter : label(ROLE_LABELS, r)}
          </button>
        ))}
      </div>

      {isLoading && (
        <PageCard>
          <LoadingSkeleton lines={4} height="2rem" />
        </PageCard>
      )}

      {isError && (
        <ErrorState message={error?.message ?? TEXT.adminUsers.loadError} onRetry={refetch} />
      )}

      {!isLoading && !isError && filteredUsers.length === 0 && (
        <EmptyState
          title={TEXT.adminUsers.emptyTitle}
          description={TEXT.adminUsers.emptyDescription}
          action={{ label: TEXT.adminUsers.emptyAction, onClick: openCreate }}
        />
      )}

      {!isLoading && filteredUsers.length > 0 && (
        <PageCard style={{ padding: 0, overflow: 'hidden' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>{TEXT.adminUsers.tableName}</th>
                <th>{TEXT.adminUsers.tableRole}</th>
                <th>{TEXT.adminUsers.tableTrust}</th>
                <th>{TEXT.adminUsers.tableIdentities}</th>
                <th>{TEXT.adminUsers.tableRooms}</th>
                <th>{TEXT.adminUsers.tableCreated}</th>
                <th style={{ textAlign: 'right' }}>{TEXT.adminUsers.tableActions}</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((u) => (
                <tr key={u.id}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{u.display_name}</div>
                    <div className="text-xs text-muted">{u.id.slice(0, 8)}</div>
                  </td>
                  <td>
                    <span
                      className={`admin-users-role-badge admin-users-role-badge--${u.role === 'admin' ? 'admin' : u.role === 'trusted' ? 'trusted' : u.role === 'child' ? 'child' : 'default'}`}
                    >
                      {label(ROLE_LABELS, u.role)}
                    </span>
                  </td>
                  <td>{u.trust_preset ?? '—'}</td>
                  <td>{u.identity_count}</td>
                  <td>{u.room_count}</td>
                  <td>{formatDate(u.created_at)}</td>
                  <td style={{ textAlign: 'right' }}>
                    <div className="admin-users-actions">
                      <button onClick={() => openEdit(u)}>{TEXT.common.edit}</button>
                      <button
                        onClick={() => setConfirmDelete(u.id)}
                        className="text-danger"
                        style={{ borderColor: 'var(--color-danger)' }}
                      >
                        {TEXT.common.delete}
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
          className="modal-overlay"
          onClick={() => setModalOpen(false)}
        >
          <div
            className="modal modal--md"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ marginTop: 0 }}>{editingUser ? TEXT.adminUsers.editTitle : TEXT.adminUsers.createTitle}</h3>
            <div className="stack-md">
              <label>
                {TEXT.adminUsers.displayNameLabel}
                <input
                  value={form.display_name}
                  onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
                  placeholder={TEXT.adminUsers.displayNamePlaceholder}
                  className="form-input mt-1"
                />
              </label>
              <label>
                {TEXT.adminUsers.roleLabel}
                <div className="mt-1">
                  <RoleDropdown value={form.role} onChange={(v) => setForm((f) => ({ ...f, role: v }))} />
                </div>
              </label>
              <label>
                {TEXT.adminUsers.trustPresetLabel}
                <div className="mt-1">
                  <TrustPresetDropdown value={form.trust_preset} onChange={(v) => setForm((f) => ({ ...f, trust_preset: v }))} />
                </div>
              </label>
              <label>
                {TEXT.adminUsers.notesLabel}
                <textarea
                  rows={3}
                  value={form.notes}
                  onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                  placeholder={TEXT.adminUsers.notesPlaceholder}
                  className="form-textarea mt-1"
                />
              </label>
            </div>
            <div className="row-between mt-4">
              <button onClick={() => setModalOpen(false)}>{TEXT.common.cancel}</button>
              <button onClick={handleSave} disabled={!form.display_name.trim()}>
                {editingUser ? TEXT.common.save : TEXT.common.create}
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmDelete && (
        <div
          className="modal-overlay"
          onClick={() => setConfirmDelete(null)}
        >
          <div className="modal modal--sm" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginTop: 0 }}>{TEXT.adminUsers.deleteConfirmTitle}</h3>
            <p className="text-small text-secondary">
              {TEXT.adminUsers.deleteConfirmDescription}
            </p>
            <div className="row-center gap-2 mt-4" style={{ justifyContent: 'center' }}>
              <button onClick={() => setConfirmDelete(null)}>{TEXT.common.cancel}</button>
              <button onClick={() => handleDelete(confirmDelete)} className="text-danger" style={{ borderColor: 'var(--color-danger)' }}>
                {TEXT.common.delete}
              </button>
            </div>
          </div>
        </div>
      )}

      {showAddIdentity && (
        <div
          className="modal-overlay"
          onClick={() => setShowAddIdentity(null)}
        >
          <div className="modal modal--sm" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginTop: 0 }}>{TEXT.adminUsers.addIdentityTitle}</h3>
            <p className="text-small text-secondary">
              {TEXT.adminUsers.addIdentityPrompt}
            </p>
            <div className="stack-md mt-2">
              <label>
                {TEXT.adminUsers.addIdentityPlatformLabel}
                <input
                  value={identityForm.platform}
                  onChange={(e) => setIdentityForm((f) => ({ ...f, platform: e.target.value }))}
                  className="form-input mt-1"
                />
              </label>
              <label>
                {TEXT.adminUsers.addIdentityUserLabel}
                <input
                  value={identityForm.platform_user}
                  onChange={(e) => setIdentityForm((f) => ({ ...f, platform_user: e.target.value }))}
                  className="form-input mt-1"
                />
              </label>
            </div>
            <div className="row-between mt-4">
              <button onClick={() => setShowAddIdentity(null)}>{TEXT.adminUsers.skip}</button>
              <button onClick={handleAddIdentity} disabled={!identityForm.platform.trim() || !identityForm.platform_user.trim()}>
                {TEXT.common.add}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
