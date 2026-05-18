import { useEffect, useState } from 'react';

import { fetchUserSessions, fetchStyleProfile, fetchMemoriesForUser, fetchHandoffs, deleteMemory } from '../api/client';
import { useCurrentUser } from '../hooks/useCurrentUser';
import PageCard from '../components/layout/PageCard';
import EmptyState from '../components/layout/EmptyState';
import LoadingSkeleton from '../components/layout/LoadingSkeleton';
import ErrorState from '../components/layout/ErrorState';
import { formatDate, formatRelativeDate, formatJson } from '../lib/format';

interface Session {
  id: string;
  platform: string;
  platform_user: string;
  started_at: string;
  message_count?: number;
}

interface Memory {
  id: string;
  content: string;
  tags?: string[];
  created_at?: string;
}

interface Handoff {
  session_id: string;
  summary: string;
  created_at: string;
}

export default function Knowledge() {
  const { user, isLoading: userLoading, error: userError } = useCurrentUser();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [style, setStyle] = useState<Record<string, unknown>>({});
  const [memories, setMemories] = useState<Memory[]>([]);
  const [handoffs, setHandoffs] = useState<Handoff[]>([]);
  const [memoriesError, setMemoriesError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingMemoryId, setDeletingMemoryId] = useState<string | null>(null);

  useEffect(() => {
    if (userLoading) return;
    if (!user) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    setMemoriesError(null);

    const load = async () => {
      try {
        const identity = user.identities?.[0];
        const platform = identity?.platform || 'cli';
        const platformUser = identity?.platform_user || 'default';

        const [sessionsData, styleData, memoriesData, handoffsData] = await Promise.all([
          fetchUserSessions(platform, platformUser, 10),
          fetchStyleProfile(platform, platformUser),
          fetchMemoriesForUser(platform, platformUser, 20).catch(() => null),
          fetchHandoffs(user.id).catch(() => ({ handoffs: [] })),
        ]);

        setSessions((sessionsData.sessions || []) as Session[]);
        setStyle(styleData.profile || {});
        if (memoriesData && memoriesData.memories) {
          setMemories(memoriesData.memories as Memory[]);
        } else if (memoriesData && Array.isArray(memoriesData)) {
          setMemories(memoriesData as Memory[]);
        } else {
          setMemories([]);
        }
        setHandoffs((handoffsData.handoffs || []) as Handoff[]);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [user, userLoading]);

  const handleDeleteMemory = async (memoryId: string) => {
    if (!window.confirm('Delete this memory?')) return;
    setDeletingMemoryId(memoryId);
    try {
      await deleteMemory(memoryId);
      setMemories((prev) => prev.filter((m) => m.id !== memoryId));
    } catch (err: any) {
      setMemoriesError(err.message);
    } finally {
      setDeletingMemoryId(null);
    }
  };

  if (userLoading || loading) {
    return (
      <div style={{ padding: '1rem' }}>
        <h1>What Hestia Knows About You</h1>
        <PageCard>
          <LoadingSkeleton lines={5} />
        </PageCard>
      </div>
    );
  }

  if (userError) {
    return (
      <div style={{ padding: '1rem' }}>
        <ErrorState
          message={userError}
          onRetry={userError.includes('Not authenticated') ? () => { window.location.href = '/login'; } : () => window.location.reload()}
        />
      </div>
    );
  }

  if (error && !user) {
    return (
      <div style={{ padding: '1rem' }}>
        <ErrorState message={error} onRetry={() => window.location.reload()} />
      </div>
    );
  }

  const styleMetrics = Object.entries(style);

  return (
    <div style={{ padding: '1rem' }}>
      <h1>What Hestia Knows About You</h1>

      {error && (
        <PageCard>
          <ErrorState message={error} onRetry={() => window.location.reload()} />
        </PageCard>
      )}

      <PageCard>
        <h3 style={{ marginTop: 0 }}>User Notes</h3>
        <p style={{ margin: '0 0 0.5rem', fontSize: '0.75rem', color: '#888' }}>
          Facts about you that Hestia sees in every conversation.
        </p>
        <p style={{ whiteSpace: 'pre-wrap', marginTop: 0 }}>
          {user?.notes || 'No notes saved.'}
        </p>
        <a href="/profile" style={{ fontSize: '0.875rem' }}>
          Edit notes on Profile →
        </a>
      </PageCard>

      <PageCard>
        <h3 style={{ marginTop: 0 }}>Style Profile</h3>
        <p style={{ margin: '0 0 0.5rem', fontSize: '0.75rem', color: '#888' }}>
          How Hestia thinks you communicate.
        </p>
        {styleMetrics.length === 0 && (
          <EmptyState
            title="No style metrics yet"
            description="Style profiling is disabled or hasn't collected enough data."
          />
        )}
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
                {typeof value === 'object' ? formatJson(value) : String(value)}
              </div>
            </div>
          </div>
        ))}
      </PageCard>

      <PageCard>
        <h3 style={{ marginTop: 0 }}>Session History</h3>
        {sessions.length === 0 && (
          <EmptyState title="No sessions found" description="Your conversation history will appear here." />
        )}
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
                  <td style={{ padding: '0.25rem' }}>{formatDate(s.started_at)}</td>
                  <td style={{ padding: '0.25rem' }}>{s.message_count ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </PageCard>

      <PageCard>
        <h3 style={{ marginTop: 0 }}>Memories</h3>
        <p style={{ margin: '0 0 0.5rem', fontSize: '0.75rem', color: '#888' }}>
          Facts Hestia has learned about you. You can delete any you disagree with.
        </p>
        {memoriesError && <p style={{ color: '#ef4444', fontSize: '0.875rem' }}>{memoriesError}</p>}
        {memories.length === 0 && (
          <EmptyState
            title="No memories yet"
            description="Hestia learns about you during conversations."
          />
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {memories.map((m) => (
            <div
              key={m.id}
              style={{
                padding: '0.75rem',
                border: '1px solid #eee',
                borderRadius: '6px',
                background: '#fafafa',
                fontSize: '0.875rem',
              }}
            >
              <div style={{ marginBottom: '0.5rem' }}>{m.content}</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                  {m.tags && m.tags.length > 0 && m.tags.map((tag) => (
                    <span
                      key={tag}
                      style={{
                        fontSize: '0.75rem',
                        padding: '0.125rem 0.375rem',
                        borderRadius: '999px',
                        background: '#e5e7eb',
                        color: '#374151',
                      }}
                    >
                      {tag}
                    </span>
                  ))}
                  {m.created_at && (
                    <span style={{ color: '#999', fontSize: '0.75rem' }}>
                      {formatDate(m.created_at)}
                    </span>
                  )}
                </div>
                <button
                  onClick={() => handleDeleteMemory(m.id)}
                  disabled={deletingMemoryId === m.id}
                  style={{ fontSize: '0.75rem', color: '#ef4444' }}
                >
                  {deletingMemoryId === m.id ? 'Deleting…' : 'Delete'}
                </button>
              </div>
            </div>
          ))}
        </div>
      </PageCard>

      <PageCard>
        <h3 style={{ marginTop: 0 }}>Handoff Summaries</h3>
        <p style={{ margin: '0 0 0.5rem', fontSize: '0.75rem', color: '#888' }}>
          What Hestia remembers from your last few sessions.
        </p>
        {handoffs.length === 0 && (
          <EmptyState
            title="No handoff summaries yet"
            description="These appear when Hestia carries context across sessions."
          />
        )}
        {handoffs.map((h) => (
          <div
            key={h.session_id}
            style={{
              padding: '0.5rem 0',
              borderBottom: '1px solid #eee',
              fontSize: '0.875rem',
            }}
          >
            <div style={{ fontWeight: 'bold', marginBottom: '0.25rem' }}>
              Session {h.session_id.slice(0, 8)}…
            </div>
            <div style={{ color: '#555', marginBottom: '0.25rem' }}>{h.summary}</div>
            {h.created_at && (
              <span style={{ color: '#999', fontSize: '0.75rem' }}>
                {formatRelativeDate(h.created_at)}
              </span>
            )}
          </div>
        ))}
      </PageCard>
    </div>
  );
}
