import { useEffect, useState } from 'react';
import { fetchStyleProfile, deleteStyleMetric } from '../api/client';

interface Metric {
  key: string;
  value: unknown;
}

export default function StyleProfile() {
  const [platform, setPlatform] = useState('cli');
  const [user, setUser] = useState('default');
  const [profile, setProfile] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchStyleProfile(platform, user)
      .then((data) => {
        setProfile(data.profile || {});
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [platform, user, refreshKey]);

  const handleReset = async (metric: string) => {
    const res = await deleteStyleMetric(platform, user, metric);
    if (res.ok) {
      setRefreshKey((k) => k + 1);
    }
  };

  const metrics: Metric[] = Object.entries(profile).map(([key, value]) => ({ key, value }));

  return (
    <div style={{ padding: '1rem' }}>
      <h1>Style Profile</h1>
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        <label>
          Platform:{ ' '}
          <input value={platform} onChange={(e) => setPlatform(e.target.value)} />
        </label>
        <label>
          User:{ ' '}
          <input value={user} onChange={(e) => setUser(e.target.value)} />
        </label>
      </div>
      {loading && <p>Loading profile…</p>}
      {error && <p style={{ color: 'red' }}>{error}</p>}
      {!loading && metrics.length === 0 && <p>No metrics found.</p>}
      {metrics.map((m) => (
        <div
          key={m.key}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '0.75rem',
            borderBottom: '1px solid #eee',
          }}
        >
          <div>
            <strong>{m.key}</strong>
            <div style={{ fontSize: '0.9rem', color: '#555' }}>
              {typeof m.value === 'object' ? JSON.stringify(m.value) : String(m.value)}
            </div>
          </div>
          <button onClick={() => handleReset(m.key)}>Reset</button>
        </div>
      ))}
    </div>
  );
}
