import { useState } from 'react';
import { acceptProposal, rejectProposal, deferProposal } from '../api/client';

interface Proposal {
  id: string;
  type: string;
  summary: string;
  confidence: number;
  evidence: string[];
  action: Record<string, unknown>;
  status: string;
}

interface ProposalCardProps {
  proposal: Proposal;
  onAction: () => void;
}

export default function ProposalCard({ proposal, onAction }: ProposalCardProps) {
  const [rejectNote, setRejectNote] = useState('');
  const [showReject, setShowReject] = useState(false);
  const [acting, setActing] = useState(false);
  const isPending = proposal.status === 'pending';

  const handleAccept = async () => {
    setActing(true);
    try {
      await acceptProposal(proposal.id);
    } finally {
      setActing(false);
      onAction();
    }
  };

  const handleReject = async () => {
    setActing(true);
    try {
      await rejectProposal(proposal.id, rejectNote);
      setShowReject(false);
      setRejectNote('');
    } finally {
      setActing(false);
      onAction();
    }
  };

  const handleDefer = async () => {
    setActing(true);
    try {
      await deferProposal(proposal.id);
    } finally {
      setActing(false);
      onAction();
    }
  };

  return (
    <div
      data-testid="proposal-card"
      style={{
        border: '1px solid #ddd',
        borderRadius: '8px',
        padding: '1rem',
        marginBottom: '1rem',
        background: '#fff',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0 }}>{proposal.type}</h3>
        <span
          style={{
            padding: '0.25rem 0.5rem',
            borderRadius: '4px',
            background: '#eee',
            fontSize: '0.85rem',
          }}
        >
          {proposal.status}
        </span>
      </div>
      <p style={{ margin: '0.5rem 0' }}>{proposal.summary}</p>
      <p style={{ margin: '0.25rem 0', fontSize: '0.9rem', color: '#555' }}>
        Confidence: {(proposal.confidence * 100).toFixed(0)}%
      </p>
      {proposal.evidence.length > 0 && (
        <ul style={{ margin: '0.5rem 0', paddingLeft: '1.25rem', fontSize: '0.9rem', color: '#555' }}>
          {proposal.evidence.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
      {proposal.action && Object.keys(proposal.action).length > 0 && (
        <pre
          style={{
            background: '#f5f5f5',
            padding: '0.5rem',
            borderRadius: '4px',
            fontSize: '0.85rem',
            overflowX: 'auto',
          }}
        >
          {JSON.stringify(proposal.action, null, 2)}
        </pre>
      )}
      {isPending && (
        <>
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem' }}>
            <button onClick={handleAccept} disabled={acting}>
              Accept
            </button>
            <button onClick={() => setShowReject((s) => !s)} disabled={acting}>
              Reject
            </button>
            <button onClick={handleDefer} disabled={acting}>
              Defer
            </button>
          </div>
          {showReject && (
            <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.5rem' }}>
              <input
                type="text"
                placeholder="Reason for rejection"
                value={rejectNote}
                onChange={(e) => setRejectNote(e.target.value)}
                style={{ flex: 1 }}
              />
              <button onClick={handleReject} disabled={acting || !rejectNote.trim()}>
                Confirm Reject
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
