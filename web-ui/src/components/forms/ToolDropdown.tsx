import { useEffect, useState } from 'react';
import { fetchTools } from '../../api/client';

interface Tool {
  name: string;
  description: string;
}

interface ToolDropdownProps {
  value: string;
  onChange: (value: string) => void;
  includeAny?: boolean;
}

export default function ToolDropdown({ value, onChange, includeAny = false }: ToolDropdownProps) {
  const [tools, setTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchTools()
      .then((data) => {
        if (cancelled) return;
        setTools(data.tools || []);
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
    return <div style={{ padding: '0.5rem', color: '#888', fontSize: '0.875rem' }}>Loading tools…</div>;
  }

  if (error) {
    return (
      <div style={{ padding: '0.5rem', color: '#ef4444', fontSize: '0.875rem' }}>
        Failed to load tools
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
      {includeAny && <option value="">— Any —</option>}
      {tools.length === 0 && <option value="">No tools</option>}
      {tools.map((t) => (
        <option key={t.name} value={t.name}>
          {t.name}
        </option>
      ))}
    </select>
  );
}
