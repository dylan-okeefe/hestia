import { useEffect, useState } from 'react';
import { fetchAuthStatus } from '../../api/client';
import './dropdowns.css';

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
    return <div className="text-small text-muted p-2">Loading platforms…</div>;
  }

  if (error) {
    return (
      <div className="text-small text-danger p-2">
        Failed to load platforms
        <button onClick={() => window.location.reload()} className="text-xs ml-2">
          Retry
        </button>
      </div>
    );
  }

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="form-select form-select--full"
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
