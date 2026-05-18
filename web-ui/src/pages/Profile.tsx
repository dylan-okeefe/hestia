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
    try {
      await updateUser(user.id, { display_name: editName });
      setEditingName(false);
      refetch();
    } catch {
      // swallow to match prior behavior
    }
  };

  const handleSaveNotes = async () => {
    if (!user) return;
    setSavingNotes(true);
    try {
      await updateUser(user.id, { notes: editNotes });
      refetch();
    } catch {
      // swallow to match prior behavior
    } finally {
      setSavingNotes(false);
    }
  };

  const handleAddIdentity = async () => {
    if (!user || !newPlatform || !newPlatformUser) return;
    setAddingIdentity(true);
    try {
      await addIdentity(user.id, newPlatform, newPlatformUser);
      setNewPlatform('');
      setNewPlatformUser('');
      setShowAddIdentity(false);
      refetch();
    } catch {
      // swallow to match prior behavior
    } finally {
      setAddingIdentity(false);
    }
  };

  const handleRemoveIdentity = async (platform: string, platformUser: string) => {
    if (!user) return;
    if (!window.confirm(`Remove identity ${platform}: ${platformUser}?`)) return;
    setRemovingIdentity(`${platform}-${platformUser}`);
    try {
      await removeIdentity(user.id, platform, platformUser);
      refetch();
    } catch {
      // swallow to match prior behavior
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
        <EmptyState title="No user found" description="Please log in to view your profile." />
      </div>
    );
  }

  return (
    <div style={{ padding: '1rem' }}>
      <h1>User Profile</h1>

      <PageCard>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
          {editingName ? (
            <>
              <input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                style={{ padding: '0.5rem', borderRadius: '4px', border: '1px solid #ccc', fontSize: '1.25rem', fontWeight: 'bold', flex: 1, minWidth: '200px' }}
              />
              <button onClick={handleSaveName} disabled={!editName.trim()}>Save</button>
              <button onClick={() => { setEditingName(false); setEditName(user.display_name); }}>Cancel</button>
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
                Edit name
              </button>
            </>
          )}
        </div>

        <div style={{ marginBottom: '0.5rem', fontSize: '0.875rem', color: '#666' }}>
          <strong>Personal trust override:</strong>{' '}
          {user.role === 'admin' ? (
            <TrustPresetDropdown
              value={user.trust_preset || ''}
              onChange={async (value) => {
                try {
                  await updateUser(user.id, { trust_preset: value || null });
                  refetch();
                } catch {
                  // swallow
                }
              }}
            />
          ) : (
            <span>{user.trust_preset || '—'}</span>
          )}
        </div>
        <p style={{ margin: '0.25rem 0 0', fontSize: '0.75rem', color: '#888' }}>
          {user.trust_preset
            ? `Overrides the global trust level (currently: ${globalPreset || '—'}).`
            : `Using global trust level: ${globalPreset || '—'}. Select a preset to override.`}
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
            Effective: {label(TRUST_PRESET_LABELS, user.trust_preset || globalPreset || '—')}
          </span>
        </div>
        <div style={{ marginBottom: '0.5rem', fontSize: '0.875rem', color: '#666' }}>
          <strong>Created:</strong>{' '}
          {new Date(user.created_at).toLocaleString()}
        </div>
      </PageCard>

      <PageCard>
        <h3 style={{ marginTop: 0 }}>Notes</h3>
        <p style={{ margin: '0 0 0.5rem', fontSize: '0.75rem', color: '#888' }}>
          Facts about you that Hestia sees in every conversation.
        </p>
        <textarea
          value={editNotes}
          onChange={(e) => setEditNotes(e.target.value)}
          rows={4}
          style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #ccc', fontFamily: 'inherit', marginBottom: '0.5rem' }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '0.75rem', color: '#888' }}>
            {editNotes.length} characters
          </span>
          <button onClick={handleSaveNotes} disabled={savingNotes}>
            {savingNotes ? 'Saving…' : 'Save Notes'}
          </button>
        </div>
      </PageCard>

      <PageCard>
        <h3 style={{ marginTop: 0 }}>Identities</h3>
        {user.identities.length === 0 && (
          <EmptyState title="No identities linked" description="Add an identity so Hestia knows how to reach you on other platforms." />
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
                  <span style={{ color: '#22c55e', fontSize: '0.75rem', fontWeight: 'bold' }}>✓ verified</span>
                )}
              </div>
              <button
                onClick={() => handleRemoveIdentity(id.platform, id.platform_user)}
                disabled={removingIdentity === `${id.platform}-${id.platform_user}`}
                style={{ fontSize: '0.75rem', color: '#ef4444' }}
              >
                {removingIdentity === `${id.platform}-${id.platform_user}` ? 'Removing…' : 'Remove'}
              </button>
            </div>
          ))}
        </div>

        {!showAddIdentity ? (
          <button onClick={() => setShowAddIdentity(true)} style={{ marginTop: '1rem' }}>
            + Add identity
          </button>
        ) : (
          <div style={{ marginTop: '1rem', padding: '1rem', border: '1px solid #eee', borderRadius: '8px', background: '#fafafa' }}>
            <div style={{ marginBottom: '0.5rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontSize: '0.875rem' }}>Platform</label>
              <PlatformDropdown value={newPlatform} onChange={setNewPlatform} includeEmpty />
            </div>
            <div style={{ marginBottom: '0.5rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontSize: '0.875rem' }}>User ID</label>
              <input
                value={newPlatformUser}
                onChange={(e) => setNewPlatformUser(e.target.value)}
                placeholder="e.g. @alice:example.com"
                style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #ccc', fontSize: '0.875rem' }}
              />
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button onClick={handleAddIdentity} disabled={addingIdentity || !newPlatform || !newPlatformUser.trim()}>
                {addingIdentity ? 'Adding…' : 'Add'}
              </button>
              <button onClick={() => { setShowAddIdentity(false); setNewPlatform(''); setNewPlatformUser(''); }}>
                Cancel
              </button>
            </div>
          </div>
        )}
      </PageCard>

      <PageCard>
        <h3 style={{ marginTop: 0 }}>Rooms</h3>
        {roomsLoading && <LoadingSkeleton lines={3} />}
        {roomsIsError && roomsError && (
          <ErrorState message={roomsError.message} onRetry={() => window.location.reload()} />
        )}
        {!roomsLoading && !roomsIsError && rooms.length === 0 && (
          <EmptyState title="No rooms found" description="Rooms appear when Hestia is added to group chats." />
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
