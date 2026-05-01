import { useEffect, useState } from 'react';
import { fetchProposals } from '../api/client';
import ProposalCard from '../components/ProposalCard';

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

  useEffect(() => {
    setLoading(true);
    const status = tab === 'pending' ? 'pending' : '';
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

  const handleAction = () => {
    setRefreshKey((k) => k + 1);
  };

  const pendingCount = tab === 'pending' ? proposals.length : 0;

  return (
    <div style={{ padding: '1rem' }}>
      <h1>
        Proposals{' '}
        {tab === 'pending' && pendingCount > 0 && (
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
          }}
        >
          Pending
        </button>
        <button
          onClick={() => setTab('history')}
          style={{
            fontWeight: tab === 'history' ? 'bold' : 'normal',
            borderBottom: tab === 'history' ? '2px solid #1976d2' : '2px solid transparent',
          }}
        >
          History
        </button>
      </div>
      {loading && <p>Loading proposals…</p>}
      {error && <p style={{ color: 'red' }}>{error}</p>}
      {!loading && proposals.length === 0 && <p>No proposals found.</p>}
      {proposals.map((p) => (
        <ProposalCard key={p.id} proposal={p} onAction={handleAction} />
      ))}
    </div>
  );
}
