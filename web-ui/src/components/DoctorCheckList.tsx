import { useState, useEffect } from 'react';
import { runDoctor } from '../api/client';
import { HEALTH_CHECK_LABELS, label } from '../lib/labels';
import { formatRelativeDate } from '../lib/format';
import PageCard from './layout/PageCard';

interface Check {
  name: string;
  ok: boolean;
  detail: string;
}

const REMEDIATION: Record<string, string> = {
  python_version: 'Ensure Python 3.11+ is installed.',
  dependencies_in_sync: 'Run `uv sync` to update dependencies.',
  config_file_loads: 'Check that config.py exists and is valid Python.',
  config_schema: 'Validate config fields against the schema documentation.',
  allowed_roots_cwd: 'Ensure the current working directory is within allowed_roots.',
  sqlite_dbs_readable: 'Check SQLite database file permissions.',
  llamacpp_reachable: 'Verify llama.cpp server is running and reachable.',
  platform_prereqs: 'Check platform adapter configuration and credentials.',
  voice_prerequisites: 'Install voice dependencies and configure audio devices.',
  trust_preset_resolves: 'Verify the trust preset name in config matches a known preset.',
  trust_preset_safe: 'Review trust preset rules for production safety.',
  memory_epoch: 'Check memory store connectivity and epoch configuration.',
};

interface DoctorCheckListProps {
  checks: Check[];
  onRefresh: (checks: Check[]) => void;
}

export default function DoctorCheckList({ checks, onRefresh }: DoctorCheckListProps) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [cachedAt, setCachedAt] = useState<string | null>(null);
  const [flash, setFlash] = useState(false);

  const handleRerun = async () => {
    setLoading(true);
    setFlash(false);
    try {
      const data = await runDoctor();
      onRefresh(data.checks || []);
      if (data.cached_at) setCachedAt(data.cached_at);
      setFlash(true);
      setTimeout(() => setFlash(false), 800);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (checks.length === 0 && !loading) {
      handleRerun();
    }
  }, []);

  const passRate = checks.length > 0
    ? Math.round((checks.filter((c) => c.ok).length / checks.length) * 100)
    : 0;

  return (
    <PageCard style={{ transition: 'box-shadow 0.3s ease', boxShadow: flash ? '0 0 0 2px #1976d2' : undefined }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
        <h2 style={{ margin: 0 }}>Health Checks</h2>
        <button onClick={handleRerun} disabled={loading}>
          {loading ? 'Running…' : 'Re-run checks'}
        </button>
      </div>
      {cachedAt && (
        <p style={{ fontSize: '0.8rem', color: '#888', marginTop: '-0.25rem', marginBottom: '0.5rem' }}>
          Last checked: {formatRelativeDate(cachedAt)}
        </p>
      )}
      {checks.length > 0 && (
        <div style={{ marginBottom: '0.75rem' }}>
          <div
            style={{
              height: '6px',
              background: '#eee',
              borderRadius: '3px',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${passRate}%`,
                height: '100%',
                background: passRate === 100 ? '#22c55e' : passRate >= 50 ? '#f59e0b' : '#ef4444',
                transition: 'width 0.3s ease',
              }}
            />
          </div>
          <div style={{ fontSize: '0.75rem', color: '#666', marginTop: '0.25rem' }}>
            {passRate}% passing ({checks.filter((c) => c.ok).length}/{checks.length})
          </div>
        </div>
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
            <span style={{ flex: 1 }}>{label(HEALTH_CHECK_LABELS, c.name)}</span>
            <span style={{ fontSize: '0.75rem', color: '#888' }}>
              {expanded === c.name ? '▲' : '▼'}
            </span>
          </div>
          {expanded === c.name && (
            <div style={{ padding: '0.75rem', fontSize: '0.875rem', background: '#f9f9f9', borderBottom: '1px solid #eee' }}>
              {c.detail && (
                <div style={{ marginBottom: '0.5rem', color: '#555' }}>
                  <strong>Detail:</strong> {c.detail}
                </div>
              )}
              {!c.ok && REMEDIATION[c.name] && (
                <div style={{ color: '#92400e', background: '#fef3c7', padding: '0.5rem', borderRadius: '4px' }}>
                  <strong>Remediation:</strong> {REMEDIATION[c.name]}
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </PageCard>
  );
}
