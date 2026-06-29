import { useEffect, useMemo, useState } from 'react';

import {
  fetchUserSessions,
  fetchStyleProfile,
  fetchMemoriesForUser,
  fetchHandoffs,
  fetchTopics,
  createTopic,
  renameTopic,
  deleteTopic,
  updateMemory,
  pinMemory,
  unpinMemory,
  softDeleteMemory,
  restoreMemory,
  deleteMemory,
  type Memory as ApiMemory,
  type Topic as ApiTopic,
} from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useCurrentUser } from '../hooks/useCurrentUser';
import PageCard from '../components/layout/PageCard';
import EmptyState from '../components/layout/EmptyState';
import LoadingSkeleton from '../components/layout/LoadingSkeleton';
import ErrorState from '../components/layout/ErrorState';
import Modal from '../components/Modal';
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

interface Handoff {
  session_id: string;
  summary: string;
  created_at: string;
}

interface Topic extends ApiTopic {}
interface Memory extends ApiMemory {}

export default function Knowledge() {
  const { logout } = useAuth();
  const { user, isLoading: userLoading, error: userError } = useCurrentUser();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [style, setStyle] = useState<Record<string, unknown>>({});
  const [memories, setMemories] = useState<Memory[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [handoffs, setHandoffs] = useState<Handoff[]>([]);
  const [memoriesError, setMemoriesError] = useState<string | null>(null);
  const [topicsError, setTopicsError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showTrash, setShowTrash] = useState(false);
  const [editingMemory, setEditingMemory] = useState<Memory | null>(null);
  const [newTopicName, setNewTopicName] = useState('');
  const [renamingTopic, setRenamingTopic] = useState<Topic | null>(null);
  const [busyMemoryIds, setBusyMemoryIds] = useState<Set<string>>(new Set());
  const [busyTopicIds, setBusyTopicIds] = useState<Set<string>>(new Set());

  const identity = useMemo(() => {
    if (!user) return null;
    return user.identities?.[0] || { platform: 'cli', platform_user: 'default' };
  }, [user]);

  useEffect(() => {
    if (userLoading) return;
    if (!user || !identity) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    setMemoriesError(null);
    setTopicsError(null);

    const load = async () => {
      try {
        const [sessionsData, styleData, memoriesData, handoffsData, topicsData] = await Promise.all([
          fetchUserSessions(identity.platform, identity.platform_user, 10),
          fetchStyleProfile(identity.platform, identity.platform_user),
          fetchMemoriesForUser(identity.platform, identity.platform_user, 100, true).catch(() => ({ memories: [] })),
          fetchHandoffs(user.id).catch(() => ({ handoffs: [] })),
          fetchTopics(identity.platform, identity.platform_user).catch(() => ({ topics: [] })),
        ]);

        setSessions((sessionsData.sessions || []) as Session[]);
        setStyle(styleData.profile || {});
        setMemories(memoriesData.memories || []);
        setHandoffs((handoffsData.handoffs || []) as Handoff[]);
        setTopics(topicsData.topics || []);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [user, userLoading, identity]);

  const refreshMemoriesAndTopics = async () => {
    if (!identity) return;
    try {
      const [memoriesData, topicsData] = await Promise.all([
        fetchMemoriesForUser(identity.platform, identity.platform_user, 100, showTrash || true),
        fetchTopics(identity.platform, identity.platform_user),
      ]);
      setMemories(memoriesData.memories || []);
      setTopics(topicsData.topics || []);
    } catch (err: any) {
      setMemoriesError(err.message);
    }
  };

  const withBusyMemory = async (memoryId: string, fn: () => Promise<void>) => {
    setBusyMemoryIds((prev) => new Set(prev).add(memoryId));
    setActionError(null);
    try {
      await fn();
    } catch (err: any) {
      setActionError(err.message);
    } finally {
      setBusyMemoryIds((prev) => {
        const next = new Set(prev);
        next.delete(memoryId);
        return next;
      });
    }
  };

  const handlePin = async (memory: Memory) => {
    await withBusyMemory(memory.id, async () => {
      if (memory.is_pinned) {
        await unpinMemory(memory.id);
      } else {
        await pinMemory(memory.id);
      }
      await refreshMemoriesAndTopics();
    });
  };

  const handleSoftDelete = async (memory: Memory) => {
    if (!window.confirm(TEXT.knowledge.memoriesSoftDeleteConfirm)) return;
    await withBusyMemory(memory.id, async () => {
      await softDeleteMemory(memory.id);
      await refreshMemoriesAndTopics();
    });
  };

  const handleRestore = async (memory: Memory) => {
    if (!window.confirm(TEXT.knowledge.memoriesRestoreConfirm)) return;
    await withBusyMemory(memory.id, async () => {
      await restoreMemory(memory.id);
      await refreshMemoriesAndTopics();
    });
  };

  const handleHardDelete = async (memory: Memory) => {
    if (!window.confirm(TEXT.knowledge.memoriesDeleteConfirm)) return;
    await withBusyMemory(memory.id, async () => {
      await deleteMemory(memory.id);
      await refreshMemoriesAndTopics();
    });
  };

  const handleCreateTopic = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!identity || !newTopicName.trim()) return;
    setTopicsError(null);
    try {
      await createTopic(identity.platform, identity.platform_user, newTopicName.trim());
      setNewTopicName('');
      await refreshMemoriesAndTopics();
    } catch (err: any) {
      setTopicsError(err.message);
    }
  };

  const handleRenameTopic = async (topicId: string, newName: string) => {
    setBusyTopicIds((prev) => new Set(prev).add(topicId));
    setTopicsError(null);
    try {
      await renameTopic(topicId, newName.trim());
      setRenamingTopic(null);
      await refreshMemoriesAndTopics();
    } catch (err: any) {
      setTopicsError(err.message);
    } finally {
      setBusyTopicIds((prev) => {
        const next = new Set(prev);
        next.delete(topicId);
        return next;
      });
    }
  };

  const handleDeleteTopic = async (topic: Topic) => {
    if (!window.confirm(`Delete topic "${topic.name}"? Memories will keep their content but lose this scope.`)) return;
    setBusyTopicIds((prev) => new Set(prev).add(topic.id));
    setTopicsError(null);
    try {
      await deleteTopic(topic.id);
      await refreshMemoriesAndTopics();
    } catch (err: any) {
      setTopicsError(err.message);
    } finally {
      setBusyTopicIds((prev) => {
        const next = new Set(prev);
        next.delete(topic.id);
        return next;
      });
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
  const activeMemories = memories.filter((m) => m.is_active);
  const deletedMemories = memories.filter((m) => !m.is_active);
  const globalMemories = activeMemories.filter((m) => m.is_global);
  const topicMemories = activeMemories.filter((m) => !m.is_global);

  const topicMap = new Map(topics.map((t) => [t.id, t]));

  return (
    <div className="knowledge-page">
      <h1>{TEXT.knowledge.title}</h1>

      {(error || actionError) && (
        <PageCard>
          <ErrorState message={error || actionError || ''} onRetry={() => window.location.reload()} />
        </PageCard>
      )}

      <div className="knowledge-layout">
        <div className="stack-md">
          <PageCard>
            <h3>{TEXT.knowledge.memoriesTopicManageTitle}</h3>
            <p className="text-xs text-muted mb-2">
              {TEXT.knowledge.memoriesTopicManageDescription}
            </p>
            {topicsError && <p className="text-small text-danger">{topicsError}</p>}
            <form onSubmit={handleCreateTopic} className="knowledge-topic-form">
              <input
                type="text"
                value={newTopicName}
                onChange={(e) => setNewTopicName(e.target.value)}
                placeholder={TEXT.knowledge.memoriesCreateTopicPlaceholder}
                className="form-input"
              />
              <button
                type="submit"
                disabled={!newTopicName.trim()}
                className="knowledge-topic-form__button"
              >
                {TEXT.knowledge.memoriesCreateTopicButton}
              </button>
            </form>
            {topics.length === 0 && (
              <EmptyState
                title={TEXT.knowledge.memoriesTopicEmptyTitle}
                description={TEXT.knowledge.memoriesTopicEmptyDescription}
              />
            )}
            {topics.length > 0 && (
              <ul className="knowledge-topic-list">
                {topics.map((topic) => (
                  <li key={topic.id} className="knowledge-topic-item">
                    {renamingTopic?.id === topic.id ? (
                      <form
                        onSubmit={(e) => {
                          e.preventDefault();
                          handleRenameTopic(topic.id, renamingTopic.name);
                        }}
                        className="knowledge-topic-rename-form"
                      >
                        <input
                          type="text"
                          value={renamingTopic.name}
                          onChange={(e) => setRenamingTopic({ ...renamingTopic, name: e.target.value })}
                          className="form-input"
                          autoFocus
                        />
                        <button type="submit" className="text-small" disabled={!renamingTopic.name.trim()}>
                          {TEXT.common.save}
                        </button>
                        <button
                          type="button"
                          onClick={() => setRenamingTopic(null)}
                          className="text-small text-muted"
                        >
                          {TEXT.common.cancel}
                        </button>
                      </form>
                    ) : (
                      <>
                        <span className="knowledge-topic-name">{topic.name}</span>
                        <div className="row-sm">
                          <button
                            onClick={() => setRenamingTopic(topic)}
                            className="text-xs text-muted"
                            disabled={busyTopicIds.has(topic.id)}
                          >
                            {TEXT.knowledge.memoriesTopicRename}
                          </button>
                          <button
                            onClick={() => handleDeleteTopic(topic)}
                            className="text-xs text-danger"
                            disabled={busyTopicIds.has(topic.id)}
                          >
                            {TEXT.knowledge.memoriesTopicDelete}
                          </button>
                        </div>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </PageCard>

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
        </div>

        <div className="stack-md">
          <PageCard>
            <div className="row-between mb-4">
              <div>
                <h3>{TEXT.knowledge.memoriesTitle}</h3>
                <p className="text-xs text-muted">
                  {TEXT.knowledge.memoriesDescription}
                </p>
              </div>
              <div className="row-sm">
                <button
                  onClick={() => setShowTrash((prev) => !prev)}
                  className={showTrash ? 'knowledge-tag knowledge-tag--active' : 'knowledge-tag'}
                >
                  {TEXT.knowledge.memoriesSectionTrash}
                </button>
              </div>
            </div>
            {memoriesError && <p className="text-small text-danger">{memoriesError}</p>}

            {!showTrash && (
              <div className="stack-md">
                <MemorySection
                  title={TEXT.knowledge.memoriesSectionGlobal}
                  memories={globalMemories}
                  topics={topics}
                  topicMap={topicMap}
                  busyMemoryIds={busyMemoryIds}
                  onEdit={setEditingMemory}
                  onPin={handlePin}
                  onSoftDelete={handleSoftDelete}
                  onRestore={handleRestore}
                  onHardDelete={handleHardDelete}
                />
                {topics.map((topic) => {
                  const topicMemoryList = topicMemories.filter((m) => m.topic_ids.includes(topic.id));
                  return (
                    <MemorySection
                      key={topic.id}
                      title={TEXT.knowledge.memoriesSectionTopic(topic.name)}
                      memories={topicMemoryList}
                      topics={topics}
                      topicMap={topicMap}
                      busyMemoryIds={busyMemoryIds}
                      onEdit={setEditingMemory}
                      onPin={handlePin}
                      onSoftDelete={handleSoftDelete}
                      onRestore={handleRestore}
                      onHardDelete={handleHardDelete}
                    />
                  );
                })}
                {activeMemories.length === 0 && (
                  <EmptyState
                    title={TEXT.knowledge.memoriesEmptyTitle}
                    description={TEXT.knowledge.memoriesEmptyDescription}
                  />
                )}
              </div>
            )}

            {showTrash && (
              <div className="stack-md">
                {deletedMemories.length === 0 && (
                  <EmptyState
                    title={TEXT.knowledge.memoriesTrashEmptyTitle}
                    description={TEXT.knowledge.memoriesTrashEmptyDescription}
                  />
                )}
                {deletedMemories.map((m) => (
                  <MemoryCard
                    key={m.id}
                    memory={m}
                    topics={topics}
                    topicMap={topicMap}
                    busy={busyMemoryIds.has(m.id)}
                    onEdit={setEditingMemory}
                    onPin={handlePin}
                    onSoftDelete={handleSoftDelete}
                    onRestore={handleRestore}
                    onHardDelete={handleHardDelete}
                  />
                ))}
              </div>
            )}
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

      {editingMemory && (
        <MemoryEditModal
          memory={editingMemory}
          topics={topics}
          onClose={() => setEditingMemory(null)}
          onSave={async (updates) => {
            await withBusyMemory(editingMemory.id, async () => {
              await updateMemory(editingMemory.id, updates);
              setEditingMemory(null);
              await refreshMemoriesAndTopics();
            });
          }}
        />
      )}
    </div>
  );
}

interface MemorySectionProps {
  title: string;
  memories: Memory[];
  topics: Topic[];
  topicMap: Map<string, Topic>;
  busyMemoryIds: Set<string>;
  onEdit: (memory: Memory) => void;
  onPin: (memory: Memory) => void;
  onSoftDelete: (memory: Memory) => void;
  onRestore: (memory: Memory) => void;
  onHardDelete: (memory: Memory) => void;
}

function MemorySection({
  title,
  memories,
  topics,
  topicMap,
  busyMemoryIds,
  onEdit,
  onPin,
  onSoftDelete,
  onRestore,
  onHardDelete,
}: MemorySectionProps) {
  if (memories.length === 0) return null;
  return (
    <div className="knowledge-memory-section">
      <h4 className="knowledge-memory-section__title">{title}</h4>
      <div className="stack-md">
        {memories.map((m) => (
          <MemoryCard
            key={m.id}
            memory={m}
            topics={topics}
            topicMap={topicMap}
            busy={busyMemoryIds.has(m.id)}
            onEdit={onEdit}
            onPin={onPin}
            onSoftDelete={onSoftDelete}
            onRestore={onRestore}
            onHardDelete={onHardDelete}
          />
        ))}
      </div>
    </div>
  );
}

interface MemoryCardProps {
  memory: Memory;
  topics: Topic[];
  topicMap: Map<string, Topic>;
  busy: boolean;
  onEdit: (memory: Memory) => void;
  onPin: (memory: Memory) => void;
  onSoftDelete: (memory: Memory) => void;
  onRestore: (memory: Memory) => void;
  onHardDelete: (memory: Memory) => void;
}

function MemoryCard({
  memory,
  topicMap,
  busy,
  onEdit,
  onPin,
  onSoftDelete,
  onRestore,
  onHardDelete,
}: MemoryCardProps) {
  const topicBadges = memory.is_global
    ? []
    : memory.topic_ids
        .map((id) => topicMap.get(id))
        .filter((t): t is Topic => t !== undefined);

  return (
    <div className={`knowledge-memory-card ${!memory.is_active ? 'knowledge-memory-card--deleted' : ''}`}>
      <div className="knowledge-memory-card__content">{memory.content}</div>
      <div className="knowledge-memory-card__meta">
        <div className="row-sm row-center flex-wrap">
          {memory.is_global && (
            <span className="knowledge-scope-badge knowledge-scope-badge--global">
              {TEXT.knowledge.memoriesScopeGlobal}
            </span>
          )}
          {topicBadges.map((topic) => (
            <span key={topic.id} className="knowledge-scope-badge knowledge-scope-badge--topic">
              {topic.name}
            </span>
          ))}
          {memory.tags && memory.tags.length > 0 && memory.tags.map((tag) => (
            <span key={tag} className="knowledge-tag-badge">
              {tag}
            </span>
          ))}
        </div>
        <div className="knowledge-memory-card__timestamps text-xs text-muted">
          {memory.session_id && (
            <span>{TEXT.knowledge.memoriesSourceSession(memory.session_id)}</span>
          )}
          {memory.created_at && (
            <span>{TEXT.knowledge.memoriesCreated(formatDate(memory.created_at))}</span>
          )}
          {memory.last_recalled_at && (
            <span>{TEXT.knowledge.memoriesRecalled(formatDate(memory.last_recalled_at))}</span>
          )}
        </div>
      </div>
      <div className="knowledge-memory-card__actions">
        <button
          onClick={() => onEdit(memory)}
          disabled={busy}
          className="text-xs"
        >
          {TEXT.common.edit}
        </button>
        <button
          onClick={() => onPin(memory)}
          disabled={busy}
          className={memory.is_pinned ? 'text-xs text-warning' : 'text-xs text-muted'}
        >
          {memory.is_pinned ? TEXT.knowledge.memoriesUnpin : TEXT.knowledge.memoriesPin}
        </button>
        {memory.is_active ? (
          <button
            onClick={() => onSoftDelete(memory)}
            disabled={busy}
            className="text-xs text-danger"
          >
            {TEXT.knowledge.memoriesDelete}
          </button>
        ) : (
          <button
            onClick={() => onRestore(memory)}
            disabled={busy}
            className="text-xs text-success"
          >
            {TEXT.knowledge.memoriesRestore}
          </button>
        )}
        {!memory.is_active && (
          <button
            onClick={() => onHardDelete(memory)}
            disabled={busy}
            className="text-xs text-danger"
          >
            {TEXT.common.delete}
          </button>
        )}
      </div>
    </div>
  );
}

interface MemoryEditModalProps {
  memory: Memory;
  topics: Topic[];
  onClose: () => void;
  onSave: (updates: Partial<Pick<Memory, 'content' | 'tags' | 'is_global' | 'topic_ids'>>) => void;
}

function MemoryEditModal({ memory, topics, onClose, onSave }: MemoryEditModalProps) {
  const [content, setContent] = useState(memory.content);
  const [tags, setTags] = useState(memory.tags.join(', '));
  const [isGlobal, setIsGlobal] = useState(memory.is_global);
  const [selectedTopicIds, setSelectedTopicIds] = useState<Set<string>>(new Set(memory.topic_ids));
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    const tagList = tags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);
    await onSave({
      content,
      tags: tagList,
      is_global: isGlobal,
      topic_ids: isGlobal ? [] : Array.from(selectedTopicIds),
    });
    setSaving(false);
  };

  return (
    <Modal isOpen title={TEXT.knowledge.memoriesEditTitle} onClose={onClose}>
      <div className="stack-md">
        <div>
          <label className="knowledge-edit-label">{TEXT.knowledge.memoriesContentLabel}</label>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="form-textarea"
            rows={4}
          />
        </div>
        <div>
          <label className="knowledge-edit-label">{TEXT.knowledge.memoriesTagsLabel}</label>
          <input
            type="text"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            className="form-input"
            placeholder="tag1, tag2, tag3"
          />
        </div>
        <div>
          <label className="knowledge-edit-label">{TEXT.knowledge.memoriesScopeLabel}</label>
          <div className="knowledge-scope-toggle">
            <button
              type="button"
              onClick={() => setIsGlobal(true)}
              className={isGlobal ? 'knowledge-scope-toggle__option--active' : 'knowledge-scope-toggle__option'}
            >
              {TEXT.knowledge.memoriesScopeGlobal}
            </button>
            <button
              type="button"
              onClick={() => setIsGlobal(false)}
              className={!isGlobal ? 'knowledge-scope-toggle__option--active' : 'knowledge-scope-toggle__option'}
            >
              {TEXT.knowledge.memoriesScopeTopic}
            </button>
          </div>
        </div>
        {!isGlobal && (
          <div>
            <label className="knowledge-edit-label">{TEXT.knowledge.memoriesAddTopicLabel}</label>
            <div className="knowledge-topic-checkboxes">
              {topics.length === 0 && (
                <p className="text-small text-muted">{TEXT.knowledge.memoriesTopicEmptyDescription}</p>
              )}
              {topics.map((topic) => (
                <label key={topic.id} className="knowledge-topic-checkbox">
                  <input
                    type="checkbox"
                    checked={selectedTopicIds.has(topic.id)}
                    onChange={(e) => {
                      const next = new Set(selectedTopicIds);
                      if (e.target.checked) {
                        next.add(topic.id);
                      } else {
                        next.delete(topic.id);
                      }
                      setSelectedTopicIds(next);
                    }}
                  />
                  <span>{topic.name}</span>
                </label>
              ))}
            </div>
          </div>
        )}
        <div className="row-md justify-end">
          <button onClick={onClose} className="text-small" disabled={saving}>
            {TEXT.common.cancel}
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !content.trim()}
            className="knowledge-save-button"
          >
            {saving ? TEXT.common.saving : TEXT.common.save}
          </button>
        </div>
      </div>
    </Modal>
  );
}
