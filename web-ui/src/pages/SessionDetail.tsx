import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';

import { fetchSessionMessages } from '../api/client';
import PageCard from '../components/layout/PageCard';
import EmptyState from '../components/layout/EmptyState';
import LoadingSkeleton from '../components/layout/LoadingSkeleton';
import ErrorState from '../components/layout/ErrorState';
import { formatDate } from '../lib/format';
import { TEXT } from '../lib/text';
import './SessionDetail.css';

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
      setError(TEXT.sessionDetail.noSessionIdError);
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
      <div className="session-detail-page">
        <h1>{TEXT.sessionDetail.title}</h1>
        <PageCard>
          <LoadingSkeleton lines={5} />
        </PageCard>
      </div>
    );
  }

  if (error) {
    return (
      <div className="session-detail-page">
        <h1>{TEXT.sessionDetail.title}</h1>
        <PageCard>
          <ErrorState message={error} onRetry={() => window.location.reload()} />
        </PageCard>
        <p>
          <Link to="/knowledge">{TEXT.sessionDetail.backToKnowledge}</Link>
        </p>
      </div>
    );
  }

  return (
    <div className="session-detail-page">
      <h1>{TEXT.sessionDetail.title}</h1>

      <p>
        <Link to="/knowledge">{TEXT.sessionDetail.backToKnowledge}</Link>
      </p>

      {session && (
        <PageCard>
          <h3>{TEXT.sessionDetail.metadataTitle}</h3>
          <div className="session-detail-grid">
            <div className="session-detail-grid__label">{TEXT.sessionDetail.idLabel}</div>
            <div className="session-detail-grid__mono">{session.id}</div>
            <div className="session-detail-grid__label">{TEXT.sessionDetail.platformLabel}</div>
            <div>{session.platform}</div>
            <div className="session-detail-grid__label">{TEXT.sessionDetail.userLabel}</div>
            <div>{session.platform_user}</div>
            <div className="session-detail-grid__label">{TEXT.sessionDetail.startedLabel}</div>
            <div>{formatDate(session.started_at)}</div>
            <div className="session-detail-grid__label">{TEXT.sessionDetail.messagesLabel}</div>
            <div>{turns.length}</div>
          </div>
        </PageCard>
      )}

      <PageCard>
        <h3>{TEXT.sessionDetail.transcriptTitle}</h3>
        {turns.length === 0 && (
          <EmptyState title={TEXT.sessionDetail.emptyTitle} description={TEXT.sessionDetail.emptyDescription} />
        )}
        <div className="stack-md">
          {turns.map((t) => (
            <div
              key={t.id}
              className={`session-turn${t.error ? ' session-turn--error' : ''}`}
            >
              <div className="session-turn__header">
                <span className="session-turn__id">
                  {TEXT.sessionDetail.turnLabel(t.id)}
                </span>
                <span
                  className={`session-turn__state session-turn__state--${t.state === 'done' ? 'done' : t.state === 'failed' ? 'failed' : 'default'}`}
                >
                  {t.state ?? TEXT.common.unknown}
                </span>
              </div>
              <div className="session-turn__meta">
                {formatDate(t.started_at)} · {t.iterations} iteration{t.iterations === 1 ? '' : 's'}
              </div>
              {t.error && (
                <div className="session-turn__error">
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
