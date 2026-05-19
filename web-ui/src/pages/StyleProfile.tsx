import { useState, useEffect, useCallback } from 'react';
import { useCurrentUser } from '../hooks/useCurrentUser';
import { fetchStyleProfile, deleteStyleMetric } from '../api/client';
import PageCard from '../components/layout/PageCard';
import LoadingSkeleton from '../components/layout/LoadingSkeleton';
import ErrorState from '../components/layout/ErrorState';
import EmptyState from '../components/layout/EmptyState';
import { TEXT } from '../lib/text';
import './StyleProfile.css';

interface Metric {
  key: string;
  value: unknown;
}

export default function StyleProfile() {
  const { user, isLoading: userLoading, error: userError } = useCurrentUser();

  const identities = user?.identities ?? [];
  const [selectedIdentity, setSelectedIdentity] = useState(0);

  const platform = identities[selectedIdentity]?.platform ?? 'cli';
  const platformUser = identities[selectedIdentity]?.platform_user ?? 'default';

  const [profile, setProfile] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [confirmReset, setConfirmReset] = useState(false);

  const loadProfile = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchStyleProfile(platform, platformUser);
      setProfile(data.profile || {});
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [platform, platformUser]);

  useEffect(() => {
    loadProfile();
  }, [loadProfile, refreshKey]);

  const handleReset = async () => {
    try {
      const keys = Object.keys(profile);
      for (const key of keys) {
        await deleteStyleMetric(platform, platformUser, key);
      }
      setConfirmReset(false);
      setRefreshKey((k) => k + 1);
    } catch (err: any) {
      setError(err.message || TEXT.styleProfile.resetError);
    }
  };

  const metrics: Metric[] = Object.entries(profile).map(([key, value]) => ({ key, value }));

  if (userLoading) {
    return (
      <div className="style-profile-page">
        <PageCard>
          <LoadingSkeleton lines={3} />
        </PageCard>
      </div>
    );
  }

  if (userError) {
    return (
      <div className="style-profile-page">
        <ErrorState message={userError} />
      </div>
    );
  }

  return (
    <div className="style-profile-page">
      <div className="style-profile-header">
        <h1 className="style-profile-title">{TEXT.styleProfile.title}</h1>
        {metrics.length > 0 && (
          <button onClick={() => setConfirmReset(true)} className="text-danger" className="border-danger">
            {TEXT.styleProfile.resetButton}
          </button>
        )}
      </div>

      <PageCard className="mb-4">
        <div className="style-profile-info-grid">
          <div>
            <span className="style-profile-info-label">{TEXT.styleProfile.platformLabel}</span>
            <div className="style-profile-info-value">{platform}</div>
          </div>
          <div>
            <span className="style-profile-info-label">{TEXT.styleProfile.userLabel}</span>
            <div className="font-semibold">{platformUser}</div>
          </div>
          {identities.length > 1 && (
            <div>
              <span className="style-profile-info-label">{TEXT.styleProfile.identityLabel}</span>
              <select
                value={selectedIdentity}
                onChange={(e) => setSelectedIdentity(Number(e.target.value))}
                className="form-select"
                className="ml-2"
              >
                {identities.map((id, idx) => (
                  <option key={idx} value={idx}>
                    {id.platform} — {id.platform_user}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </PageCard>

      {loading && (
        <PageCard>
          <LoadingSkeleton lines={4} height="2rem" />
        </PageCard>
      )}

      {error && <ErrorState message={error} onRetry={() => setRefreshKey((k) => k + 1)} />}

      {!loading && !error && metrics.length === 0 && (
        <EmptyState
          title={TEXT.styleProfile.emptyTitle}
          description={TEXT.styleProfile.emptyDescription}
        />
      )}

      {!loading && metrics.length > 0 && (
        <div className="grid-auto-220">
          {metrics.map((m) => (
            <PageCard key={m.key}>
              <div className="style-profile-metric-key">{m.key}</div>
              <div className="style-profile-metric-value">
                {typeof m.value === 'object' ? JSON.stringify(m.value) : String(m.value)}
              </div>
            </PageCard>
          ))}
        </div>
      )}

      {confirmReset && (
        <div
          className="modal-overlay"
          onClick={() => setConfirmReset(false)}
        >
          <div className="modal modal--sm" onClick={(e) => e.stopPropagation()}>
            <h3>{TEXT.styleProfile.resetConfirmTitle}</h3>
            <p className="text-small text-secondary">
              {TEXT.styleProfile.resetConfirmDescription(metrics.length, platformUser, platform)}
            </p>
            <div className="row-center gap-2 mt-4">
              <button onClick={() => setConfirmReset(false)}>{TEXT.common.cancel}</button>
              <button onClick={handleReset} className="text-danger" className="border-danger">
                {TEXT.styleProfile.resetConfirmButton}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
