import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchWorkflows, createWorkflow, deleteWorkflow, type Workflow } from '../api/client';

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
      const wf = await createWorkflow('New Workflow');
      navigate(`/workflows/${wf.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create workflow');
    }
  };

  const executionDot = (status?: string) => {
    const color = status === 'ok' ? '#22c55e' : status === 'error' ? '#ef4444' : '#9ca3af';
    return (
      <span
        style={{
          display: 'inline-block',
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: color,
          marginRight: '0.5rem',
        }}
        title={status || 'never run'}
      />
    );
  };

  return (
    <div style={{ padding: '1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
        <h1>Workflows</h1>
        <button onClick={handleNew}>New Workflow</button>
      </div>
      {loading && <p>Loading workflows…</p>}
      {error && <p style={{ color: 'red' }}>{error}</p>}
      {!loading && workflows.length === 0 && <p>No workflows yet.</p>}
      {!loading && workflows.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #ddd', textAlign: 'left' }}>
              <th style={{ padding: '0.5rem' }}>Name</th>
              <th style={{ padding: '0.5rem' }}>Trigger</th>
              <th style={{ padding: '0.5rem' }}>Last Run</th>
              <th style={{ padding: '0.5rem' }}>Active Version</th>
              <th style={{ padding: '0.5rem' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {workflows.map((wf) => (
              <tr
                key={wf.id}
                onClick={() => navigate(`/workflows/${wf.id}`)}
                style={{ borderBottom: '1px solid #eee', cursor: 'pointer' }}
                data-testid="workflow-row"
              >
                <td style={{ padding: '0.5rem' }}>{wf.name}</td>
                <td style={{ padding: '0.5rem' }}>
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.25rem',
                      padding: '0.125rem 0.5rem',
                      borderRadius: '9999px',
                      background: '#e5e7eb',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      textTransform: 'uppercase',
                    }}
                  >
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
                      style={{ marginLeft: '0.5rem', textDecoration: 'none' }}
                    >
                      🔗
                    </a>
                  )}
                </td>
                <td style={{ padding: '0.5rem' }}>
                  <span style={{ display: 'flex', alignItems: 'center' }}>
                    {executionDot(wf.last_execution_status)}
                    {relativeTime(wf.last_execution_at ?? null)}
                  </span>
                </td>
                <td style={{ padding: '0.5rem' }}>{wf.active_version_id ?? '—'}</td>
                <td style={{ padding: '0.5rem' }}>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (!window.confirm(`Delete workflow "${wf.name}"?`)) return;
                      deleteWorkflow(wf.id)
                        .then(() => setWorkflows((prev) => prev.filter((w) => w.id !== wf.id)))
                        .catch((err) => setError(err instanceof Error ? err.message : 'Failed to delete workflow'));
                    }}
                    style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', color: 'red' }}
                  >
                    Delete
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
