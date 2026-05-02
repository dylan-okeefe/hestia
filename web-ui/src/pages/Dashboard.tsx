import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchDashboard, type ExecutionRecord } from '../api/client';

interface DashboardData {
  active_workflow_count: number;
  recent_executions: ExecutionRecord[];
  pending_proposal_count: number;
  platforms_connected: string[];
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetchDashboard()
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Failed to load dashboard');
        setLoading(false);
      });
  }, []);

  if (loading) {
    return <div style={{ padding: '1rem' }}><p>Loading dashboard…</p></div>;
  }

  if (error) {
    return <div style={{ padding: '1rem' }}><p style={{ color: 'red' }}>{error}</p></div>;
  }

  if (!data) {
    return <div style={{ padding: '1rem' }}><p>No data available.</p></div>;
  }

  const platformStatus = (name: string) => {
    const connected = data.platforms_connected.includes(name);
    return (
      <span
        style={{
          display: 'inline-block',
          width: 10,
          height: 10,
          borderRadius: '50%',
          background: connected ? '#22c55e' : '#ef4444',
          marginRight: '0.5rem',
        }}
        title={connected ? 'Connected' : 'Disconnected'}
      />
    );
  };

  return (
    <div style={{ padding: '1rem' }}>
      <h1>Dashboard</h1>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
        <div style={{ padding: '1rem', border: '1px solid #ddd', borderRadius: 8, background: '#fafafa' }}>
          <div style={{ fontSize: '0.875rem', color: '#666' }}>Active Workflows</div>
          <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{data.active_workflow_count}</div>
          <button onClick={() => navigate('/workflows')} style={{ marginTop: '0.5rem', fontSize: '0.75rem' }}>
            View Workflows →
          </button>
        </div>
        <div style={{ padding: '1rem', border: '1px solid #ddd', borderRadius: 8, background: '#fafafa' }}>
          <div style={{ fontSize: '0.875rem', color: '#666' }}>Pending Proposals</div>
          <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{data.pending_proposal_count}</div>
        </div>
        <div style={{ padding: '1rem', border: '1px solid #ddd', borderRadius: 8, background: '#fafafa' }}>
          <div style={{ fontSize: '0.875rem', color: '#666', marginBottom: '0.5rem' }}>System Health</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', fontSize: '0.875rem' }}>
            <div>{platformStatus('telegram')} Telegram</div>
            <div>{platformStatus('matrix')} Matrix</div>
            <div>{platformStatus('email')} Email</div>
          </div>
        </div>
      </div>

      <h2>Recent Executions</h2>
      {data.recent_executions.length === 0 && <p>No executions yet.</p>}
      {data.recent_executions.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #ccc', textAlign: 'left' }}>
              <th style={{ padding: '0.25rem' }}>Workflow</th>
              <th style={{ padding: '0.25rem' }}>Status</th>
              <th style={{ padding: '0.25rem' }}>Time</th>
              <th style={{ padding: '0.25rem' }}>Elapsed</th>
              <th style={{ padding: '0.25rem' }}>Nodes</th>
            </tr>
          </thead>
          <tbody>
            {data.recent_executions.map((ex: ExecutionRecord) => (
              <tr
                key={ex.id}
                style={{ borderBottom: '1px solid #eee', cursor: 'pointer' }}
                onClick={() => navigate(`/workflows/${ex.workflow_id}`)}
              >
                <td style={{ padding: '0.25rem' }}>{ex.workflow_id}</td>
                <td style={{ padding: '0.25rem', color: ex.status === 'ok' ? 'green' : 'red' }}>{ex.status}</td>
                <td style={{ padding: '0.25rem' }}>{ex.created_at ? new Date(ex.created_at).toLocaleString() : '—'}</td>
                <td style={{ padding: '0.25rem' }}>{ex.total_elapsed_ms}ms</td>
                <td style={{ padding: '0.25rem' }}>{ex.node_results.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
