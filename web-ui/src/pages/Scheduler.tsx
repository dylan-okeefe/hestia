import { useState } from 'react';
import { useApiQuery, useApiMutation } from '../hooks/useApi';
import { useToast } from '../hooks/useToast';
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
import './Scheduler.css';

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
  const { addToast } = useToast();
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
    try {
      if (editingTask) {
        await updateMut.mutateAsync({ id: editingTask.id, payload });
        addToast({ message: 'Task updated', type: 'success', duration: 3000 });
      } else {
        await createMut.mutateAsync(payload);
        addToast({ message: 'Task created', type: 'success', duration: 3000 });
      }
      setModalOpen(false);
      refetch();
    } catch (err: any) {
      addToast({ message: err.message || 'Save failed', type: 'error', duration: 5000 });
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteMut.mutateAsync(id);
      addToast({ message: 'Task deleted', type: 'success', duration: 3000 });
      setConfirmDelete(null);
      refetch();
    } catch (err: any) {
      addToast({ message: err.message || 'Delete failed', type: 'error', duration: 5000 });
    }
  };

  const handleRun = async (id: string) => {
    try {
      await runMut.mutateAsync(id);
      addToast({ message: 'Task triggered', type: 'success', duration: 3000 });
      setConfirmRun(null);
      refetch();
    } catch (err: any) {
      addToast({ message: err.message || 'Run failed', type: 'error', duration: 5000 });
    }
  };

  return (
    <div className="scheduler-page">
      <div className="scheduler-header">
        <h1 className="scheduler-title">{TEXT.scheduler.title}</h1>
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
        <PageCard className="page-card--flush">
          <table className="data-table responsive-table">
            <thead>
              <tr>
                <th>{TEXT.scheduler.tableTask}</th>
                <th>{TEXT.scheduler.tableSchedule}</th>
                <th>{TEXT.scheduler.tableNextRun}</th>
                <th>{TEXT.scheduler.tableStatus}</th>
                <th className="text-right">{TEXT.scheduler.tableActions}</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((t) => (
                <tr key={t.id}>
                  <td data-label={TEXT.scheduler.tableTask}>
                    <div className="font-semibold">{getTaskName(t)}</div>
                    <div className="text-small text-muted break-all">{t.prompt}</div>
                  </td>
                  <td data-label={TEXT.scheduler.tableSchedule}>
                    {t.cron_expression ? formatCron(t.cron_expression) : '—'}
                  </td>
                  <td data-label={TEXT.scheduler.tableNextRun}>{formatDate(t.next_run_at)}</td>
                  <td data-label={TEXT.scheduler.tableStatus}>
                    <span
                      className={`scheduler-status-badge scheduler-status-badge--${t.enabled ? 'enabled' : 'disabled'}`}
                    >
                      {t.enabled ? TEXT.scheduler.statusEnabled : TEXT.scheduler.statusDisabled}
                    </span>
                    {t.last_error && (
                      <span
                        className="scheduler-error-badge"
                        title={t.last_error}
                      >
                        {TEXT.scheduler.statusError}
                      </span>
                    )}
                  </td>
                  <td data-label={TEXT.scheduler.tableActions} className="text-right">
                    <div className="scheduler-actions">
                      <button onClick={() => setConfirmRun(t.id)} disabled={!t.enabled}>
                        {TEXT.scheduler.runNow}
                      </button>
                      <button onClick={() => openEdit(t)}>{TEXT.common.edit}</button>
                      <button
                        onClick={() => setConfirmDelete(t.id)}
                        className="text-danger border-danger"
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
          className="modal-overlay"
          onClick={() => setModalOpen(false)}
        >
          <div
            className="modal modal--md"
            onClick={(e) => e.stopPropagation()}
          >
            <h2>{editingTask ? TEXT.scheduler.editTitle : TEXT.scheduler.createTitle}</h2>
            <div className="stack-md">
              <label>
                {TEXT.scheduler.nameLabel}
                <input
                  value={form.description}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                  placeholder={TEXT.scheduler.namePlaceholder}
                  className="form-input mt-1"
                />
              </label>
              <label>
                {TEXT.scheduler.promptLabel}
                <textarea
                  rows={4}
                  value={form.prompt}
                  onChange={(e) => setForm((f) => ({ ...f, prompt: e.target.value }))}
                  placeholder={TEXT.scheduler.promptPlaceholder}
                  className="form-textarea mt-1"
                />
              </label>
              <label>
                {TEXT.scheduler.scheduleLabel}
                <div className="mt-1">
                  <CronBuilder
                    value={form.cron_expression}
                    onChange={(v) => setForm((f) => ({ ...f, cron_expression: v }))}
                  />
                </div>
              </label>
              <label className="row-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
                />
                {TEXT.scheduler.enabledLabel}
              </label>
            </div>
            <div className="row-between mt-4">
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
          className="modal-overlay"
          onClick={() => setConfirmDelete(null)}
        >
          <div className="modal modal--sm" onClick={(e) => e.stopPropagation()}>
            <h3>{TEXT.scheduler.deleteConfirmTitle}</h3>
            <p className="text-small text-secondary">
              {TEXT.scheduler.deleteConfirmDescription}
            </p>
            <div className="row-center gap-2 mt-4">
              <button onClick={() => setConfirmDelete(null)}>{TEXT.common.cancel}</button>
              <button onClick={() => handleDelete(confirmDelete)} className="text-danger border-danger">
                {TEXT.common.delete}
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmRun && (
        <div
          className="modal-overlay"
          onClick={() => setConfirmRun(null)}
        >
          <div className="modal modal--sm" onClick={(e) => e.stopPropagation()}>
            <h3>{TEXT.scheduler.runNowConfirmTitle}</h3>
            <p className="text-small text-secondary">
              {TEXT.scheduler.runNowConfirmDescription}
            </p>
            <div className="row-center gap-2 mt-4">
              <button onClick={() => setConfirmRun(null)}>{TEXT.common.cancel}</button>
              <button onClick={() => handleRun(confirmRun)}>{TEXT.common.run}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
