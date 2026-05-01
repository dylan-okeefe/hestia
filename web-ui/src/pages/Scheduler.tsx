import { useEffect, useState } from 'react';
import { fetchSchedulerTasks, runTaskNow } from '../api/client';

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

export default function Scheduler() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runningId, setRunningId] = useState<string | null>(null);

  const loadTasks = () => {
    setLoading(true);
    fetchSchedulerTasks()
      .then((data) => {
        setTasks(data.tasks || []);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  };

  useEffect(() => {
    loadTasks();
  }, []);

  const handleRun = async (id: string) => {
    setRunningId(id);
    await runTaskNow(id);
    setRunningId(null);
    loadTasks();
  };

  return (
    <div style={{ padding: '1rem' }}>
      <h1>Scheduled Tasks</h1>
      {loading && <p>Loading tasks…</p>}
      {error && <p style={{ color: 'red' }}>{error}</p>}
      {!loading && tasks.length === 0 && <p>No tasks found.</p>}
      {tasks.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #ccc', textAlign: 'left' }}>
              <th>Task</th>
              <th>Cron</th>
              <th>Last Run</th>
              <th>Next Run</th>
              <th>Last Result</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((t) => (
              <tr key={t.id} style={{ borderBottom: '1px solid #eee' }}>
                <td>{t.description || t.prompt || t.id}</td>
                <td>{t.cron_expression ?? '—'}</td>
                <td>{t.last_run_at ? new Date(t.last_run_at).toLocaleString() : '—'}</td>
                <td>{t.next_run_at ? new Date(t.next_run_at).toLocaleString() : '—'}</td>
                <td style={{ color: t.last_error ? 'red' : 'green' }}>
                  {t.last_error ?? 'OK'}
                </td>
                <td>
                  <button onClick={() => handleRun(t.id)} disabled={runningId === t.id || !t.enabled}>
                    {runningId === t.id ? 'Running…' : 'Run now'}
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
