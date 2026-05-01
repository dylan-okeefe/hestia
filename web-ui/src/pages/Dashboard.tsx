import React, { useEffect, useState } from 'react';
import { fetchSessions, fetchTurns } from '../api/client';

interface Session {
  id: string;
  platform: string;
  platform_user: string;
  started_at: string | null;
  state: string | null;
  temperature: string | null;
}

interface Turn {
  id: string;
  state: string | null;
  started_at: string | null;
  iterations: number;
  error: string | null;
}

export default function Dashboard() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [turns, setTurns] = useState<Record<string, Turn[]>>({});
  const [turnsLoading, setTurnsLoading] = useState<string | null>(null);

  useEffect(() => {
    fetchSessions()
      .then((data) => {
        setSessions(data.sessions || []);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  const toggleExpand = async (sessionId: string) => {
    if (expanded === sessionId) {
      setExpanded(null);
      return;
    }
    setExpanded(sessionId);
    if (!turns[sessionId]) {
      setTurnsLoading(sessionId);
      try {
        const data = await fetchTurns(sessionId);
        setTurns((prev) => ({ ...prev, [sessionId]: data.turns || [] }));
      } catch (err) {
        setTurns((prev) => ({ ...prev, [sessionId]: [] }));
      } finally {
        setTurnsLoading(null);
      }
    }
  };

  return (
    <div style={{ padding: '1rem' }}>
      <h1>Sessions</h1>
      {loading && <p>Loading sessions…</p>}
      {error && <p style={{ color: 'red' }}>{error}</p>}
      {!loading && sessions.length === 0 && <p>No sessions found.</p>}
      {sessions.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #ccc', textAlign: 'left' }}>
              <th>ID</th>
              <th>Platform</th>
              <th>User</th>
              <th>Started</th>
              <th>State</th>
              <th>Temperature</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <React.Fragment key={s.id}>
                <tr
                  onClick={() => toggleExpand(s.id)}
                  style={{ cursor: 'pointer', borderBottom: '1px solid #eee' }}
                  data-testid="session-row"
                >
                  <td>{s.id}</td>
                  <td>{s.platform}</td>
                  <td>{s.platform_user}</td>
                  <td>{s.started_at ? new Date(s.started_at).toLocaleString() : '—'}</td>
                  <td>{s.state ?? '—'}</td>
                  <td>{s.temperature ?? '—'}</td>
                </tr>
                {expanded === s.id && (
                  <tr>
                    <td colSpan={6} style={{ padding: '0.5rem 1rem', background: '#f9f9f9' }}>
                      {turnsLoading === s.id ? (
                        <p>Loading turns…</p>
                      ) : (
                        <TurnList turns={turns[s.id] || []} />
                      )}
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function TurnList({ turns }: { turns: Turn[] }) {
  if (turns.length === 0) return <p>No turns for this session.</p>;
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr style={{ borderBottom: '1px solid #ddd', textAlign: 'left' }}>
          <th>Turn ID</th>
          <th>State</th>
          <th>Started</th>
          <th>Iterations</th>
          <th>Error</th>
        </tr>
      </thead>
      <tbody>
        {turns.map((t) => (
          <tr key={t.id} style={{ borderBottom: '1px solid #eee' }}>
            <td>{t.id}</td>
            <td>{t.state ?? '—'}</td>
            <td>{t.started_at ? new Date(t.started_at).toLocaleString() : '—'}</td>
            <td>{t.iterations}</td>
            <td style={{ color: t.error ? 'red' : undefined }}>{t.error ?? '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
