import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchWorkflows, createWorkflow, type Workflow } from '../api/client';

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

  return (
    <div style={{ padding: '1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
        <h1>Workflows</h1>
        <button onClick={handleNew}>New Workflow</button>
      </div>
      {loading && <p>Loading workflows…</p>}
      {error && <p style={{ color: 'red' }}>{error}</p>}
      {!loading && workflows.length === 0 && <p>No workflows yet.</p>}
      {workflows.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #ddd', textAlign: 'left' }}>
              <th style={{ padding: '0.5rem' }}>Name</th>
              <th style={{ padding: '0.5rem' }}>Trigger</th>
              <th style={{ padding: '0.5rem' }}>Last Edited</th>
              <th style={{ padding: '0.5rem' }}>Active Version</th>
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
                <td style={{ padding: '0.5rem' }}>{wf.trigger_type}</td>
                <td style={{ padding: '0.5rem' }}>{new Date(wf.last_edited_at).toLocaleString()}</td>
                <td style={{ padding: '0.5rem' }}>{wf.active_version_id ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
