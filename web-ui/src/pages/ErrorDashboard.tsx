import { useState, Fragment } from 'react';
import { useApiQuery, useApiMutation } from '../hooks/useApi';
import {
  fetchErrors,
  resolveError,
  ignoreError,
  debugError,
  type ErrorItem,
} from '../api/client';
import PageCard from '../components/layout/PageCard';
import LoadingSkeleton from '../components/layout/LoadingSkeleton';
import ErrorState from '../components/layout/ErrorState';
import EmptyState from '../components/layout/EmptyState';
import { formatRelativeDate } from '../lib/format';
import { TEXT } from '../lib/text';
import './ErrorDashboard.css';

const TYPE_LABELS: Record<string, string> = {
  workflow_execution: 'Workflow',
  scheduler_task: 'Scheduler',
  session_turn: 'Session',
};

const TYPE_COLORS: Record<string, { bg: string; color: string }> = {
  workflow_execution: { bg: '#fee2e2', color: '#991b1b' },
  scheduler_task: { bg: '#fef3c7', color: '#92400e' },
  session_turn: { bg: '#dbeafe', color: '#1e40af' },
};

const STATUS_COLORS: Record<string, { bg: string; color: string }> = {
  unresolved: { bg: '#fee2e2', color: '#991b1b' },
  resolved: { bg: '#dcfce7', color: '#166534' },
  ignored: { bg: '#f3f4f6', color: '#6b7280' },
};

export default function ErrorDashboard() {
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useApiQuery<{ errors: ErrorItem[] }>('errors', fetchErrors);

  const errors = data?.errors ?? [];
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [debugModal, setDebugModal] = useState<{ id: string; prompt: string } | null>(null);

  const resolveMut = useApiMutation(resolveError);
  const ignoreMut = useApiMutation(ignoreError);
  const debugMut = useApiMutation(debugError);

  const filteredErrors = errors.filter((e) => {
    if (typeFilter !== 'all' && e.type !== typeFilter) return false;
    if (statusFilter !== 'all' && e.status !== statusFilter) return false;
    return true;
  });

  const unresolvedCount = errors.filter((e) => e.status === 'unresolved').length;
  const typeBreakdown = errors.reduce<Record<string, number>>((acc, e) => {
    if (e.status === 'unresolved') {
      acc[e.type] = (acc[e.type] || 0) + 1;
    }
    return acc;
  }, {});

  const handleResolve = async (id: string) => {
    await resolveMut.mutateAsync(id);
    refetch();
  };

  const handleIgnore = async (id: string) => {
    await ignoreMut.mutateAsync(id);
    refetch();
  };

  const handleDebug = async (id: string) => {
    const result = await debugMut.mutateAsync(id);
    setDebugModal({ id, prompt: result.prompt });
  };

  return (
    <div className="error-dashboard-page">
      <div className="error-dashboard-header">
        <h1 className="error-dashboard-title">{TEXT.errorDashboard.title}</h1>
      </div>

      <PageCard className="mb-4">
        <div className="error-dashboard-stats">
          <div>
            <div className="error-dashboard-stat-value">{unresolvedCount}</div>
            <div className="error-dashboard-stat-label">{TEXT.errorDashboard.unresolvedLabel}</div>
          </div>
          {Object.entries(typeBreakdown).map(([type, count]) => (
            <div key={type}>
              <div className="error-dashboard-stat-value">{count}</div>
              <div className="error-dashboard-stat-label">{TYPE_LABELS[type] || type}</div>
            </div>
          ))}
        </div>
      </PageCard>

      <div className="error-dashboard-filters">
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="form-select"
        >
          <option value="all">{TEXT.errorDashboard.filterAllTypes}</option>
          <option value="workflow_execution">{TEXT.errorDashboard.typeWorkflow}</option>
          <option value="scheduler_task">{TEXT.errorDashboard.typeScheduler}</option>
          <option value="session_turn">{TEXT.errorDashboard.typeSession}</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="form-select"
        >
          <option value="all">{TEXT.errorDashboard.filterAllStatuses}</option>
          <option value="unresolved">{TEXT.errorDashboard.filterUnresolved}</option>
          <option value="resolved">{TEXT.errorDashboard.filterResolved}</option>
          <option value="ignored">{TEXT.errorDashboard.filterIgnored}</option>
        </select>
      </div>

      {isLoading && (
        <PageCard>
          <LoadingSkeleton lines={4} height="2rem" />
        </PageCard>
      )}

      {isError && (
        <ErrorState message={error?.message ?? TEXT.errorDashboard.loadError} onRetry={refetch} />
      )}

      {!isLoading && !isError && filteredErrors.length === 0 && (
        <EmptyState
          title={TEXT.errorDashboard.emptyTitle}
          description={TEXT.errorDashboard.emptyDescription}
        />
      )}

      {!isLoading && filteredErrors.length > 0 && (
        <PageCard className="page-card--flush">
          <table className="data-table">
            <thead>
              <tr>
                <th>{TEXT.errorDashboard.tableType}</th>
                <th>{TEXT.errorDashboard.tableSource}</th>
                <th>{TEXT.errorDashboard.tableMessage}</th>
                <th>{TEXT.errorDashboard.tableWhen}</th>
                <th>{TEXT.errorDashboard.tableStatus}</th>
                <th className="text-right">{TEXT.errorDashboard.tableActions}</th>
              </tr>
            </thead>
            <tbody>
              {filteredErrors.map((err) => (
                <Fragment key={err.id}>
                  <tr>
                    <td>
                      <span
                        className="error-dashboard-type-badge"
                        style={{
                          background: TYPE_COLORS[err.type]?.bg || '#f3f4f6',
                          color: TYPE_COLORS[err.type]?.color || '#374151',
                        }}
                      >
                        {TYPE_LABELS[err.type] || err.type}
                      </span>
                    </td>
                    <td>
                      <div className="font-semibold">{err.source_name}</div>
                      <div className="text-xs text-muted">{err.source_id.slice(0, 8)}</div>
                    </td>
                    <td className="max-w-300">
                      <div className="text-small" className="text-ellipsis">
                        {err.message}
                      </div>
                    </td>
                    <td>{formatRelativeDate(err.created_at)}</td>
                    <td>
                      <span
                        className="error-dashboard-status-badge"
                        style={{
                          background: STATUS_COLORS[err.status]?.bg || '#f3f4f6',
                          color: STATUS_COLORS[err.status]?.color || '#374151',
                        }}
                      >
                        {err.status}
                      </span>
                    </td>
                    <td className="text-right">
                      <div className="admin-users-actions">
                        <button onClick={() => setExpandedId(expandedId === err.id ? null : err.id)}>
                          {expandedId === err.id ? TEXT.errorDashboard.hideButton : TEXT.errorDashboard.detailsButton}
                        </button>
                        <button onClick={() => handleDebug(err.id)}>{TEXT.errorDashboard.debugButton}</button>
                        {err.status !== 'resolved' && (
                          <button onClick={() => handleResolve(err.id)}>{TEXT.errorDashboard.resolveButton}</button>
                        )}
                        {err.status !== 'ignored' && (
                          <button onClick={() => handleIgnore(err.id)} className="text-secondary">
                            {TEXT.errorDashboard.ignoreButton}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {expandedId === err.id && (
                    <tr className="error-dashboard-detail-row">
                      <td colSpan={6} className="p-4">
                        <div className="error-dashboard-detail-text">
                          {err.message}
                        </div>
                        <div className="error-dashboard-detail-meta">
                          {TEXT.errorDashboard.sourceIdFormat(err.source_id, err.type)}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </PageCard>
      )}

      {debugModal && (
        <div
          className="modal-overlay"
          onClick={() => setDebugModal(null)}
        >
          <div
            className="modal modal--lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h3>{TEXT.errorDashboard.debugModalTitle}</h3>
            <textarea
              readOnly
              value={debugModal.prompt}
              rows={12}
              className="code-input"
            />
            <div className="row-between mt-4">
              <button onClick={() => setDebugModal(null)}>{TEXT.common.close}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
