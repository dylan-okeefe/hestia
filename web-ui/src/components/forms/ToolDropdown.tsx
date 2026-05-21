import { useEffect, useState } from 'react';
import { fetchTools } from '../../api/client';
import './dropdowns.css';

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
    return <div className="text-small text-muted p-2">Loading tools…</div>;
  }

  if (error) {
    return (
      <div className="text-small text-danger p-2">
        Failed to load tools
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
