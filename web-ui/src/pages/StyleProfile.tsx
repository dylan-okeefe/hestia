import { useState, useEffect, useCallback } from 'react';
import { useCurrentUser } from '../hooks/useCurrentUser';
import { fetchStyleProfile, deleteStyleMetric } from '../api/client';
import PageCard from '../components/layout/PageCard';
import LoadingSkeleton from '../components/layout/LoadingSkeleton';
import ErrorState from '../components/layout/ErrorState';
import EmptyState from '../components/layout/EmptyState';

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
      setError(err.message || 'Failed to reset profile');
    }
  };

  const metrics: Metric[] = Object.entries(profile).map(([key, value]) => ({ key, value }));

  if (userLoading) {
    return (
      <div style={{ padding: '1rem' }}>
        <PageCard>
          <LoadingSkeleton lines={3} />
        </PageCard>
      </div>
    );
  }

  if (userError) {
    return (
      <div style={{ padding: '1rem' }}>
        <ErrorState message={userError} />
      </div>
    );
  }

  return (
    <div style={{ padding: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h1 style={{ margin: 0 }}>Style Profile</h1>
        {metrics.length > 0 && (
          <button onClick={() => setConfirmReset(true)} style={{ color: '#ef4444', borderColor: '#ef4444' }}>
            Reset Profile
          </button>
        )}
      </div>

      <PageCard style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          <div>
            <span style={{ fontSize: '0.875rem', color: '#666' }}>Platform</span>
            <div style={{ fontWeight: 600, textTransform: 'uppercase' }}>{platform}</div>
          </div>
          <div>
            <span style={{ fontSize: '0.875rem', color: '#666' }}>User</span>
            <div style={{ fontWeight: 600 }}>{platformUser}</div>
          </div>
          {identities.length > 1 && (
            <div>
              <span style={{ fontSize: '0.875rem', color: '#666' }}>Identity</span>
              <select
                value={selectedIdentity}
                onChange={(e) => setSelectedIdentity(Number(e.target.value))}
                style={{ marginLeft: '0.5rem', padding: '0.25rem 0.5rem' }}
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
          title="No style metrics"
          description="No style metrics for this identity yet. Hestia builds a style profile over time."
        />
      )}

      {!loading && metrics.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '1rem' }}>
          {metrics.map((m) => (
            <PageCard key={m.key}>
              <div style={{ fontSize: '0.75rem', color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.25rem' }}>
                {m.key}
              </div>
              <div style={{ fontSize: '1.25rem', fontWeight: 600, wordBreak: 'break-word' }}>
                {typeof m.value === 'object' ? JSON.stringify(m.value) : String(m.value)}
              </div>
            </PageCard>
          ))}
        </div>
      )}

      {confirmReset && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setConfirmReset(false)}
        >
          <div
            style={{ width: 360, textAlign: 'center', background: '#fff', border: '1px solid #eee', borderRadius: '8px', padding: '1rem' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ marginTop: 0 }}>Reset style profile?</h3>
            <p style={{ fontSize: '0.875rem', color: '#666' }}>
              This will delete all {metrics.length} metrics for {platformUser} on {platform}.
            </p>
            <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1rem' }}>
              <button onClick={() => setConfirmReset(false)}>Cancel</button>
              <button onClick={handleReset} style={{ color: '#ef4444', borderColor: '#ef4444' }}>
                Reset
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
