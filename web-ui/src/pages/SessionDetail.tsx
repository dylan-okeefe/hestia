import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';

import { fetchSessionMessages } from '../api/client';
import PageCard from '../components/layout/PageCard';
import EmptyState from '../components/layout/EmptyState';
import LoadingSkeleton from '../components/layout/LoadingSkeleton';
import ErrorState from '../components/layout/ErrorState';
import { formatDate } from '../lib/format';

interface Turn {
  id: string;
  state: string | null;
  started_at: string | null;
  iterations: number;
  error: string | null;
}

interface SessionInfo {
  id: string;
  platform: string;
  platform_user: string;
  started_at: string | null;
}

export default function SessionDetail() {
  const { id } = useParams<{ id: string }>();
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) {
      setError('No session ID provided');
      setLoading(false);
      return;
    }

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchSessionMessages(id);
        setSession(data.session);
        setTurns(data.turns || []);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [id]);

  if (loading) {
    return (
      <div style={{ padding: '1rem' }}>
        <h1>Session Detail</h1>
        <PageCard>
          <LoadingSkeleton lines={5} />
        </PageCard>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '1rem' }}>
        <h1>Session Detail</h1>
        <PageCard>
          <ErrorState message={error} onRetry={() => window.location.reload()} />
        </PageCard>
        <p>
          <Link to="/knowledge">← Back to Knowledge</Link>
        </p>
      </div>
    );
  }

  return (
    <div style={{ padding: '1rem' }}>
      <h1>Session Detail</h1>

      <p>
        <Link to="/knowledge">← Back to Knowledge</Link>
      </p>

      {session && (
        <PageCard>
          <h3 style={{ marginTop: 0 }}>Session Metadata</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: '0.5rem 1rem', fontSize: '0.875rem' }}>
            <div style={{ color: '#666' }}>ID</div>
            <div style={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>{session.id}</div>
            <div style={{ color: '#666' }}>Platform</div>
            <div>{session.platform}</div>
            <div style={{ color: '#666' }}>User</div>
            <div>{session.platform_user}</div>
            <div style={{ color: '#666' }}>Started</div>
            <div>{formatDate(session.started_at)}</div>
            <div style={{ color: '#666' }}>Messages</div>
            <div>{turns.length}</div>
          </div>
        </PageCard>
      )}

      <PageCard>
        <h3 style={{ marginTop: 0 }}>Conversation Transcript</h3>
        {turns.length === 0 && (
          <EmptyState title="No turns found" description="This session has no conversation turns." />
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {turns.map((t) => (
            <div
              key={t.id}
              style={{
                padding: '0.75rem',
                border: '1px solid #eee',
                borderRadius: '6px',
                background: t.error ? '#fef2f2' : '#fafafa',
                borderLeft: t.error ? '3px solid #ef4444' : '3px solid #e5e7eb',
                fontSize: '0.875rem',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
                <span style={{ fontWeight: 'bold', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                  Turn {t.id.slice(0, 8)}…
                </span>
                <span
                  style={{
                    fontSize: '0.75rem',
                    padding: '0.125rem 0.375rem',
                    borderRadius: '4px',
                    background: t.state === 'done' ? '#dcfce7' : t.state === 'failed' ? '#fee2e2' : '#e5e7eb',
                    color: t.state === 'done' ? '#166534' : t.state === 'failed' ? '#991b1b' : '#374151',
                  }}
                >
                  {t.state ?? 'unknown'}
                </span>
              </div>
              <div style={{ color: '#666', fontSize: '0.75rem', marginBottom: '0.25rem' }}>
                {formatDate(t.started_at)} · {t.iterations} iteration{t.iterations === 1 ? '' : 's'}
              </div>
              {t.error && (
                <div style={{ color: '#ef4444', fontSize: '0.875rem', whiteSpace: 'pre-wrap' }}>
                  {t.error}
                </div>
              )}
            </div>
          ))}
        </div>
      </PageCard>
    </div>
  );
}
