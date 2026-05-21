import { useState } from 'react';
import { acceptProposal, rejectProposal, deferProposal } from '../api/client';
import './ProposalCard.css';

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
      className="proposal-card"
    >
      <div className="proposal-card__header">
        <h3>{proposal.type}</h3>
        <span className="proposal-card__status">
          {proposal.status}
        </span>
      </div>
      <p className="proposal-card__summary">{proposal.summary}</p>
      <p className="proposal-card__confidence">
        Confidence: {(proposal.confidence * 100).toFixed(0)}%
      </p>
      {proposal.evidence.length > 0 && (
        <ul className="proposal-card__evidence">
          {proposal.evidence.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
      {proposal.action && Object.keys(proposal.action).length > 0 && (
        <pre className="proposal-card__action-pre">
          {JSON.stringify(proposal.action, null, 2)}
        </pre>
      )}
      {isPending && (
        <>
          <div className="proposal-card__actions">
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
            <div className="proposal-card__reject-row">
              <input
                type="text"
                placeholder="Reason for rejection"
                value={rejectNote}
                onChange={(e) => setRejectNote(e.target.value)}
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
