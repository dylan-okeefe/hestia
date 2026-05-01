import { useState, useEffect } from 'react';
import { runDoctor } from '../api/client';

interface Check {
  name: string;
  ok: boolean;
  detail: string;
}

interface DoctorCheckListProps {
  checks: Check[];
  onRefresh: (checks: Check[]) => void;
}

export default function DoctorCheckList({ checks, onRefresh }: DoctorCheckListProps) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [cachedAt, setCachedAt] = useState<string | null>(null);

  const handleRerun = async () => {
    setLoading(true);
    try {
      const data = await runDoctor();
      onRefresh(data.checks || []);
      if (data.cached_at) setCachedAt(data.cached_at);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (checks.length === 0 && !loading) {
      handleRerun();
    }
  }, []);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
        <h2>Health Checks</h2>
        <button onClick={handleRerun} disabled={loading}>
          {loading ? 'Running…' : 'Re-run checks'}
        </button>
      </div>
      {cachedAt && (
        <p style={{ fontSize: '0.8rem', color: '#888', marginTop: '-0.25rem', marginBottom: '0.5rem' }}>
          Last checked: {cachedAt}
        </p>
      )}
      {checks.length === 0 && <p>No checks available.</p>}
      {checks.map((c) => (
        <div key={c.name}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.5rem',
              borderBottom: '1px solid #eee',
              cursor: 'pointer',
            }}
            onClick={() => setExpanded(expanded === c.name ? null : c.name)}
          >
            <span
              style={{
                width: '12px',
                height: '12px',
                borderRadius: '50%',
                background: c.ok ? '#4caf50' : '#f44336',
                display: 'inline-block',
                flexShrink: 0,
              }}
            />
            <span style={{ flex: 1 }}>{c.name}</span>
          </div>
          {expanded === c.name && c.detail && (
            <div style={{ padding: '0.5rem', fontSize: '0.9rem', color: '#555', background: '#f9f9f9' }}>
              {c.detail}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
