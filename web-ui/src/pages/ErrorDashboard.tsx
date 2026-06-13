import { useState, Fragment } from 'react';
import { useApiQuery, useApiMutation } from '../hooks/useApi';
import { useToast } from '../hooks/useToast';
import {
  fetchErrors,
  resolveError,
  ignoreError,
  debugError,
  type ErrorItem,
} from '../api/client';
import PageCard from '../components/layout/PageCard';
import Button from '../components/Button';
import Modal from '../components/Modal';
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

const TYPE_CLASSES: Record<string, string> = {
  workflow_execution: 'badge--solid-danger',
  scheduler_task: 'badge--solid-warning',
  session_turn: 'badge--solid-info',
};

const STATUS_CLASSES: Record<string, string> = {
  unresolved: 'badge--solid-danger',
  resolved: 'badge--solid-success',
  ignored: 'badge--solid-neutral',
};

export default function ErrorDashboard() {
  const { addToast } = useToast();
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
    try {
      await resolveMut.mutateAsync(id);
      addToast({ message: 'Error resolved', type: 'success', duration: 3000 });
      refetch();
    } catch (err: any) {
      addToast({ message: err.message || 'Failed to resolve error', type: 'error', duration: 5000 });
    }
  };

  const handleIgnore = async (id: string) => {
    try {
      await ignoreMut.mutateAsync(id);
      addToast({ message: 'Error ignored', type: 'info', duration: 3000 });
      refetch();
    } catch (err: any) {
      addToast({ message: err.message || 'Failed to ignore error', type: 'error', duration: 5000 });
    }
  };

  const handleDebug = async (id: string) => {
    try {
      const result = await debugMut.mutateAsync(id);
      setDebugModal({ id, prompt: result.prompt });
    } catch (err: any) {
      addToast({ message: err.message || 'Failed to fetch debug prompt', type: 'error', duration: 5000 });
    }
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
          <table className="data-table responsive-table">
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
                    <td data-label={TEXT.errorDashboard.tableType}>
                      <span
                        className={`error-dashboard-type-badge ${TYPE_CLASSES[err.type] || 'badge--solid-neutral'}`}
                      >
                        {TYPE_LABELS[err.type] || err.type}
                      </span>
                    </td>
                    <td data-label={TEXT.errorDashboard.tableSource}>
                      <div className="font-semibold">{err.source_name}</div>
                      <div className="text-xs text-muted">{err.source_id.slice(0, 8)}</div>
                    </td>
                    <td data-label={TEXT.errorDashboard.tableMessage} className="max-w-300">
                      <div className="text-small text-ellipsis">
                        {err.message}
                      </div>
                    </td>
                    <td data-label={TEXT.errorDashboard.tableWhen}>{formatRelativeDate(err.created_at)}</td>
                    <td data-label={TEXT.errorDashboard.tableStatus}>
                      <span
                        className={`error-dashboard-status-badge ${STATUS_CLASSES[err.status] || 'badge--solid-neutral'}`}
                      >
                        {err.status}
                      </span>
                    </td>
                    <td data-label={TEXT.errorDashboard.tableActions} className="text-right">
                      <div className="admin-users-actions">
                        <Button variant="ghost" size="sm" onClick={() => setExpandedId(expandedId === err.id ? null : err.id)}>
                          {expandedId === err.id ? TEXT.errorDashboard.hideButton : TEXT.errorDashboard.detailsButton}
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => handleDebug(err.id)}>
                          {TEXT.errorDashboard.debugButton}
                        </Button>
                        {err.status !== 'resolved' && (
                          <Button size="sm" onClick={() => handleResolve(err.id)}>
                            {TEXT.errorDashboard.resolveButton}
                          </Button>
                        )}
                        {err.status !== 'ignored' && (
                          <Button variant="ghost" size="sm" onClick={() => handleIgnore(err.id)}>
                            {TEXT.errorDashboard.ignoreButton}
                          </Button>
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

      <Modal
        isOpen={!!debugModal}
        onClose={() => setDebugModal(null)}
        title={TEXT.errorDashboard.debugModalTitle}
        size="lg"
        footer={
          <div className="row-between">
            <button onClick={() => setDebugModal(null)}>{TEXT.common.close}</button>
          </div>
        }
      >
        <textarea
          readOnly
          value={debugModal?.prompt ?? ''}
          rows={12}
          className="code-input"
        />
      </Modal>
    </div>
  );
}
