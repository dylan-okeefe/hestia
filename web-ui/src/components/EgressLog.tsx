import { useEffect, useState } from 'react';
import { fetchEgress } from '../api/client';

interface EgressEvent {
  id: string;
  url: string;
  domain: string;
  status: number;
  size: number;
  created_at: string;
}

function stripQuery(url: string): string {
  try {
    const u = new URL(url);
    return `${u.origin}${u.pathname}`;
  } catch {
    return url;
  }
}

export default function EgressLog() {
  const [events, setEvents] = useState<EgressEvent[]>([]);
  const [domain, setDomain] = useState('');
  const [since, setSince] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchEgress(domain || undefined, since || undefined);
      setEvents(data.events || []);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    handleSearch();
  }, []);

  return (
    <div>
      <h2>Egress Log</h2>
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        <label>
          Domain:{ ' '}
          <input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="example.com" />
        </label>
        <label>
          Since:{ ' '}
          <input type="datetime-local" value={since} onChange={(e) => setSince(e.target.value)} />
        </label>
        <button onClick={handleSearch} disabled={loading}>
          {loading ? 'Loading…' : 'Search'}
        </button>
      </div>
      {error && <p style={{ color: 'red' }}>{error}</p>}
      {events.length === 0 && !loading && !error && <p>No events found.</p>}
      {events.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #ccc', textAlign: 'left' }}>
              <th>URL</th>
              <th>Status</th>
              <th>Size</th>
              <th>Timestamp</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.id} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ wordBreak: 'break-all' }}>{stripQuery(e.url)}</td>
                <td>{e.status}</td>
                <td>{e.size}</td>
                <td>{e.created_at ? new Date(e.created_at).toLocaleString() : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
