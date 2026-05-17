import { useEffect, useState } from 'react';
import { fetchUsers } from '../../api/client';

interface User {
  id: string;
  display_name: string;
}

interface UserDropdownProps {
  value: string;
  onChange: (value: string) => void;
}

export default function UserDropdown({ value, onChange }: UserDropdownProps) {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchUsers()
      .then((data) => {
        if (cancelled) return;
        setUsers(data.users || []);
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
    return <div style={{ padding: '0.5rem', color: '#888', fontSize: '0.875rem' }}>Loading users…</div>;
  }

  if (error) {
    return (
      <div style={{ padding: '0.5rem', color: '#ef4444', fontSize: '0.875rem' }}>
        Failed to load users
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
      {users.length === 0 && <option value="">No users</option>}
      {users.map((u) => (
        <option key={u.id} value={u.id}>
          {u.display_name}
        </option>
      ))}
    </select>
  );
}
