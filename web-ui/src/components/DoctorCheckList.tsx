import { useState, useEffect } from 'react';
import { runDoctor } from '../api/client';
import { HEALTH_CHECK_LABELS, label } from '../lib/labels';
import { formatRelativeDate } from '../lib/format';
import PageCard from './layout/PageCard';
import { TEXT } from '../lib/text';
import './DoctorCheckList.css';

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

  const fillClass = passRate === 100 ? 'progress-bar__fill--success' : passRate >= 50 ? 'progress-bar__fill--warning' : 'progress-bar__fill--danger';

  return (
    <PageCard style={{ transition: 'box-shadow 0.3s ease', boxShadow: flash ? '0 0 0 2px var(--color-primary)' : undefined }}>
      <div className="row-between mb-2">
        <h2>{TEXT.healthChecks.title}</h2>
        <button onClick={handleRerun} disabled={loading}>
          {loading ? TEXT.healthChecks.rerunButtonLoading : TEXT.healthChecks.rerunButton}
        </button>
      </div>
      {cachedAt && (
        <p className="doctor-check-list__cached">
          {TEXT.healthChecks.lastChecked(formatRelativeDate(cachedAt))}
        </p>
      )}
      {checks.length > 0 && (
        <div className="doctor-check-list__progress">
          <div className="progress-bar">
            <div
              className={`progress-bar__fill ${fillClass}`}
              style={{ width: `${passRate}%` }}
            />
          </div>
          <div className="text-xs text-secondary mt-1">
            {TEXT.healthChecks.passRate(passRate, checks.filter((c) => c.ok).length, checks.length)}
          </div>
        </div>
      )}
      {checks.length === 0 && <p>{TEXT.healthChecks.noChecksAvailable}</p>}
      {checks.map((c) => (
        <div key={c.name}>
          <div
            className="doctor-check-list__item"
            onClick={() => setExpanded(expanded === c.name ? null : c.name)}
          >
            <span
              className={`doctor-check-list__dot ${c.ok ? 'doctor-check-list__dot--ok' : 'doctor-check-list__dot--fail'}`}
            />
            <span className="flex-1">{label(HEALTH_CHECK_LABELS, c.name)}</span>
            <span className="text-xs text-muted">
              {expanded === c.name ? '▲' : '▼'}
            </span>
          </div>
          {expanded === c.name && (
            <div className="doctor-check-list__detail">
              {c.detail && (
                <div className={`doctor-check-list__detail-text ${c.ok ? 'text-secondary' : 'text-danger'}`}>
                  <strong>{TEXT.healthChecks.detailLabel}</strong> {c.detail}
                </div>
              )}
              {!c.ok && REMEDIATION[c.name] && (
                <div className="doctor-check-list__remediation">
                  <strong>{TEXT.healthChecks.remediationLabel}</strong> {REMEDIATION[c.name]}
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </PageCard>
  );
}
