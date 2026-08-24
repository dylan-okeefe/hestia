import { useEffect, useState } from 'react';
import { fetchProposals, acceptProposal, rejectProposal, deferProposal } from '../api/client';
import PageCard from '../components/layout/PageCard';
import LoadingSkeleton from '../components/layout/LoadingSkeleton';
import ErrorState from '../components/layout/ErrorState';
import EmptyState from '../components/layout/EmptyState';
import { formatDate } from '../lib/format';
import { TEXT } from '../lib/text';
import './Proposals.css';

interface Proposal {
  id: string;
  type: string;
  summary: string;
  confidence: number;
  evidence: string[];
  action: Record<string, unknown>;
  status: string;
  created_at: string | null;
  expires_at: string | null;
}

type Tab = 'pending' | 'history';

export default function Proposals() {
  const [tab, setTab] = useState<Tab>('pending');
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [actingId, setActingId] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    const status = tab === 'pending' ? 'pending' : undefined;
    fetchProposals(status)
      .then((data) => {
        let list: Proposal[] = data.proposals || [];
        if (tab === 'history') {
          list = list.filter((p: Proposal) => p.status !== 'pending');
        }
        setProposals(list);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [tab, refreshKey]);

  const handleAccept = async (id: string) => {
    setActingId(id);
    try {
      await acceptProposal(id);
      setRefreshKey((k) => k + 1);
    } catch (err: any) {
      setError(err.message || TEXT.proposals.acceptError);
    } finally {
      setActingId(null);
    }
  };

  const handleReject = async (id: string) => {
    setActingId(id);
    try {
      await rejectProposal(id, '');
      setRefreshKey((k) => k + 1);
    } catch (err: any) {
      setError(err.message || TEXT.proposals.rejectError);
    } finally {
      setActingId(null);
    }
  };

  // D6/UX-003: the backend has always supported deferring proposals; the
  // button simply never existed.
  const handleDefer = async (id: string) => {
    setActingId(id);
    try {
      await deferProposal(id);
      setRefreshKey((k) => k + 1);
    } catch (err: any) {
      setError(err.message || 'Failed to defer proposal');
    } finally {
      setActingId(null);
    }
  };

  const pendingCount = proposals.filter((p) => p.status === 'pending').length;

  const outcomeBadgeClass = (status: string) => {
    switch (status) {
      case 'accepted': return 'proposals-outcome-badge--accepted';
      case 'rejected': return 'proposals-outcome-badge--rejected';
      case 'deferred': return 'proposals-outcome-badge--deferred';
      case 'pending': return 'proposals-outcome-badge--pending';
      default: return 'proposals-outcome-badge--default';
    }
  };

  return (
    <div className="proposals-page">
      <h1 className="proposals-title">
        {TEXT.proposals.title}{' '}
        {pendingCount > 0 && (
          <span className="proposals-count-badge">
            {pendingCount}
          </span>
        )}
      </h1>

      <div className="proposals-tabs">
        <button
          onClick={() => setTab('pending')}
          className={tab === 'pending' ? 'proposals-tab proposals-tab--active' : 'proposals-tab'}
        >
          {TEXT.proposals.tabPending}
        </button>
        <button
          onClick={() => setTab('history')}
          className={tab === 'history' ? 'proposals-tab proposals-tab--active' : 'proposals-tab'}
        >
          {TEXT.proposals.tabHistory}
        </button>
      </div>

      {loading && (
        <PageCard>
          <LoadingSkeleton lines={3} height="3rem" />
        </PageCard>
      )}

      {error && <ErrorState message={error} onRetry={() => setRefreshKey((k) => k + 1)} />}

      {!loading && !error && proposals.length === 0 && (
        <EmptyState
          title={tab === 'pending' ? TEXT.proposals.pendingEmptyTitle : TEXT.proposals.historyEmptyTitle}
          description={
            tab === 'pending'
              ? TEXT.proposals.pendingEmptyDescription
              : TEXT.proposals.historyEmptyDescription
          }
        />
      )}

      {!loading && proposals.map((p) => (
        <PageCard key={p.id}>
          <div className="proposals-card-header">
            <div>
              <div className="proposals-card-meta">
                <span className={`proposals-outcome-badge ${outcomeBadgeClass(p.status)}`}>
                  {p.status}
                </span>
                <span className="proposals-card-type">{p.type}</span>
              </div>
              <p className="proposals-card-summary">{p.summary}</p>
              <p className="proposals-card-date">
                {TEXT.proposals.created(formatDate(p.created_at))}
              </p>
            </div>
            {p.status === 'pending' && (
              <div className="proposals-card-actions">
                <button
                  onClick={() => handleAccept(p.id)}
                  disabled={actingId === p.id}
                  className="proposals-approve-btn"
                >
                  {TEXT.proposals.approveButton}
                </button>
                <button
                  onClick={() => handleReject(p.id)}
                  disabled={actingId === p.id}
                  className="proposals-reject-btn"
                >
                  {TEXT.proposals.rejectButton}
                </button>
                <button
                  onClick={() => handleDefer(p.id)}
                  disabled={actingId === p.id}
                  className="proposals-defer-btn"
                >
                  Defer
                </button>
              </div>
            )}
          </div>
        </PageCard>
      ))}
    </div>
  );
}
