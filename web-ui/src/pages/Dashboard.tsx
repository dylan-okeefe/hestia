import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchDashboard, fetchSchedulerTasks, runDoctor, type ExecutionRecord } from '../api/client';
import { useCurrentUser } from '../hooks/useCurrentUser';
import PageCard from '../components/layout/PageCard';
import LoadingSkeleton from '../components/layout/LoadingSkeleton';
import ErrorState from '../components/layout/ErrorState';
import { TEXT } from '../lib/text';

interface DashboardData {
  active_workflow_count: number;
  recent_executions: ExecutionRecord[];
  pending_proposal_count: number;
  platforms_connected: string[];
}

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return TEXT.dashboard.greetingMorning;
  if (hour < 18) return TEXT.dashboard.greetingAfternoon;
  return TEXT.dashboard.greetingEvening;
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scheduledCount, setScheduledCount] = useState(0);
  const [healthRate, setHealthRate] = useState<number | null>(null);
  const navigate = useNavigate();
  const { user, isLoading: userLoading } = useCurrentUser();

  useEffect(() => {
    Promise.all([
      fetchDashboard(),
      fetchSchedulerTasks(),
    ])
      .then(([dash, sched]) => {
        setData(dash);
        setScheduledCount(sched.tasks?.length ?? 0);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : TEXT.dashboard.loadError);
        setLoading(false);
      });
  }, []);

  const handleHealthCheck = async () => {
    try {
      const res = await runDoctor();
      const checks = res.checks || [];
      const rate = checks.length > 0
        ? Math.round((checks.filter((c: any) => c.ok).length / checks.length) * 100)
        : 0;
      setHealthRate(rate);
    } catch {
      setHealthRate(0);
    }
  };

  if (loading || userLoading) {
    return (
      <div style={{ padding: '1rem' }}>
        <LoadingSkeleton lines={6} height="2rem" />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '1rem' }}>
        <ErrorState message={error} onRetry={() => window.location.reload()} />
      </div>
    );
  }

  if (!data) {
    return (
      <div style={{ padding: '1rem' }}>
        <ErrorState message={TEXT.dashboard.noData} />
      </div>
    );
  }

  const displayName = user?.display_name ?? 'there';
  const greeting = `${getGreeting()}, ${displayName}`;

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
        title={connected ? TEXT.dashboard.connected : TEXT.dashboard.disconnected}
      />
    );
  };

  const healthColor = healthRate === null ? '#9ca3af' : healthRate === 100 ? '#22c55e' : healthRate >= 50 ? '#f59e0b' : '#ef4444';

  return (
    <div style={{ padding: '1rem' }}>
      <h1 style={{ marginBottom: '1.5rem' }}>{greeting}</h1>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
        <PageCard>
          <div style={{ fontSize: '0.875rem', color: '#666' }}>{TEXT.dashboard.activeWorkflowsLabel}</div>
          <div style={{ fontSize: '1.5rem', fontWeight: 'bold', margin: '0.25rem 0' }}>{data.active_workflow_count}</div>
        </PageCard>
        <PageCard>
          <div style={{ fontSize: '0.875rem', color: '#666' }}>{TEXT.dashboard.scheduledTasksLabel}</div>
          <div style={{ fontSize: '1.5rem', fontWeight: 'bold', margin: '0.25rem 0' }}>{scheduledCount}</div>
        </PageCard>
        <PageCard>
          <div style={{ fontSize: '0.875rem', color: '#666' }}>{TEXT.dashboard.pendingProposalsLabel}</div>
          <div style={{ fontSize: '1.5rem', fontWeight: 'bold', margin: '0.25rem 0' }}>{data.pending_proposal_count}</div>
        </PageCard>
        <PageCard>
          <div style={{ fontSize: '0.875rem', color: '#666' }}>{TEXT.dashboard.recentSessionsLabel}</div>
          <div style={{ fontSize: '1.5rem', fontWeight: 'bold', margin: '0.25rem 0' }}>{data.recent_executions.length}</div>
        </PageCard>
        <PageCard>
          <div style={{ fontSize: '0.875rem', color: '#666', marginBottom: '0.25rem' }}>{TEXT.dashboard.systemHealthLabel}</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span
              style={{
                display: 'inline-block',
                width: 12,
                height: 12,
                borderRadius: '50%',
                background: healthColor,
              }}
            />
            <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>
              {healthRate === null ? TEXT.dashboard.healthUnknown : TEXT.dashboard.healthPassing(healthRate)}
            </span>
          </div>
        </PageCard>
        <PageCard>
          <div style={{ fontSize: '0.875rem', color: '#666', marginBottom: '0.25rem' }}>{TEXT.dashboard.platformsLabel}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', fontSize: '0.875rem' }}>
            <div>{platformStatus('telegram')} Telegram</div>
            <div>{platformStatus('matrix')} Matrix</div>
            <div>{platformStatus('email')} Email</div>
          </div>
        </PageCard>
      </div>

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        <button onClick={() => navigate('/workflows')}>{TEXT.dashboard.goToWorkflows}</button>
        <button onClick={() => navigate('/profile')}>{TEXT.dashboard.viewProfile}</button>
        <button onClick={handleHealthCheck}>{TEXT.dashboard.runHealthCheck}</button>
      </div>

      <h2 style={{ marginBottom: '0.75rem' }}>{TEXT.dashboard.recentExecutionsTitle}</h2>
      {data.recent_executions.length === 0 && <p>{TEXT.dashboard.noExecutions}</p>}
      {data.recent_executions.length > 0 && (
        <PageCard style={{ padding: 0, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #ccc', textAlign: 'left', background: '#fafafa' }}>
                <th style={{ padding: '0.5rem 0.75rem' }}>{TEXT.dashboard.tableWorkflow}</th>
                <th style={{ padding: '0.5rem 0.75rem' }}>{TEXT.dashboard.tableStatus}</th>
                <th style={{ padding: '0.5rem 0.75rem' }}>{TEXT.dashboard.tableTime}</th>
                <th style={{ padding: '0.5rem 0.75rem' }}>{TEXT.dashboard.tableElapsed}</th>
                <th style={{ padding: '0.5rem 0.75rem' }}>{TEXT.dashboard.tableNodes}</th>
              </tr>
            </thead>
            <tbody>
              {data.recent_executions.map((ex: ExecutionRecord) => (
                <tr
                  key={ex.id}
                  style={{ borderBottom: '1px solid #eee', cursor: 'pointer' }}
                  onClick={() => navigate(`/workflows/${ex.workflow_id}`)}
                >
                  <td style={{ padding: '0.5rem 0.75rem' }}>{ex.workflow_id}</td>
                  <td style={{ padding: '0.5rem 0.75rem', color: ex.status === 'ok' ? 'green' : 'red' }}>{ex.status}</td>
                  <td style={{ padding: '0.5rem 0.75rem' }}>{ex.created_at ? new Date(ex.created_at).toLocaleString() : '—'}</td>
                  <td style={{ padding: '0.5rem 0.75rem' }}>{ex.total_elapsed_ms}ms</td>
                  <td style={{ padding: '0.5rem 0.75rem' }}>{ex.node_results.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </PageCard>
      )}
    </div>
  );
}
