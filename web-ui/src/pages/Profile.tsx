import { useEffect, useState } from 'react';
import { fetchRooms, updateUser, addIdentity, removeIdentity } from '../api/client';
import { useApiQuery } from '../hooks/useApi';
import { useCurrentUser } from '../hooks/useCurrentUser';
import ErrorState from '../components/layout/ErrorState';
import LoadingSkeleton from '../components/layout/LoadingSkeleton';

const cardStyle: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #eee',
  borderRadius: '8px',
  padding: '1rem',
  marginBottom: '1rem',
};

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
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState('');
  const [editNotes, setEditNotes] = useState('');
  const [newPlatform, setNewPlatform] = useState('');
  const [newPlatformUser, setNewPlatformUser] = useState('');

  useEffect(() => {
    if (user) {
      setEditName(user.display_name);
      setEditNotes(user.notes || '');
    }
  }, [user?.id]);

  const handleSave = async () => {
    if (!user) return;
    try {
      await updateUser(user.id, { display_name: editName, notes: editNotes });
      setEditing(false);
      refetch();
    } catch (err: any) {
      // Error handling could be improved; for now swallow to match prior behavior
    }
  };

  const handleAddIdentity = async () => {
    if (!user || !newPlatform || !newPlatformUser) return;
    try {
      await addIdentity(user.id, newPlatform, newPlatformUser);
      setNewPlatform('');
      setNewPlatformUser('');
      refetch();
    } catch (err: any) {
      // Error handling could be improved
    }
  };

  const handleRemoveIdentity = async (platform: string, platformUser: string) => {
    if (!user) return;
    try {
      await removeIdentity(user.id, platform, platformUser);
      refetch();
    } catch (err: any) {
      // Error handling could be improved
    }
  };

  if (userLoading) {
    return (
      <div style={{ padding: '1rem' }}>
        <p>Loading profile…</p>
      </div>
    );
  }

  if (userError) {
    return (
      <div style={{ padding: '1rem' }}>
        <p style={{ color: 'red' }}>{userError}</p>
        {userError.includes('Not authenticated') && (
          <button onClick={() => { window.location.href = '/login'; }}>
            Go to Login
          </button>
        )}
      </div>
    );
  }

  if (!user) {
    return (
      <div style={{ padding: '1rem' }}>
        <p>No user found.</p>
      </div>
    );
  }

  return (
    <div style={{ padding: '1rem' }}>
      <h1>User Profile</h1>

      <div style={cardStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
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
            {user.role}
          </span>
        </div>

        <div style={{ marginBottom: '0.5rem', fontSize: '0.875rem', color: '#666' }}>
          <strong>Trust preset:</strong> {user.trust_preset || '—'}
        </div>
        <div style={{ marginBottom: '0.5rem', fontSize: '0.875rem', color: '#666' }}>
          <strong>Created:</strong> {new Date(user.created_at).toLocaleString()}
        </div>

        {editing ? (
          <>
            <div style={{ marginBottom: '0.5rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontSize: '0.875rem' }}>Display name</label>
              <input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #ccc' }}
              />
            </div>
            <div style={{ marginBottom: '0.5rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontSize: '0.875rem' }}>Notes</label>
              <textarea
                value={editNotes}
                onChange={(e) => setEditNotes(e.target.value)}
                rows={4}
                style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #ccc', fontFamily: 'inherit' }}
              />
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button onClick={handleSave}>Save</button>
              <button onClick={() => { setEditing(false); setEditName(user.display_name); setEditNotes(user.notes || ''); }}>Cancel</button>
            </div>
          </>
        ) : (
          <>
            <div style={{ marginBottom: '0.5rem', whiteSpace: 'pre-wrap' }}>
              <strong>Notes:</strong> {user.notes || '—'}
            </div>
            <button onClick={() => setEditing(true)}>Edit Profile</button>
          </>
        )}
      </div>

      <div style={cardStyle}>
        <h3 style={{ marginTop: 0 }}>Identities</h3>
        {user.identities.length === 0 && <p style={{ color: '#666' }}>No identities linked.</p>}
        {user.identities.map((id) => (
          <div
            key={`${id.platform}-${id.platform_user}`}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '0.5rem 0',
              borderBottom: '1px solid #eee',
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
              style={{ fontSize: '0.75rem', color: '#ef4444' }}
            >
              Remove
            </button>
          </div>
        ))}

        <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <label style={{ fontSize: '0.875rem' }}>
            Platform:{ ' '}
            <input
              value={newPlatform}
              onChange={(e) => setNewPlatform(e.target.value)}
              placeholder="e.g. matrix"
              style={{ padding: '0.25rem', borderRadius: '4px', border: '1px solid #ccc' }}
            />
          </label>
          <label style={{ fontSize: '0.875rem' }}>
            User:{ ' '}
            <input
              value={newPlatformUser}
              onChange={(e) => setNewPlatformUser(e.target.value)}
              placeholder="e.g. @alice:example.com"
              style={{ padding: '0.25rem', borderRadius: '4px', border: '1px solid #ccc' }}
            />
          </label>
          <button onClick={handleAddIdentity}>Add Identity</button>
        </div>
      </div>

      <div style={cardStyle}>
        <h3 style={{ marginTop: 0 }}>Rooms</h3>
        {roomsLoading && <LoadingSkeleton lines={3} />}
        {roomsIsError && roomsError && (
          <ErrorState message={roomsError.message} onRetry={() => window.location.reload()} />
        )}
        {!roomsLoading && !roomsIsError && rooms.length === 0 && <p style={{ color: '#666' }}>No rooms found.</p>}
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
      </div>
    </div>
  );
}
