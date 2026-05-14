import { useEffect, useState } from 'react';
import { fetchSessions, fetchStyleProfile, fetchUsers, fetchUser, fetchMemories, updateUser } from '../api/client';

interface Session {
  id: string;
  platform: string;
  platform_user: string;
  created_at: string;
  message_count?: number;
}

interface Memory {
  id: string;
  content: string;
  created_at?: string;
}

const cardStyle: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #eee',
  borderRadius: '8px',
  padding: '1rem',
  marginBottom: '1rem',
};

export default function Knowledge() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [style, setStyle] = useState<Record<string, unknown>>({});
  const [user, setUser] = useState<any>(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [memoriesError, setMemoriesError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingNotes, setEditingNotes] = useState(false);
  const [editNotes, setEditNotes] = useState('');
  const [savingNotes, setSavingNotes] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setMemoriesError(null);

    Promise.all([
      fetchSessions(10),
      fetchStyleProfile('cli', 'default'),
      fetchUsers().then((u) => (u.users[0] ? fetchUser(u.users[0].id) : null)),
      fetchMemories(20).catch(() => null),
    ])
      .then(([sessionsData, styleData, userData, memoriesData]) => {
        setSessions((sessionsData.sessions || []) as Session[]);
        setStyle(styleData.profile || {});
        setUser(userData);
        setEditNotes(userData?.notes || '');
        if (memoriesData && memoriesData.memories) {
          setMemories(memoriesData.memories as Memory[]);
        } else if (memoriesData && Array.isArray(memoriesData)) {
          setMemories(memoriesData as Memory[]);
        } else {
          setMemories([]);
        }
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  const handleSaveNotes = async () => {
    if (!user) return;
    setSavingNotes(true);
    try {
      await updateUser(user.id, { notes: editNotes });
      setUser({ ...user, notes: editNotes });
      setEditingNotes(false);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSavingNotes(false);
    }
  };

  if (loading) {
    return <div style={{ padding: '1rem' }}><p>Loading knowledge…</p></div>;
  }

  if (error && !user) {
    return <div style={{ padding: '1rem' }}><p style={{ color: 'red' }}>{error}</p></div>;
  }

  const styleMetrics = Object.entries(style);

  return (
    <div style={{ padding: '1rem' }}>
      <h1>What Hestia Knows About You</h1>

      {error && <p style={{ color: 'red' }}>{error}</p>}

      <div style={cardStyle}>
        <h3 style={{ marginTop: 0 }}>User Notes</h3>
        {editingNotes ? (
          <>
            <textarea
              value={editNotes}
              onChange={(e) => setEditNotes(e.target.value)}
              rows={4}
              style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #ccc', fontFamily: 'inherit', marginBottom: '0.5rem' }}
            />
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button onClick={handleSaveNotes} disabled={savingNotes}>{savingNotes ? 'Saving…' : 'Save'}</button>
              <button onClick={() => { setEditingNotes(false); setEditNotes(user?.notes || ''); }}>Cancel</button>
            </div>
          </>
        ) : (
          <>
            <p style={{ whiteSpace: 'pre-wrap', marginTop: 0 }}>{user?.notes || 'No notes saved.'}</p>
            <button onClick={() => setEditingNotes(true)}>Edit Notes</button>
          </>
        )}
      </div>

      <div style={cardStyle}>
        <h3 style={{ marginTop: 0 }}>Style Profile</h3>
        {styleMetrics.length === 0 && <p style={{ color: '#666' }}>No style metrics found.</p>}
        {styleMetrics.map(([key, value]) => (
          <div
            key={key}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '0.75rem',
              borderBottom: '1px solid #eee',
            }}
          >
            <div>
              <strong>{key}</strong>
              <div style={{ fontSize: '0.9rem', color: '#555' }}>
                {typeof value === 'object' ? JSON.stringify(value) : String(value)}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div style={cardStyle}>
        <h3 style={{ marginTop: 0 }}>Session History</h3>
        {sessions.length === 0 && <p style={{ color: '#666' }}>No sessions found.</p>}
        {sessions.length > 0 && (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #ccc', textAlign: 'left' }}>
                <th style={{ padding: '0.25rem' }}>Session</th>
                <th style={{ padding: '0.25rem' }}>Platform</th>
                <th style={{ padding: '0.25rem' }}>Start</th>
                <th style={{ padding: '0.25rem' }}>Messages</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.id} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: '0.25rem', fontFamily: 'monospace', fontSize: '0.75rem' }}>{s.id.slice(0, 8)}…</td>
                  <td style={{ padding: '0.25rem' }}>{s.platform}</td>
                  <td style={{ padding: '0.25rem' }}>{s.created_at ? new Date(s.created_at).toLocaleString() : '—'}</td>
                  <td style={{ padding: '0.25rem' }}>{s.message_count ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div style={cardStyle}>
        <h3 style={{ marginTop: 0 }}>Memories</h3>
        {memories.length === 0 && (
          <p style={{ color: '#666' }}>{memoriesError || 'No memories found.'}</p>
        )}
        {memories.map((m) => (
          <div
            key={m.id}
            style={{
              padding: '0.5rem 0',
              borderBottom: '1px solid #eee',
              fontSize: '0.875rem',
            }}
          >
            {m.content}
            {m.created_at && (
              <span style={{ color: '#999', fontSize: '0.75rem', marginLeft: '0.5rem' }}>
                {new Date(m.created_at).toLocaleString()}
              </span>
            )}
          </div>
        ))}
      </div>

      <div style={cardStyle}>
        <h3 style={{ marginTop: 0 }}>Handoff Summaries</h3>
        <p style={{ color: '#666', margin: 0 }}>Session handoff summaries will appear here.</p>
      </div>
    </div>
  );
}
