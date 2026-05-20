import { useState } from 'react';
import { useApiQuery, useApiMutation } from '../hooks/useApi';
import { useCurrentUser } from '../hooks/useCurrentUser';
import { useToast } from '../hooks/useToast';
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
import Button from '../components/Button';
import RoleDropdown from '../components/forms/RoleDropdown';
import TrustPresetDropdown from '../components/forms/TrustPresetDropdown';
import PlatformDropdown from '../components/forms/PlatformDropdown';
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
  const { addToast } = useToast();
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
  const [identityForm, setIdentityForm] = useState({ platform: '', platform_user: '' });
  const [confirmRoleChange, setConfirmRoleChange] = useState(false);

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
      if (
        editingUser.id === currentUser?.id &&
        editingUser.role === 'admin' &&
        form.role !== 'admin' &&
        !confirmRoleChange
      ) {
        setConfirmRoleChange(true);
        return;
      }
      await updateMut.mutateAsync({ id: editingUser.id, payload });
      addToast({ message: 'User updated', type: 'success', duration: 3000 });
    } else {
      const created = await createMut.mutateAsync(payload as { display_name: string; role: string; notes?: string; trust_preset?: string });
      addToast({ message: 'User created', type: 'success', duration: 3000 });
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
    addToast({ message: 'User deleted', type: 'success', duration: 3000 });
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
        <PageCard className="page-card--flush">
          <table className="data-table responsive-table">
            <thead>
              <tr>
                <th>{TEXT.adminUsers.tableName}</th>
                <th>{TEXT.adminUsers.tableRole}</th>
                <th>{TEXT.adminUsers.tableTrust}</th>
                <th>{TEXT.adminUsers.tableIdentities}</th>
                <th>{TEXT.adminUsers.tableRooms}</th>
                <th>{TEXT.adminUsers.tableCreated}</th>
                <th className="text-right">{TEXT.adminUsers.tableActions}</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((u) => (
                <tr key={u.id}>
                  <td data-label={TEXT.adminUsers.tableName}>
                    <div className="font-semibold">{u.display_name}</div>
                    <div className="text-xs text-muted">{u.id.slice(0, 8)}</div>
                  </td>
                  <td data-label={TEXT.adminUsers.tableRole}>
                    <span
                      className={`admin-users-role-badge admin-users-role-badge--${u.role === 'admin' ? 'admin' : u.role === 'trusted' ? 'trusted' : u.role === 'child' ? 'child' : 'default'}`}
                    >
                      {label(ROLE_LABELS, u.role)}
                    </span>
                  </td>
                  <td data-label={TEXT.adminUsers.tableTrust}>{u.trust_preset ?? '—'}</td>
                  <td data-label={TEXT.adminUsers.tableIdentities}>{u.identity_count}</td>
                  <td data-label={TEXT.adminUsers.tableRooms}>{u.room_count}</td>
                  <td data-label={TEXT.adminUsers.tableCreated}>{formatDate(u.created_at)}</td>
                  <td data-label={TEXT.adminUsers.tableActions} className="text-right">
                    <div className="admin-users-actions">
                      <button onClick={() => openEdit(u)}>{TEXT.common.edit}</button>
                      <button
                        onClick={() => setConfirmDelete(u.id)}
                        className="text-danger border-danger"
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
            <h3>{editingUser ? TEXT.adminUsers.editTitle : TEXT.adminUsers.createTitle}</h3>
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
              <Button variant="ghost" onClick={() => { setModalOpen(false); setConfirmRoleChange(false); }}>
                {TEXT.common.cancel}
              </Button>
              <Button onClick={handleSave} disabled={!form.display_name.trim()}>
                {editingUser ? TEXT.common.save : TEXT.common.create}
              </Button>
            </div>
          </div>
        </div>
      )}

      {confirmRoleChange && (
        <div
          className="modal-overlay"
          onClick={() => setConfirmRoleChange(false)}
        >
          <div className="modal modal--sm" onClick={(e) => e.stopPropagation()}>
            <h3>Remove admin role?</h3>
            <p className="text-small text-secondary">
              You are about to remove your own administrator role. You will lose access to this page.
            </p>
            <div className="row-center gap-2 mt-4">
              <button onClick={() => setConfirmRoleChange(false)}>{TEXT.common.cancel}</button>
              <button onClick={handleSave} className="text-danger border-danger">
                {TEXT.common.confirm}
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
            <h3>{TEXT.adminUsers.deleteConfirmTitle}</h3>
            <p className="text-small text-secondary">
              {TEXT.adminUsers.deleteConfirmDescription}
            </p>
            <div className="row-center gap-2 mt-4">
              <Button variant="ghost" onClick={() => setConfirmDelete(null)}>
                {TEXT.common.cancel}
              </Button>
              <Button variant="danger" onClick={() => handleDelete(confirmDelete)}>
                {TEXT.common.delete}
              </Button>
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
            <h3>{TEXT.adminUsers.addIdentityTitle}</h3>
            <p className="text-small text-secondary">
              {TEXT.adminUsers.addIdentityPrompt}
            </p>
            <div className="stack-md mt-2">
              <label>
                {TEXT.adminUsers.addIdentityPlatformLabel}
                <div className="mt-1">
                  <PlatformDropdown
                    value={identityForm.platform}
                    onChange={(v) => setIdentityForm((f) => ({ ...f, platform: v }))}
                    includeEmpty
                  />
                </div>
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
