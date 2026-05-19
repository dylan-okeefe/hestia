import { useState } from 'react';
import { useApiQuery, useApiMutation } from '../hooks/useApi';
import {
  fetchSchedulerTasks,
  createTask,
  updateTask,
  deleteTask,
  runTaskNow,
} from '../api/client';
import PageCard from '../components/layout/PageCard';
import LoadingSkeleton from '../components/layout/LoadingSkeleton';
import ErrorState from '../components/layout/ErrorState';
import EmptyState from '../components/layout/EmptyState';
import CronBuilder from '../components/workflow-editor/CronBuilder';
import { formatDate, formatCron } from '../lib/format';
import { TEXT } from '../lib/text';

interface Task {
  id: string;
  description: string | null;
  prompt: string;
  cron_expression: string | null;
  last_run_at: string | null;
  next_run_at: string | null;
  last_error: string | null;
  enabled: boolean;
}

function getTaskName(task: Task): string {
  if (task.description) return task.description;
  try {
    const url = new URL(task.prompt);
    return url.hostname;
  } catch {
    return task.prompt;
  }
}

export default function Scheduler() {
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useApiQuery<{ tasks: Task[] }>('scheduler-tasks', fetchSchedulerTasks);

  const tasks = data?.tasks ?? [];

  const [modalOpen, setModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [form, setForm] = useState({
    description: '',
    prompt: '',
    cron_expression: '0 8 * * *',
    enabled: true,
  });
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [confirmRun, setConfirmRun] = useState<string | null>(null);

  const createMut = useApiMutation(createTask);
  const updateMut = useApiMutation((args: { id: string; payload: Partial<{ prompt: string; description: string; cron_expression: string; enabled: boolean }> }) => updateTask(args.id, args.payload));
  const deleteMut = useApiMutation(deleteTask);
  const runMut = useApiMutation(runTaskNow);

  const openCreate = () => {
    setEditingTask(null);
    setForm({ description: '', prompt: '', cron_expression: '0 8 * * *', enabled: true });
    setModalOpen(true);
  };

  const openEdit = (task: Task) => {
    setEditingTask(task);
    setForm({
      description: task.description ?? '',
      prompt: task.prompt,
      cron_expression: task.cron_expression ?? '0 8 * * *',
      enabled: task.enabled,
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    const payload = {
      description: form.description || undefined,
      prompt: form.prompt,
      cron_expression: form.cron_expression || undefined,
      enabled: form.enabled,
    };
    if (editingTask) {
      await updateMut.mutateAsync({ id: editingTask.id, payload });
    } else {
      await createMut.mutateAsync(payload);
    }
    setModalOpen(false);
    refetch();
  };

  const handleDelete = async (id: string) => {
    await deleteMut.mutateAsync(id);
    setConfirmDelete(null);
    refetch();
  };

  const handleRun = async (id: string) => {
    await runMut.mutateAsync(id);
    setConfirmRun(null);
    refetch();
  };

  return (
    <div style={{ padding: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h1 style={{ margin: 0 }}>{TEXT.scheduler.title}</h1>
        <button onClick={openCreate}>{TEXT.scheduler.createButton}</button>
      </div>

      {isLoading && (
        <PageCard>
          <LoadingSkeleton lines={4} height="2rem" />
        </PageCard>
      )}

      {isError && (
        <ErrorState message={error?.message ?? TEXT.scheduler.loadError} onRetry={refetch} />
      )}

      {!isLoading && !isError && tasks.length === 0 && (
        <EmptyState
          title={TEXT.scheduler.emptyTitle}
          description={TEXT.scheduler.emptyDescription}
          action={{ label: TEXT.scheduler.emptyAction, onClick: openCreate }}
        />
      )}

      {!isLoading && tasks.length > 0 && (
        <PageCard style={{ padding: 0, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #eee', textAlign: 'left', background: '#fafafa' }}>
                <th style={{ padding: '0.75rem 1rem' }}>{TEXT.scheduler.tableTask}</th>
                <th style={{ padding: '0.75rem 1rem' }}>{TEXT.scheduler.tableSchedule}</th>
                <th style={{ padding: '0.75rem 1rem' }}>{TEXT.scheduler.tableNextRun}</th>
                <th style={{ padding: '0.75rem 1rem' }}>{TEXT.scheduler.tableStatus}</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>{TEXT.scheduler.tableActions}</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((t) => (
                <tr key={t.id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                  <td style={{ padding: '0.75rem 1rem' }}>
                    <div style={{ fontWeight: 600 }}>{getTaskName(t)}</div>
                    <div style={{ fontSize: '0.8rem', color: '#888', wordBreak: 'break-all' }}>{t.prompt}</div>
                  </td>
                  <td style={{ padding: '0.75rem 1rem' }}>
                    {t.cron_expression ? formatCron(t.cron_expression) : '—'}
                  </td>
                  <td style={{ padding: '0.75rem 1rem' }}>{formatDate(t.next_run_at)}</td>
                  <td style={{ padding: '0.75rem 1rem' }}>
                    <span
                      style={{
                        display: 'inline-block',
                        padding: '0.15rem 0.5rem',
                        borderRadius: '12px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        background: t.enabled ? '#dcfce7' : '#f3f4f6',
                        color: t.enabled ? '#166534' : '#6b7280',
                      }}
                    >
                      {t.enabled ? TEXT.scheduler.statusEnabled : TEXT.scheduler.statusDisabled}
                    </span>
                    {t.last_error && (
                      <span
                        style={{
                          display: 'inline-block',
                          marginLeft: '0.25rem',
                          padding: '0.15rem 0.5rem',
                          borderRadius: '12px',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          background: '#fee2e2',
                          color: '#991b1b',
                        }}
                        title={t.last_error}
                      >
                        {TEXT.scheduler.statusError}
                      </span>
                    )}
                  </td>
                  <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                    <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                      <button onClick={() => setConfirmRun(t.id)} disabled={!t.enabled}>
                        {TEXT.scheduler.runNow}
                      </button>
                      <button onClick={() => openEdit(t)}>{TEXT.common.edit}</button>
                      <button
                        onClick={() => setConfirmDelete(t.id)}
                        style={{ color: '#ef4444', borderColor: '#ef4444' }}
                      >
                        {TEXT.common.delete}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </PageCard>
      )}

      {modalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setModalOpen(false)}
        >
          <div
            style={{ width: '90%', maxWidth: 480, maxHeight: '90vh', overflowY: 'auto', background: '#fff', border: '1px solid #eee', borderRadius: '8px', padding: '1rem' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ marginTop: 0 }}>{editingTask ? TEXT.scheduler.editTitle : TEXT.scheduler.createTitle}</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <label>
                {TEXT.scheduler.nameLabel}
                <input
                  value={form.description}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                  placeholder={TEXT.scheduler.namePlaceholder}
                  style={{ width: '100%', padding: '0.5rem', marginTop: '0.25rem' }}
                />
              </label>
              <label>
                {TEXT.scheduler.promptLabel}
                <textarea
                  rows={4}
                  value={form.prompt}
                  onChange={(e) => setForm((f) => ({ ...f, prompt: e.target.value }))}
                  placeholder={TEXT.scheduler.promptPlaceholder}
                  style={{ width: '100%', padding: '0.5rem', marginTop: '0.25rem', fontFamily: 'inherit' }}
                />
              </label>
              <label>
                {TEXT.scheduler.scheduleLabel}
                <div style={{ marginTop: '0.25rem' }}>
                  <CronBuilder
                    value={form.cron_expression}
                    onChange={(v) => setForm((f) => ({ ...f, cron_expression: v }))}
                  />
                </div>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
                />
                {TEXT.scheduler.enabledLabel}
              </label>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1rem' }}>
              <button onClick={() => setModalOpen(false)}>{TEXT.common.cancel}</button>
              <button onClick={handleSave} disabled={!form.prompt.trim()}>
                {editingTask ? TEXT.common.save : TEXT.common.create}
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmDelete && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setConfirmDelete(null)}
        >
          <div style={{ width: 360, textAlign: 'center', background: '#fff', border: '1px solid #eee', borderRadius: '8px', padding: '1rem' }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginTop: 0 }}>{TEXT.scheduler.deleteConfirmTitle}</h3>
            <p style={{ fontSize: '0.875rem', color: '#666' }}>
              {TEXT.scheduler.deleteConfirmDescription}
            </p>
            <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1rem' }}>
              <button onClick={() => setConfirmDelete(null)}>{TEXT.common.cancel}</button>
              <button onClick={() => handleDelete(confirmDelete)} style={{ color: '#ef4444', borderColor: '#ef4444' }}>
                {TEXT.common.delete}
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmRun && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setConfirmRun(null)}
        >
          <div style={{ width: 360, textAlign: 'center', background: '#fff', border: '1px solid #eee', borderRadius: '8px', padding: '1rem' }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginTop: 0 }}>{TEXT.scheduler.runNowConfirmTitle}</h3>
            <p style={{ fontSize: '0.875rem', color: '#666' }}>
              {TEXT.scheduler.runNowConfirmDescription}
            </p>
            <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1rem' }}>
              <button onClick={() => setConfirmRun(null)}>{TEXT.common.cancel}</button>
              <button onClick={() => handleRun(confirmRun)}>{TEXT.common.run}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
