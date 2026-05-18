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
    <div style={{ padding: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h1 style={{ margin: 0 }}>Errors & Failures</h1>
      </div>

      <PageCard style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{unresolvedCount}</div>
            <div style={{ fontSize: '0.875rem', color: '#666' }}>Unresolved</div>
          </div>
          {Object.entries(typeBreakdown).map(([type, count]) => (
            <div key={type}>
              <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{count}</div>
              <div style={{ fontSize: '0.875rem', color: '#666' }}>{TYPE_LABELS[type] || type}</div>
            </div>
          ))}
        </div>
      </PageCard>

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          style={{ padding: '0.35rem 0.5rem', borderRadius: '4px', border: '1px solid #ccc', fontSize: '0.875rem' }}
        >
          <option value="all">All Types</option>
          <option value="workflow_execution">Workflow</option>
          <option value="scheduler_task">Scheduler</option>
          <option value="session_turn">Session</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          style={{ padding: '0.35rem 0.5rem', borderRadius: '4px', border: '1px solid #ccc', fontSize: '0.875rem' }}
        >
          <option value="all">All Statuses</option>
          <option value="unresolved">Unresolved</option>
          <option value="resolved">Resolved</option>
          <option value="ignored">Ignored</option>
        </select>
      </div>

      {isLoading && (
        <PageCard>
          <LoadingSkeleton lines={4} height="2rem" />
        </PageCard>
      )}

      {isError && (
        <ErrorState message={error?.message ?? 'Failed to load errors'} onRetry={refetch} />
      )}

      {!isLoading && !isError && filteredErrors.length === 0 && (
        <EmptyState
          title="No errors found"
          description="Hestia is running smoothly."
        />
      )}

      {!isLoading && filteredErrors.length > 0 && (
        <PageCard style={{ padding: 0, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #eee', textAlign: 'left', background: '#fafafa' }}>
                <th style={{ padding: '0.75rem 1rem' }}>Type</th>
                <th style={{ padding: '0.75rem 1rem' }}>Source</th>
                <th style={{ padding: '0.75rem 1rem' }}>Message</th>
                <th style={{ padding: '0.75rem 1rem' }}>When</th>
                <th style={{ padding: '0.75rem 1rem' }}>Status</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredErrors.map((err) => (
                <Fragment key={err.id}>
                  <tr key={err.id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                    <td style={{ padding: '0.75rem 1rem' }}>
                      <span
                        style={{
                          display: 'inline-block',
                          padding: '0.15rem 0.5rem',
                          borderRadius: '12px',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          background: TYPE_COLORS[err.type]?.bg || '#f3f4f6',
                          color: TYPE_COLORS[err.type]?.color || '#374151',
                        }}
                      >
                        {TYPE_LABELS[err.type] || err.type}
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem 1rem' }}>
                      <div style={{ fontWeight: 600 }}>{err.source_name}</div>
                      <div style={{ fontSize: '0.75rem', color: '#888' }}>{err.source_id.slice(0, 8)}</div>
                    </td>
                    <td style={{ padding: '0.75rem 1rem', maxWidth: 300 }}>
                      <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {err.message}
                      </div>
                    </td>
                    <td style={{ padding: '0.75rem 1rem' }}>{formatRelativeDate(err.created_at)}</td>
                    <td style={{ padding: '0.75rem 1rem' }}>
                      <span
                        style={{
                          display: 'inline-block',
                          padding: '0.15rem 0.5rem',
                          borderRadius: '12px',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          background: STATUS_COLORS[err.status]?.bg || '#f3f4f6',
                          color: STATUS_COLORS[err.status]?.color || '#374151',
                        }}
                      >
                        {err.status}
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                        <button onClick={() => setExpandedId(expandedId === err.id ? null : err.id)}>
                          {expandedId === err.id ? 'Hide' : 'Details'}
                        </button>
                        <button onClick={() => handleDebug(err.id)}>Debug</button>
                        {err.status !== 'resolved' && (
                          <button onClick={() => handleResolve(err.id)}>Resolve</button>
                        )}
                        {err.status !== 'ignored' && (
                          <button onClick={() => handleIgnore(err.id)} style={{ color: '#6b7280' }}>
                            Ignore
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {expandedId === err.id && (
                    <tr style={{ background: '#fafafa' }}>
                      <td colSpan={6} style={{ padding: '0.75rem 1rem' }}>
                        <div style={{ fontFamily: 'monospace', fontSize: '0.8rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                          {err.message}
                        </div>
                        <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: '#888' }}>
                          Source ID: {err.source_id} | Type: {err.type}
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
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setDebugModal(null)}
        >
          <div
            style={{ width: '90%', maxWidth: 640, maxHeight: '90vh', overflowY: 'auto', background: '#fff', border: '1px solid #eee', borderRadius: '8px', padding: '1rem' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ marginTop: 0 }}>Debug Prompt</h3>
            <textarea
              readOnly
              value={debugModal.prompt}
              rows={12}
              style={{ width: '100%', padding: '0.5rem', fontFamily: 'monospace', fontSize: '0.875rem', border: '1px solid #ccc', borderRadius: '4px' }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1rem' }}>
              <button onClick={() => setDebugModal(null)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
