import { useEffect, useState } from 'react';
import { fetchUsers } from '../../api/client';
import './dropdowns.css';

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
    return <div className="text-small text-muted p-2">Loading users…</div>;
  }

  if (error) {
    return (
      <div className="text-small text-danger p-2">
        Failed to load users
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
      {users.length === 0 && <option value="">No users</option>}
      {users.map((u) => (
        <option key={u.id} value={u.id}>
          {u.display_name}
        </option>
      ))}
    </select>
  );
}
