import { useEffect, useState } from 'react';
import { fetchAuthStatus } from '../../api/client';

interface PlatformDropdownProps {
  value: string;
  onChange: (value: string) => void;
  includeEmpty?: boolean;
}

const STATIC_PLATFORMS = ['cli', 'matrix', 'telegram', 'email', 'discord'];

export default function PlatformDropdown({ value, onChange, includeEmpty = false }: PlatformDropdownProps) {
  const [platforms, setPlatforms] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchAuthStatus()
      .then((data) => {
        if (cancelled) return;
        const list = data.available_platforms?.length ? data.available_platforms : STATIC_PLATFORMS;
        setPlatforms(list);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return <div style={{ padding: '0.5rem', color: '#888', fontSize: '0.875rem' }}>Loading platforms…</div>;
  }

  if (error) {
    return (
      <div style={{ padding: '0.5rem', color: '#ef4444', fontSize: '0.875rem' }}>
        Failed to load platforms
        <button onClick={() => window.location.reload()} style={{ marginLeft: '0.5rem', fontSize: '0.75rem' }}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      style={{
        width: '100%',
        padding: '0.5rem',
        borderRadius: '4px',
        border: '1px solid #ccc',
        fontFamily: 'inherit',
        fontSize: '0.875rem',
      }}
    >
      {includeEmpty && <option value="">— Select —</option>}
      {platforms.map((p) => (
        <option key={p} value={p}>
          {p}
        </option>
      ))}
    </select>
  );
}
