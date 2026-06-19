import { useNavigate } from 'react-router-dom';
import { useApiQuery, useApiMutation } from '../hooks/useApi';
import { useToast } from '../hooks/useToast';
import {
  fetchBrowserSessions,
  fetchActiveBrowserStream,
  deleteBrowserSession,
  checkBrowserSession,
  setBrowserSessionRequiresHeaded,
  stopBrowserStream,
  type BrowserSession,
  type StreamSession,
} from '../api/client';
import PageCard from '../components/layout/PageCard';
import LoadingSkeleton from '../components/layout/LoadingSkeleton';
import ErrorState from '../components/layout/ErrorState';
import EmptyState from '../components/layout/EmptyState';
import { formatRelativeDate } from '../lib/format';
import './BrowserSessions.css';

function statusClass(status: string): string {
  switch (status) {
    case 'healthy':
      return 'status-dot--healthy';
    case 'stale':
      return 'status-dot--stale';
    case 'expired':
      return 'status-dot--expired';
    default:
      return 'status-dot--unknown';
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'healthy':
      return 'Healthy';
    case 'stale':
      return 'Stale';
    case 'expired':
      return 'Expired';
    default:
      return 'Unknown';
  }
}

export default function BrowserSessions() {
  const navigate = useNavigate();
  const { addToast } = useToast();
  const {
    data: sessions,
    isLoading,
    isError,
    error,
    refetch,
  } = useApiQuery<BrowserSession[]>('browser-sessions', fetchBrowserSessions);
  const {
    data: activeStream,
    isLoading: isLoadingActive,
    refetch: refetchActive,
  } = useApiQuery<StreamSession | null>('browser-sessions-active', fetchActiveBrowserStream, {
    refetchInterval: 5000,
  });

  const checkMut = useApiMutation(
    ({ domain, force }: { domain: string; force: boolean }) => checkBrowserSession(domain, force)
  );
  const deleteMut = useApiMutation(deleteBrowserSession);
  const stopStreamMut = useApiMutation(stopBrowserStream);
  const requiresHeadedMut = useApiMutation(
    ({ domain, requires_headed }: { domain: string; requires_headed: boolean }) =>
      setBrowserSessionRequiresHeaded(domain, requires_headed)
  );

  const handleCheck = async (domain: string) => {
    try {
      await checkMut.mutateAsync({ domain, force: true });
      addToast({ message: `Health check passed for ${domain}`, type: 'success', duration: 3000 });
      refetch();
    } catch (err: any) {
      addToast({ message: err.message || 'Health check failed', type: 'error', duration: 5000 });
    }
  };

  const handleDelete = async (domain: string) => {
    if (!window.confirm(`Delete browser session for "${domain}"? This cannot be undone.`)) {
      return;
    }
    try {
      await deleteMut.mutateAsync(domain);
      addToast({ message: 'Session deleted', type: 'success', duration: 3000 });
      refetch();
    } catch (err: any) {
      addToast({ message: err.message || 'Delete failed', type: 'error', duration: 5000 });
    }
  };

  const handleStopStream = async () => {
    if (!window.confirm('End the active browser stream?')) {
      return;
    }
    try {
      await stopStreamMut.mutateAsync();
      addToast({ message: 'Stream ended', type: 'success', duration: 3000 });
      refetchActive();
      refetch();
    } catch (err: any) {
      addToast({ message: err.message || 'Failed to end stream', type: 'error', duration: 5000 });
    }
  };

  const handleReauth = (session: BrowserSession) => {
    const targetUrl = session.health_check_url || `https://${session.domain}/`;
    const params = new URLSearchParams({
      domain: session.domain,
      url: targetUrl,
    });
    if (session.requires_headed) {
      params.set('headed', 'true');
    }
    navigate(`/browser-sessions/stream?${params.toString()}`);
  };

  const handleRequiresHeadedChange = async (session: BrowserSession, checked: boolean) => {
    try {
      await requiresHeadedMut.mutateAsync({ domain: session.domain, requires_headed: checked });
      refetch();
    } catch (err: any) {
      addToast({ message: err.message || 'Failed to update headed preference', type: 'error', duration: 5000 });
    }
  };

  return (
    <div className="browser-sessions-page">
      <div className="browser-sessions-header">
        <h1 className="browser-sessions-title">Browser Sessions</h1>
        <button onClick={() => navigate('/browser-sessions/stream')}>
          + New Session
        </button>
      </div>

      {!isLoadingActive && activeStream && (
        <div className="browser-sessions-active-banner">
          <div className="browser-sessions-active-banner__content">
            <span className="browser-sessions-active-banner__dot" />
            <span>
              Active stream on <strong>{activeStream.domain}</strong>
            </span>
          </div>
          <div className="browser-sessions-active-banner__actions">
            <button
              onClick={() => navigate(`/browser-sessions/stream?domain=${encodeURIComponent(activeStream.domain)}`)}
              className="button--secondary"
            >
              View Stream
            </button>
            <button
              onClick={handleStopStream}
              disabled={stopStreamMut.isPending}
              className="button--danger"
            >
              End Session
            </button>
          </div>
        </div>
      )}

      {isLoading && (
        <PageCard>
          <LoadingSkeleton lines={4} height="2rem" />
        </PageCard>
      )}

      {isError && (
        <ErrorState message={error?.message ?? 'Failed to load browser sessions'} onRetry={refetch} />
      )}

      {!isLoading && !isError && (!sessions || sessions.length === 0) && (
        <EmptyState
          title="No saved browser sessions"
          description="Click New Session to authenticate with a site."
          action={{ label: 'New Session', onClick: () => navigate('/browser-sessions/stream') }}
        />
      )}

      {!isLoading && sessions && sessions.length > 0 && (
        <PageCard className="page-card--flush">
          <table className="data-table responsive-table">
            <thead>
              <tr>
                <th>Domain</th>
                <th>Status</th>
                <th>Cookies</th>
                <th>Last Saved</th>
                <th>Last Used</th>
                <th>Last Checked</th>
                <th>Headed</th>
                <th className="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.domain}>
                  <td data-label="Domain">
                    <div className="font-semibold">{s.domain}</div>
                  </td>
                  <td data-label="Status">
                    <span className="browser-sessions-status">
                      <span className={`status-dot ${statusClass(s.health_status)}`} />
                      <span>{statusLabel(s.health_status)}</span>
                    </span>
                  </td>
                  <td data-label="Cookies">{s.cookie_count}</td>
                  <td data-label="Last Saved">
                    {s.last_saved ? formatRelativeDate(s.last_saved) : 'Never'}
                  </td>
                  <td data-label="Last Used">
                    {s.last_used ? formatRelativeDate(s.last_used) : 'Never'}
                  </td>
                  <td data-label="Last Checked">
                    {s.last_health_check ? formatRelativeDate(s.last_health_check) : 'Never'}
                  </td>
                  <td data-label="Headed">
                    <input
                      type="checkbox"
                      checked={s.requires_headed}
                      onChange={(e) => handleRequiresHeadedChange(s, e.target.checked)}
                      disabled={requiresHeadedMut.isPending}
                      title="Always use a headed (visible) browser for this site"
                    />
                  </td>
                  <td data-label="Actions" className="text-right">
                    <div className="browser-sessions-actions">
                      <button onClick={() => handleCheck(s.domain)} disabled={checkMut.isPending}>
                        Check Now
                      </button>
                      <button
                        onClick={() => handleReauth(s)}
                        title="Open a browser stream for this site; toggle headed mode on the next screen"
                      >
                        Stream
                      </button>
                      <button
                        onClick={() => handleDelete(s.domain)}
                        className="text-danger border-danger"
                        disabled={deleteMut.isPending}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </PageCard>
      )}
    </div>
  );
}
