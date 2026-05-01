import { useState, useEffect } from 'react';
import { runAudit } from '../api/client';

interface Finding {
  severity: 'critical' | 'warning' | 'info';
  category: string;
  message: string;
  details: Record<string, unknown>;
}

interface AuditFindingsProps {
  findings: Finding[];
  onRefresh: (findings: Finding[]) => void;
}

const severityOrder: Record<string, number> = { critical: 0, warning: 1, info: 2 };

export default function AuditFindings({ findings, onRefresh }: AuditFindingsProps) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [cachedAt, setCachedAt] = useState<string | null>(null);

  const handleRun = async () => {
    setLoading(true);
    try {
      const data = await runAudit();
      onRefresh(data.findings || []);
      if (data.cached_at) setCachedAt(data.cached_at);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (findings.length === 0 && !loading) {
      handleRun();
    }
  }, []);

  const sorted = [...findings].sort(
    (a, b) => (severityOrder[a.severity] ?? 99) - (severityOrder[b.severity] ?? 99)
  );

  const badgeColor = (severity: string) => {
    switch (severity) {
      case 'critical':
        return '#d32f2f';
      case 'warning':
        return '#f57c00';
      default:
        return '#388e3c';
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
        <h2>Audit Findings</h2>
        <button onClick={handleRun} disabled={loading}>
          {loading ? 'Running…' : 'Run audit'}
        </button>
      </div>
      {cachedAt && (
        <p style={{ fontSize: '0.8rem', color: '#888', marginTop: '-0.25rem', marginBottom: '0.5rem' }}>
          Last checked: {cachedAt}
        </p>
      )}
      {sorted.length === 0 && <p>No findings.</p>}
      {sorted.map((f, idx) => (
        <div
          key={idx}
          style={{
            padding: '0.75rem',
            borderBottom: '1px solid #eee',
            cursor: 'pointer',
          }}
          onClick={() => setExpanded(expanded === idx ? null : idx)}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span
              style={{
                padding: '0.15rem 0.4rem',
                borderRadius: '4px',
                background: badgeColor(f.severity),
                color: '#fff',
                fontSize: '0.75rem',
                textTransform: 'uppercase',
              }}
            >
              {f.severity}
            </span>
            <strong>{f.category}</strong>
          </div>
          <p style={{ margin: '0.25rem 0 0', fontSize: '0.9rem' }}>{f.message}</p>
          {expanded === idx && Object.keys(f.details).length > 0 && (
            <pre
              style={{
                marginTop: '0.5rem',
                background: '#f5f5f5',
                padding: '0.5rem',
                borderRadius: '4px',
                fontSize: '0.85rem',
                overflowX: 'auto',
              }}
            >
              {JSON.stringify(f.details, null, 2)}
            </pre>
          )}
        </div>
      ))}
    </div>
  );
}
