import { useEffect, useState } from 'react';

import { fetchUserSessions, fetchStyleProfile, fetchMemoriesForUser, fetchHandoffs, deleteMemory } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useCurrentUser } from '../hooks/useCurrentUser';
import PageCard from '../components/layout/PageCard';
import EmptyState from '../components/layout/EmptyState';
import LoadingSkeleton from '../components/layout/LoadingSkeleton';
import ErrorState from '../components/layout/ErrorState';
import { formatDate, formatRelativeDate, formatJson } from '../lib/format';
import { TEXT } from '../lib/text';
import './Knowledge.css';

interface Session {
  id: string;
  platform: string;
  platform_user: string;
  title: string | null;
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
  const { logout } = useAuth();
  const { user, isLoading: userLoading, error: userError } = useCurrentUser();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [style, setStyle] = useState<Record<string, unknown>>({});
  const [memories, setMemories] = useState<Memory[]>([]);
  const [handoffs, setHandoffs] = useState<Handoff[]>([]);
  const [memoriesError, setMemoriesError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingMemoryId, setDeletingMemoryId] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);

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
    if (!window.confirm(TEXT.knowledge.memoriesDeleteConfirm)) return;
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
      <div className="knowledge-page">
        <h1>{TEXT.knowledge.title}</h1>
        <PageCard>
          <LoadingSkeleton lines={5} />
        </PageCard>
      </div>
    );
  }

  if (userError) {
    return (
      <div className="knowledge-page">
        <ErrorState
          message={userError}
          onRetry={userError.includes('Not authenticated') ? () => { logout(); window.location.href = '/'; } : () => window.location.reload()}
        />
      </div>
    );
  }

  if (error && !user) {
    return (
      <div className="knowledge-page">
        <ErrorState message={error} onRetry={() => window.location.reload()} />
      </div>
    );
  }

  const styleMetrics = Object.entries(style);

  const filteredMemories =
    selectedTags.length > 0
      ? memories.filter((m) => selectedTags.every((tag) => m.tags?.includes(tag)))
      : memories;

  return (
    <div className="knowledge-page">
      <h1>{TEXT.knowledge.title}</h1>

      {error && (
        <PageCard>
          <ErrorState message={error} onRetry={() => window.location.reload()} />
        </PageCard>
      )}

      <div className="knowledge-layout">
      <PageCard>
        <h3>{TEXT.knowledge.notesTitle}</h3>
        <p className="text-xs text-muted mb-2">
          {TEXT.knowledge.notesDescription}
        </p>
        <p className="whitespace-pre-wrap mt-0">
          {user?.notes || TEXT.knowledge.noNotesSaved}
        </p>
        <a href="/profile" className="text-small">
          {TEXT.knowledge.editNotesLink}
        </a>
      </PageCard>

      <PageCard>
        <h3>{TEXT.knowledge.styleTitle}</h3>
        <p className="text-xs text-muted mb-2">
          {TEXT.knowledge.styleDescription}
        </p>
        {styleMetrics.length === 0 && (
          <EmptyState
            title={TEXT.knowledge.styleEmptyTitle}
            description={TEXT.knowledge.styleEmptyDescription}
          />
        )}
        {styleMetrics.map(([key, value]) => (
          <div
            key={key}
            className="knowledge-style-row"
          >
            <div>
              <strong>{key}</strong>
              <div className="text-small text-secondary">
                {typeof value === 'object' ? formatJson(value) : String(value)}
              </div>
            </div>
          </div>
        ))}
      </PageCard>

      <PageCard>
        <h3>{TEXT.knowledge.sessionsTitle}</h3>
        {sessions.length === 0 && (
          <EmptyState title={TEXT.knowledge.sessionsEmptyTitle} description={TEXT.knowledge.sessionsEmptyDescription} />
        )}
        {sessions.length > 0 && (
          <table className="knowledge-table">
            <thead>
              <tr>
                <th>Session</th>
                <th>Title</th>
                <th>Platform</th>
                <th>Start</th>
                <th>Messages</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.id} onClick={() => window.location.href = `/sessions/${s.id}`}>
                  <td className="knowledge-table__mono"><a href={`/sessions/${s.id}`} className="no-underline">{s.id.slice(0, 8)}…</a></td>
                  <td>{s.title ?? '—'}</td>
                  <td>{s.platform}</td>
                  <td>{formatDate(s.started_at)}</td>
                  <td>{s.message_count ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </PageCard>

      <PageCard>
        <h3>{TEXT.knowledge.memoriesTitle}</h3>
        <p className="text-xs text-muted mb-2">
          {TEXT.knowledge.memoriesDescription}
        </p>
        {memoriesError && <p className="text-small text-danger">{memoriesError}</p>}
        {memories.length === 0 && (
          <EmptyState
            title={TEXT.knowledge.memoriesEmptyTitle}
            description={TEXT.knowledge.memoriesEmptyDescription}
          />
        )}
        {memories.length > 0 && (
          <div className="mb-4">
            <div className="row-sm row-center flex-wrap">
              {Array.from(new Set(memories.flatMap((m) => m.tags || []))).sort().map((tag) => {
                const active = selectedTags.includes(tag);
                return (
                  <button
                    key={tag}
                    onClick={() => {
                      setSelectedTags((prev) =>
                        active ? prev.filter((t) => t !== tag) : [...prev, tag]
                      );
                    }}
                    className={active ? 'knowledge-tag knowledge-tag--active' : 'knowledge-tag'}
                  >
                    {tag}
                  </button>
                );
              })}
              {selectedTags.length > 0 && (
                <button
                  onClick={() => setSelectedTags([])}
                  className="knowledge-tag-clear"
                >
                  {TEXT.knowledge.tagFilterClear}
                </button>
              )}
            </div>
            <p className="text-xs text-muted mt-1">
              {TEXT.knowledge.tagFilterShowing(filteredMemories.length, memories.length)}
            </p>
          </div>
        )}
        <div className="stack-md">
          {filteredMemories.map((m) => (
            <div
              key={m.id}
              className="knowledge-memory-card"
            >
              <div className="mb-2">{m.content}</div>
              <div className="row-between">
                <div className="row-sm row-center flex-wrap">
                  {m.tags && m.tags.length > 0 && m.tags.map((tag) => (
                    <span
                      key={tag}
                      className="knowledge-memory-tag"
                    >
                      {tag}
                    </span>
                  ))}
                  {m.created_at && (
                    <span className="text-muted text-xs">
                      {formatDate(m.created_at)}
                    </span>
                  )}
                </div>
                <button
                  onClick={() => handleDeleteMemory(m.id)}
                  disabled={deletingMemoryId === m.id}
                  className="text-xs text-danger"
                >
                  {deletingMemoryId === m.id ? TEXT.common.deleting : TEXT.common.delete}
                </button>
              </div>
            </div>
          ))}
        </div>
      </PageCard>

      <PageCard>
        <h3>{TEXT.knowledge.handoffsTitle}</h3>
        <p className="text-xs text-muted mb-2">
          {TEXT.knowledge.handoffsDescription}
        </p>
        {handoffs.length === 0 && (
          <EmptyState
            title={TEXT.knowledge.handoffsEmptyTitle}
            description={TEXT.knowledge.handoffsEmptyDescription}
          />
        )}
        {handoffs.map((h) => (
          <div
            key={h.session_id}
            className="knowledge-handoff-row"
          >
            <div className="font-bold mb-1">
              Session {h.session_id.slice(0, 8)}…
            </div>
            <div className="text-secondary mb-1">{h.summary}</div>
            {h.created_at && (
              <span className="text-muted text-xs">
                {formatRelativeDate(h.created_at)}
              </span>
            )}
          </div>
        ))}
      </PageCard>
      </div>
    </div>
  );
}
