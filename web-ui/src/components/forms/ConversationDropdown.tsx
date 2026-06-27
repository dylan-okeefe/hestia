import { useEffect, useState } from 'react';
import { fetchConversations, type Conversation } from '../../api/client';
import './dropdowns.css';

interface ConversationDropdownProps {
  value: string;
  onChange: (value: string) => void;
  platform?: string;
}

interface ConversationOption {
  key: string;
  label: string;
  value: string;
}

export default function ConversationDropdown({ value, onChange, platform }: ConversationDropdownProps) {
  const [options, setOptions] = useState<ConversationOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    if (!platform) {
      setOptions([]);
      setLoading(false);
      return;
    }

    fetchConversations(platform)
      .then((data) => {
        if (cancelled) return;
        const conversations = data.sessions || [];
        const opts: ConversationOption[] = conversations.map((c: Conversation) => {
          const display = c.title?.trim() || c.platform_user;
          const label = c.title?.trim()
            ? `${display} (${c.platform_user})`
            : display;
          return {
            key: `${c.platform}-${c.platform_user}-${c.id}`,
            label,
            value: c.platform_user,
          };
        });
        setOptions(opts);
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
    return <div className="text-small text-muted p-2">Loading conversations…</div>;
  }

  if (error) {
    return (
      <div className="text-small text-danger p-2">
        Failed to load conversations
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
      <option value="">{platform ? `Select ${platform} conversation…` : 'Select conversation…'}</option>
      {options.length === 0 && (
        <option value="" disabled>
          {platform ? `No conversations found for ${platform}` : 'No conversations'}
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
