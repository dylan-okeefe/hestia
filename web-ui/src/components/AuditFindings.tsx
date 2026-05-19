import { useState, useEffect } from 'react';
import { runAudit } from '../api/client';
import './AuditFindings.css';

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

  const severityClass = (severity: string) => {
    switch (severity) {
      case 'critical': return 'audit-findings__severity--critical';
      case 'warning': return 'audit-findings__severity--warning';
      default: return 'audit-findings__severity--info';
    }
  };

  return (
    <div>
      <div className="audit-findings__header">
        <h2>Audit Findings</h2>
        <button onClick={handleRun} disabled={loading}>
          {loading ? 'Running…' : 'Run audit'}
        </button>
      </div>
      {cachedAt && (
        <p className="audit-findings__cached">
          Last checked: {cachedAt}
        </p>
      )}
      {sorted.length === 0 && <p>No findings.</p>}
      {sorted.map((f, idx) => (
        <div
          key={idx}
          className="audit-findings__item"
          onClick={() => setExpanded(expanded === idx ? null : idx)}
        >
          <div className="row-center gap-2">
            <span
              className={`audit-findings__severity ${severityClass(f.severity)}`}
            >
              {f.severity}
            </span>
            <strong>{f.category}</strong>
          </div>
          <p className="audit-findings__message">{f.message}</p>
          {expanded === idx && Object.keys(f.details).length > 0 && (
            <pre className="audit-findings__details">
              {JSON.stringify(f.details, null, 2)}
            </pre>
          )}
        </div>
      ))}
    </div>
  );
}
