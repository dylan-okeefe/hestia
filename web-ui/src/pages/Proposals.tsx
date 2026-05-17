import { useEffect, useState } from 'react';
import { fetchProposals, acceptProposal, rejectProposal } from '../api/client';
import PageCard from '../components/layout/PageCard';
import LoadingSkeleton from '../components/layout/LoadingSkeleton';
import ErrorState from '../components/layout/ErrorState';
import EmptyState from '../components/layout/EmptyState';
import { formatDate } from '../lib/format';

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
      setError(err.message || 'Failed to accept proposal');
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
      setError(err.message || 'Failed to reject proposal');
    } finally {
      setActingId(null);
    }
  };

  const pendingCount = proposals.filter((p) => p.status === 'pending').length;

  const outcomeBadge = (status: string) => {
    const colors: Record<string, { bg: string; color: string }> = {
      accepted: { bg: '#dcfce7', color: '#166534' },
      rejected: { bg: '#fee2e2', color: '#991b1b' },
      deferred: { bg: '#fef3c7', color: '#92400e' },
      pending: { bg: '#eff6ff', color: '#1e40af' },
    };
    const style = colors[status] ?? { bg: '#f3f4f6', color: '#374151' };
    return (
      <span
        style={{
          display: 'inline-block',
          padding: '0.15rem 0.5rem',
          borderRadius: '12px',
          fontSize: '0.75rem',
          fontWeight: 600,
          background: style.bg,
          color: style.color,
          textTransform: 'capitalize',
        }}
      >
        {status}
      </span>
    );
  };

  return (
    <div style={{ padding: '1rem' }}>
      <h1 style={{ marginBottom: '1rem' }}>
        Proposals{' '}
        {pendingCount > 0 && (
          <span
            style={{
              background: '#d32f2f',
              color: '#fff',
              borderRadius: '12px',
              padding: '0.15rem 0.5rem',
              fontSize: '0.85rem',
              verticalAlign: 'middle',
            }}
          >
            {pendingCount}
          </span>
        )}
      </h1>

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        <button
          onClick={() => setTab('pending')}
          style={{
            fontWeight: tab === 'pending' ? 'bold' : 'normal',
            borderBottom: tab === 'pending' ? '2px solid #1976d2' : '2px solid transparent',
            background: 'transparent',
            border: 'none',
            borderRadius: 0,
            cursor: 'pointer',
            padding: '0.25rem 0.5rem',
          }}
        >
          Pending
        </button>
        <button
          onClick={() => setTab('history')}
          style={{
            fontWeight: tab === 'history' ? 'bold' : 'normal',
            borderBottom: tab === 'history' ? '2px solid #1976d2' : '2px solid transparent',
            background: 'transparent',
            border: 'none',
            borderRadius: 0,
            cursor: 'pointer',
            padding: '0.25rem 0.5rem',
          }}
        >
          History
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
          title={tab === 'pending' ? 'No pending proposals' : 'No history'}
          description={
            tab === 'pending'
              ? 'There are no proposals awaiting your review. Hestia will create proposals when it needs confirmation for actions.'
              : 'No reviewed proposals yet. Approved or rejected proposals will appear here.'
          }
        />
      )}

      {!loading && proposals.map((p) => (
        <PageCard key={p.id}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem', flexWrap: 'wrap' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                {outcomeBadge(p.status)}
                <span style={{ fontSize: '0.875rem', color: '#888' }}>{p.type}</span>
              </div>
              <p style={{ margin: '0.25rem 0', fontSize: '0.95rem' }}>{p.summary}</p>
              <p style={{ margin: 0, fontSize: '0.8rem', color: '#888' }}>
                Created {formatDate(p.created_at)}
              </p>
            </div>
            {p.status === 'pending' && (
              <div style={{ display: 'flex', gap: '0.5rem', flexShrink: 0 }}>
                <button
                  onClick={() => handleAccept(p.id)}
                  disabled={actingId === p.id}
                  style={{ background: '#dcfce7', color: '#166534', borderColor: '#bbf7d0' }}
                >
                  Approve
                </button>
                <button
                  onClick={() => handleReject(p.id)}
                  disabled={actingId === p.id}
                  style={{ background: '#fee2e2', color: '#991b1b', borderColor: '#fecaca' }}
                >
                  Reject
                </button>
              </div>
            )}
          </div>
        </PageCard>
      ))}
    </div>
  );
}
