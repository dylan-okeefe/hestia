import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchWorkflows, createWorkflow, deleteWorkflow, type Workflow } from '../api/client';
import { TEXT } from '../lib/text';
import './Workflows.css';

const TRIGGER_ICONS: Record<string, string> = {
  manual: '🖱️',
  schedule: '📅',
  chat_command: '💬',
  message: '💬',
  webhook: '🔗',
  email: '✉️',
  proposal_approved: '✅',
  proposal_rejected: '❌',
  tool_error: '⚠️',
  workflow_completed: '🔄',
  session_started: '🚀',
};

function relativeTime(iso: string | null): string {
  if (!iso) return 'never';
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diff = Math.floor((now - then) / 1000);
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
}

export default function Workflows() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetchWorkflows()
      .then((data) => {
        setWorkflows(data.workflows);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  const handleNew = async () => {
    try {
      const wf = await createWorkflow(TEXT.workflows.defaultName);
      navigate(`/workflows/${wf.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : TEXT.workflows.createError);
    }
  };

  const executionDot = (status?: string) => {
    const colorClass = status === 'ok' ? 'status-dot-sm--success' : status === 'error' || status === 'failed' ? 'status-dot-sm--danger' : 'status-dot-sm--neutral';
    return (
      <span
        className={`status-dot-sm ${colorClass}`}
        title={status || 'never run'}
      />
    );
  };

  return (
    <div className="workflows-page">
      <div className="workflows-header">
        <h1>{TEXT.workflows.title}</h1>
        <button onClick={handleNew}>{TEXT.workflows.createButton}</button>
      </div>
      {loading && <p>{TEXT.workflows.loading}</p>}
      {error && <p className="text-danger">{error}</p>}
      {!loading && workflows.length === 0 && <p>{TEXT.workflows.empty}</p>}
      {!loading && workflows.length > 0 && (
        <table className="workflows-table">
          <thead>
            <tr>
              <th>{TEXT.workflows.tableName}</th>
              <th>{TEXT.workflows.tableTrigger}</th>
              <th>{TEXT.workflows.tableLastRun}</th>
              <th>{TEXT.workflows.tableActiveVersion}</th>
              <th>{TEXT.workflows.tableActions}</th>
            </tr>
          </thead>
          <tbody>
            {workflows.map((wf) => (
              <tr
                key={wf.id}
                onClick={() => navigate(`/workflows/${wf.id}`)}
                data-testid="workflow-row"
              >
                <td>{wf.name}</td>
                <td>
                  <span className="workflows-trigger-badge">
                    <span>{TRIGGER_ICONS[wf.trigger_type] || '•'}</span>
                    {wf.trigger_type}
                  </span>
                  {wf.trigger_type === 'webhook' && (
                    <a
                      href={`${window.location.origin}/api/webhooks/${wf.id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      title="Open webhook URL"
                      onClick={(e) => e.stopPropagation()}
                      className="workflows-webhook-link"
                    >
                      🔗
                    </a>
                  )}
                </td>
                <td>
                  <span className="row-center">
                    {executionDot(wf.last_execution_status)}
                    {relativeTime(wf.last_execution_at ?? null)}
                  </span>
                </td>
                <td>{wf.active_version_id ?? '—'}</td>
                <td>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (!window.confirm(TEXT.workflows.deleteConfirm(wf.name))) return;
                      deleteWorkflow(wf.id)
                        .then(() => setWorkflows((prev) => prev.filter((w) => w.id !== wf.id)))
                        .catch((err) => setError(err instanceof Error ? err.message : TEXT.workflows.deleteError));
                    }}
                    className="workflows-delete-btn"
                  >
                    {TEXT.common.delete}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
