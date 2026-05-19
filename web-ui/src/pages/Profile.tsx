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
      <div style={{ padding: '1rem' }}>
        <LoadingSkeleton lines={5} />
      </div>
    );
  }

  if (userError) {
    return (
      <div style={{ padding: '1rem' }}>
        <ErrorState
          message={userError}
          onRetry={userError.includes('Not authenticated') ? () => { window.location.href = '/login'; } : refetch}
        />
      </div>
    );
  }

  if (!user) {
    return (
      <div style={{ padding: '1rem' }}>
        <EmptyState title={TEXT.profile.noUserTitle} description={TEXT.profile.noUserDescription} />
      </div>
    );
  }

  return (
    <div style={{ padding: '1rem' }}>
      <h1>{TEXT.profile.title}</h1>

      {error && (
        <div
          style={{
            marginBottom: '1rem',
            padding: '0.75rem 1rem',
            background: '#fee2e2',
            color: '#991b1b',
            borderRadius: '6px',
            fontSize: '0.875rem',
          }}
        >
          {error}
        </div>
      )}

      <PageCard>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
          {editingName ? (
            <>
              <input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                style={{ padding: '0.5rem', borderRadius: '4px', border: '1px solid #ccc', fontSize: '1.25rem', fontWeight: 'bold', flex: 1, minWidth: '200px' }}
              />
              <button onClick={handleSaveName} disabled={!editName.trim()}>{TEXT.common.save}</button>
              <button onClick={() => { setEditingName(false); setEditName(user.display_name); }}>{TEXT.common.cancel}</button>
            </>
          ) : (
            <>
              <h2 style={{ margin: 0 }}>{user.display_name}</h2>
              <span
                style={{
                  display: 'inline-block',
                  padding: '0.25rem 0.5rem',
                  borderRadius: '999px',
                  fontSize: '0.75rem',
                  fontWeight: 'bold',
                  color: '#fff',
                  background: roleBadgeColor(user.role),
                  textTransform: 'uppercase',
                }}
              >
                {label(ROLE_LABELS, user.role)}
              </span>
              <button onClick={() => setEditingName(true)} style={{ fontSize: '0.875rem' }}>
                {TEXT.profile.editName}
              </button>
            </>
          )}
        </div>

        <div style={{ marginBottom: '0.5rem', fontSize: '0.875rem', color: '#666' }}>
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
        <p style={{ margin: '0.25rem 0 0', fontSize: '0.75rem', color: '#888' }}>
          {user.trust_preset
            ? TEXT.profile.trustOverrideHelper(globalPreset || TEXT.common.none)
            : TEXT.profile.trustUsingGlobal(globalPreset || TEXT.common.none)}
        </p>
        <div style={{ marginTop: '0.5rem' }}>
          <span
            style={{
              display: 'inline-block',
              padding: '0.25rem 0.5rem',
              borderRadius: '999px',
              fontSize: '0.75rem',
              fontWeight: 'bold',
              color: '#fff',
              background: '#1976d2',
            }}
          >
            {TEXT.profile.effectiveTrustLabel} {label(TRUST_PRESET_LABELS, user.trust_preset || globalPreset || TEXT.common.none)}
          </span>
        </div>
        <div style={{ marginBottom: '0.5rem', fontSize: '0.875rem', color: '#666' }}>
          <strong>{TEXT.profile.createdLabel}</strong>{' '}
          {new Date(user.created_at).toLocaleString()}
        </div>
      </PageCard>

      <PageCard>
        <h3 style={{ marginTop: 0 }}>{TEXT.profile.notesTitle}</h3>
        <p style={{ margin: '0 0 0.5rem', fontSize: '0.75rem', color: '#888' }}>
          {TEXT.profile.notesDescription}
        </p>
        <textarea
          value={editNotes}
          onChange={(e) => setEditNotes(e.target.value)}
          rows={4}
          style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #ccc', fontFamily: 'inherit', marginBottom: '0.5rem' }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '0.75rem', color: '#888' }}>
            {editNotes.length}{TEXT.profile.charactersSuffix}
          </span>
          <button onClick={handleSaveNotes} disabled={savingNotes}>
            {savingNotes ? TEXT.common.saving : TEXT.profile.saveNotes}
          </button>
        </div>
      </PageCard>

      <PageCard>
        <h3 style={{ marginTop: 0 }}>{TEXT.profile.identitiesTitle}</h3>
        {user.identities.length === 0 && (
          <EmptyState title={TEXT.profile.identitiesEmptyTitle} description={TEXT.profile.identitiesEmptyDescription} />
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {user.identities.map((id) => (
            <div
              key={`${id.platform}-${id.platform_user}`}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '0.5rem 0.75rem',
                borderRadius: '6px',
                border: '1px solid #eee',
                background: '#fafafa',
              }}
            >
              <div style={{ fontSize: '0.875rem' }}>
                <strong>{id.platform}</strong>: {id.platform_user}{' '}
                {id.verified && (
                  <span style={{ color: '#22c55e', fontSize: '0.75rem', fontWeight: 'bold' }}>{TEXT.profile.verifiedBadge}</span>
                )}
              </div>
              <button
                onClick={() => handleRemoveIdentity(id.platform, id.platform_user)}
                disabled={removingIdentity === `${id.platform}-${id.platform_user}`}
                style={{ fontSize: '0.75rem', color: '#ef4444' }}
              >
                {removingIdentity === `${id.platform}-${id.platform_user}` ? TEXT.common.removing : TEXT.common.remove}
              </button>
            </div>
          ))}
        </div>

        {!showAddIdentity ? (
          <button onClick={() => setShowAddIdentity(true)} style={{ marginTop: '1rem' }}>
            {TEXT.profile.addIdentityButton}
          </button>
        ) : (
          <div style={{ marginTop: '1rem', padding: '1rem', border: '1px solid #eee', borderRadius: '8px', background: '#fafafa' }}>
            <div style={{ marginBottom: '0.5rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontSize: '0.875rem' }}>{TEXT.profile.addIdentityPlatformLabel}</label>
              <PlatformDropdown value={newPlatform} onChange={setNewPlatform} includeEmpty />
            </div>
            <div style={{ marginBottom: '0.5rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontSize: '0.875rem' }}>{TEXT.profile.addIdentityUserLabel}</label>
              <input
                value={newPlatformUser}
                onChange={(e) => setNewPlatformUser(e.target.value)}
                placeholder={TEXT.profile.addIdentityUserPlaceholder}
                style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #ccc', fontSize: '0.875rem' }}
              />
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
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
        <h3 style={{ marginTop: 0 }}>{TEXT.profile.roomsTitle}</h3>
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
            style={{
              padding: '0.5rem 0',
              borderBottom: '1px solid #eee',
              fontSize: '0.875rem',
            }}
          >
            <strong>{room.display_name || room.platform_room_id}</strong>{' '}
            <span style={{ color: '#666' }}>({room.platform})</span>
          </div>
        ))}
      </PageCard>
    </div>
  );
}
