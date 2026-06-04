import { useEffect, useState } from 'react';
import { fetchUsers, type User, type UserIdentity } from '../../api/client';
import './dropdowns.css';

interface UserDropdownProps {
  value: string;
  onChange: (value: string) => void;
  platform?: string;
}

interface PlatformUserOption {
  key: string;
  label: string;
  value: string;
}

export default function UserDropdown({ value, onChange, platform }: UserDropdownProps) {
  const [options, setOptions] = useState<PlatformUserOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchUsers()
      .then((data) => {
        if (cancelled) return;
        const users = data.users || [];
        const opts: PlatformUserOption[] = [];

        for (const user of users) {
          const identities = user.identities || [];
          const platformIdents = platform
            ? identities.filter((i: UserIdentity) => i.platform === platform)
            : identities;

          for (const ident of platformIdents) {
            const displayName = user.display_name || ident.platform_user;
            const label = platformIdents.length > 1 || users.filter((u: User) =>
              u.identities?.some((i: UserIdentity) => i.platform === platform && i.platform_user === ident.platform_user)
            ).length > 1
              ? `${displayName} (${ident.platform_user})`
              : displayName;

            opts.push({
              key: `${user.id}-${ident.platform}-${ident.platform_user}`,
              label,
              value: ident.platform_user,
            });
          }
        }

        // De-duplicate by value (same platform_user)
        const seen = new Set<string>();
        const deduped = opts.filter((o) => {
          if (seen.has(o.value)) return false;
          seen.add(o.value);
          return true;
        });

        setOptions(deduped);
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
  }, [platform]);

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
      <option value="">{platform ? `Select ${platform} user…` : 'Select user…'}</option>
      {options.length === 0 && (
        <option value="" disabled>
          {platform ? `No users found for ${platform}` : 'No users'}
        </option>
      )}
      {options.map((o) => (
        <option key={o.key} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
