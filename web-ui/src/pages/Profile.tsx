import { useEffect, useState } from 'react';
import { fetchRooms, updateUser, addIdentity, removeIdentity, fetchConfig } from '../api/client';
import { useApiQuery } from '../hooks/useApi';
import { useCurrentUser } from '../hooks/useCurrentUser';
import PageCard from '../components/layout/PageCard';
import EmptyState from '../components/layout/EmptyState';
import LoadingSkeleton from '../components/layout/LoadingSkeleton';
import ErrorState from '../components/layout/ErrorState';
import PlatformDropdown from '../components/forms/PlatformDropdown';
import TrustPresetDropdown from '../components/forms/TrustPresetDropdown';
import { label, ROLE_LABELS, TRUST_PRESET_LABELS } from '../lib/labels';
import { TEXT } from '../lib/text';
import './Profile.css';

const roleBadgeColor = (role: string) => {
  switch (role) {
    case 'admin':
      return '#2563eb';
    case 'trusted':
      return '#d97706';
    default:
      return '#6b7280';
  }
};

export default function Profile() {
  const { user, isLoading: userLoading, error: userError, refetch } = useCurrentUser();
  const {
    data: roomsData,
    isLoading: roomsLoading,
    isError: roomsIsError,
    error: roomsError,
  } = useApiQuery('rooms', () => fetchRooms().then((d) => d.rooms || []));
  const rooms = roomsData ?? [];

  const [editingName, setEditingName] = useState(false);
  const [editName, setEditName] = useState('');

  const [editNotes, setEditNotes] = useState('');
  const [savingNotes, setSavingNotes] = useState(false);

  const [showAddIdentity, setShowAddIdentity] = useState(false);
  const [newPlatform, setNewPlatform] = useState('');
  const [newPlatformUser, setNewPlatformUser] = useState('');
  const [addingIdentity, setAddingIdentity] = useState(false);

  const [removingIdentity, setRemovingIdentity] = useState<string | null>(null);
  const [globalPreset, setGlobalPreset] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user) {
      setEditName(user.display_name);
      setEditNotes(user.notes || '');
    }
  }, [user?.id]);

  useEffect(() => {
    fetchConfig()
      .then((cfg) => {
        const preset = cfg?.trust?.preset;
        setGlobalPreset(typeof preset === 'string' ? preset : null);
      })
      .catch(() => {
        setGlobalPreset(null);
      });
  }, []);

  const handleSaveName = async () => {
    if (!user) return;
    setError(null);
    try {
      await updateUser(user.id, { display_name: editName });
      setEditingName(false);
      refetch();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleSaveNotes = async () => {
    if (!user) return;
    setError(null);
    setSavingNotes(true);
    try {
      await updateUser(user.id, { notes: editNotes });
      refetch();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSavingNotes(false);
    }
  };

  const handleAddIdentity = async () => {
    if (!user || !newPlatform || !newPlatformUser) return;
    setError(null);
    setAddingIdentity(true);
    try {
      await addIdentity(user.id, newPlatform, newPlatformUser);
      setNewPlatform('');
      setNewPlatformUser('');
      setShowAddIdentity(false);
      refetch();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setAddingIdentity(false);
    }
  };

  const handleRemoveIdentity = async (platform: string, platformUser: string) => {
    if (!user) return;
    if (!window.confirm(TEXT.profile.removeIdentityConfirm(platform, platformUser))) return;
    setError(null);
    setRemovingIdentity(`${platform}-${platformUser}`);
    try {
      await removeIdentity(user.id, platform, platformUser);
      refetch();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setRemovingIdentity(null);
    }
  };

  if (userLoading) {
    return (
      <div className="profile-page">
        <LoadingSkeleton lines={5} />
      </div>
    );
  }

  if (userError) {
    return (
      <div className="profile-page">
        <ErrorState
          message={userError}
          onRetry={userError.includes('Not authenticated') ? () => { window.location.href = '/login'; } : refetch}
        />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="profile-page">
        <EmptyState title={TEXT.profile.noUserTitle} description={TEXT.profile.noUserDescription} />
      </div>
    );
  }

  return (
    <div className="profile-page">
      <h1>{TEXT.profile.title}</h1>

      {error && (
        <div className="alert alert--danger mb-4">
          {error}
        </div>
      )}

      <div className="profile-layout">
      <PageCard>
        <div className="profile-header">
          {editingName ? (
            <>
              <input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className="profile-name-input"
              />
              <button onClick={handleSaveName} disabled={!editName.trim()}>{TEXT.common.save}</button>
              <button onClick={() => { setEditingName(false); setEditName(user.display_name); }}>{TEXT.common.cancel}</button>
            </>
          ) : (
            <>
              <h2>{user.display_name}</h2>
              <span
                className="profile-role-badge"
                style={{ background: roleBadgeColor(user.role) }}
              >
                {label(ROLE_LABELS, user.role)}
              </span>
              <button onClick={() => setEditingName(true)} className="text-small">
                {TEXT.profile.editName}
              </button>
            </>
          )}
        </div>

        <div className="profile-info-row">
          <strong>{TEXT.profile.trustOverrideLabel}</strong>{' '}
          {user.role === 'admin' ? (
            <TrustPresetDropdown
              value={user.trust_preset || ''}
              onChange={async (value) => {
                setError(null);
                try {
                  await updateUser(user.id, { trust_preset: value || null });
                  refetch();
                } catch (err: any) {
                  setError(err.message);
                }
              }}
            />
          ) : (
            <span>{user.trust_preset || TEXT.common.none}</span>
          )}
        </div>
        <p className="text-xs text-muted">
          {user.trust_preset
            ? TEXT.profile.trustOverrideHelper(globalPreset || TEXT.common.none)
            : TEXT.profile.trustUsingGlobal(globalPreset || TEXT.common.none)}
        </p>
        <div className="mb-2">
          <span className="profile-trust-badge">
            {TEXT.profile.effectiveTrustLabel} {label(TRUST_PRESET_LABELS, user.trust_preset || globalPreset || TEXT.common.none)}
          </span>
        </div>
        <div className="profile-info-row">
          <strong>{TEXT.profile.createdLabel}</strong>{' '}
          {new Date(user.created_at).toLocaleString()}
        </div>
      </PageCard>

      <PageCard>
        <h3>{TEXT.profile.notesTitle}</h3>
        <p className="text-xs text-muted mb-2">
          {TEXT.profile.notesDescription}
        </p>
        <textarea
          value={editNotes}
          onChange={(e) => setEditNotes(e.target.value)}
          rows={4}
          className="profile-notes-textarea"
        />
        <div className="row-between">
          <span className="text-xs text-muted">
            {editNotes.length}{TEXT.profile.charactersSuffix}
          </span>
          <button onClick={handleSaveNotes} disabled={savingNotes}>
            {savingNotes ? TEXT.common.saving : TEXT.profile.saveNotes}
          </button>
        </div>
      </PageCard>

      <PageCard>
        <h3>{TEXT.profile.identitiesTitle}</h3>
        {user.identities.length === 0 && (
          <EmptyState title={TEXT.profile.identitiesEmptyTitle} description={TEXT.profile.identitiesEmptyDescription} />
        )}
        <div className="stack-sm">
          {user.identities.map((id) => (
            <div
              key={`${id.platform}-${id.platform_user}`}
              className="profile-identity-row"
            >
              <div className="profile-identity-info">
                <strong>{id.platform}</strong>: {id.platform_user}{' '}
                {id.verified && (
                  <span className="profile-identity-verified">{TEXT.profile.verifiedBadge}</span>
                )}
              </div>
              <button
                onClick={() => handleRemoveIdentity(id.platform, id.platform_user)}
                disabled={removingIdentity === `${id.platform}-${id.platform_user}`}
                className="text-xs text-danger"
              >
                {removingIdentity === `${id.platform}-${id.platform_user}` ? TEXT.common.removing : TEXT.common.remove}
              </button>
            </div>
          ))}
        </div>

        {!showAddIdentity ? (
          <button onClick={() => setShowAddIdentity(true)} className="mt-4">
            {TEXT.profile.addIdentityButton}
          </button>
        ) : (
          <div className="profile-add-identity-form">
            <div className="mb-2">
              <label className="form-label">{TEXT.profile.addIdentityPlatformLabel}</label>
              <PlatformDropdown value={newPlatform} onChange={setNewPlatform} includeEmpty />
            </div>
            <div className="mb-2">
              <label className="form-label">{TEXT.profile.addIdentityUserLabel}</label>
              <input
                value={newPlatformUser}
                onChange={(e) => setNewPlatformUser(e.target.value)}
                placeholder={TEXT.profile.addIdentityUserPlaceholder}
                className="form-input"
              />
            </div>
            <div className="row-sm">
              <button onClick={handleAddIdentity} disabled={addingIdentity || !newPlatform || !newPlatformUser.trim()}>
                {addingIdentity ? TEXT.common.adding : TEXT.common.add}
              </button>
              <button onClick={() => { setShowAddIdentity(false); setNewPlatform(''); setNewPlatformUser(''); }}>
                {TEXT.common.cancel}
              </button>
            </div>
          </div>
        )}
      </PageCard>

      <PageCard>
        <h3>{TEXT.profile.roomsTitle}</h3>
        {roomsLoading && <LoadingSkeleton lines={3} />}
        {roomsIsError && roomsError && (
          <ErrorState message={roomsError.message} onRetry={() => window.location.reload()} />
        )}
        {!roomsLoading && !roomsIsError && rooms.length === 0 && (
          <EmptyState
            title={TEXT.profile.roomsEmptyTitle}
            description={TEXT.profile.roomsEmptyDescription}
          />
        )}
        {!roomsLoading && !roomsIsError && rooms.map((room) => (
          <div
            key={room.id}
            className="profile-room-row"
          >
            <strong>{room.display_name || room.platform_room_id}</strong>{' '}
            <span className="text-secondary">({room.platform})</span>
          </div>
        ))}
      </PageCard>
      </div>
    </div>
  );
}
