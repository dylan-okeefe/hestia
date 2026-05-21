import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchDashboard, fetchSchedulerTasks, runDoctor, type ExecutionRecord } from '../api/client';
import { useCurrentUser } from '../hooks/useCurrentUser';
import PageCard from '../components/layout/PageCard';
import LoadingSkeleton from '../components/layout/LoadingSkeleton';
import ErrorState from '../components/layout/ErrorState';
import { TEXT } from '../lib/text';
import './Dashboard.css';

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
      <div className="dashboard-page">
        <LoadingSkeleton lines={6} height="2rem" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard-page">
        <ErrorState message={error} onRetry={() => window.location.reload()} />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="dashboard-page">
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
        className={`status-dot ${connected ? 'status-dot--success' : 'status-dot--danger'}`}
        title={connected ? TEXT.dashboard.connected : TEXT.dashboard.disconnected}
      />
    );
  };

  const healthColorClass = healthRate === null ? 'status-dot--neutral' : healthRate === 100 ? 'status-dot--success' : healthRate >= 50 ? 'status-dot--warning' : 'status-dot--danger';

  return (
    <div className="dashboard-page">
      <h1 className="dashboard-greeting">{greeting}</h1>

      <div className="dashboard-grid">
        <PageCard>
          <div className="dashboard-stat-label">{TEXT.dashboard.activeWorkflowsLabel}</div>
          <div className="dashboard-stat-value">{data.active_workflow_count}</div>
        </PageCard>
        <PageCard>
          <div className="dashboard-stat-label">{TEXT.dashboard.scheduledTasksLabel}</div>
          <div className="dashboard-stat-value">{scheduledCount}</div>
        </PageCard>
        <PageCard>
          <div className="dashboard-stat-label">{TEXT.dashboard.pendingProposalsLabel}</div>
          <div className="dashboard-stat-value">{data.pending_proposal_count}</div>
        </PageCard>
        <PageCard>
          <div className="dashboard-stat-label">{TEXT.dashboard.recentSessionsLabel}</div>
          <div className="dashboard-stat-value">{data.recent_executions.length}</div>
        </PageCard>
        <PageCard>
          <div className="dashboard-stat-label mb-1">{TEXT.dashboard.systemHealthLabel}</div>
          <div className="row-center gap-2">
            <span className={`status-dot ${healthColorClass}`} />
            <span className="text-small font-semibold">
              {healthRate === null ? TEXT.dashboard.healthUnknown : TEXT.dashboard.healthPassing(healthRate)}
            </span>
          </div>
        </PageCard>
        <PageCard>
          <div className="dashboard-stat-label mb-1">{TEXT.dashboard.platformsLabel}</div>
          <div className="stack-sm text-small">
            <div>{platformStatus('telegram')} Telegram</div>
            <div>{platformStatus('matrix')} Matrix</div>
            <div>{platformStatus('email')} Email</div>
          </div>
        </PageCard>
      </div>

      <div className="dashboard-actions">
        <button onClick={() => navigate('/workflows')}>{TEXT.dashboard.goToWorkflows}</button>
        <button onClick={() => navigate('/profile')}>{TEXT.dashboard.viewProfile}</button>
        <button onClick={handleHealthCheck}>{TEXT.dashboard.runHealthCheck}</button>
      </div>

      <h2 className="dashboard-section-title">{TEXT.dashboard.recentExecutionsTitle}</h2>
      {data.recent_executions.length === 0 && <p>{TEXT.dashboard.noExecutions}</p>}
      {data.recent_executions.length > 0 && (
        <PageCard className="page-card--flush">
          <table className="data-table">
            <thead>
              <tr>
                <th>{TEXT.dashboard.tableWorkflow}</th>
                <th>{TEXT.dashboard.tableStatus}</th>
                <th>{TEXT.dashboard.tableTime}</th>
                <th>{TEXT.dashboard.tableElapsed}</th>
                <th>{TEXT.dashboard.tableNodes}</th>
              </tr>
            </thead>
            <tbody>
              {data.recent_executions.map((ex: ExecutionRecord) => (
                <tr
                  key={ex.id}
                  onClick={() => navigate(`/workflows/${ex.workflow_id}`)}
                >
                  <td>{ex.workflow_id}</td>
                  <td className={ex.status === 'ok' ? 'text-success' : 'text-danger'}>{ex.status}</td>
                  <td>{ex.created_at ? new Date(ex.created_at).toLocaleString() : '—'}</td>
                  <td>{ex.total_elapsed_ms}ms</td>
                  <td>{ex.node_results.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </PageCard>
      )}
    </div>
  );
}
