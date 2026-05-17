import { ROLE_LABELS } from '../../lib/labels';

interface RoleDropdownProps {
  value: string;
  onChange: (value: string) => void;
  disabledRoles?: string[];
}

export default function RoleDropdown({ value, onChange, disabledRoles = [] }: RoleDropdownProps) {
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
      {Object.entries(ROLE_LABELS).map(([key, label]) => (
        <option key={key} value={key} disabled={disabledRoles.includes(key)}>
          {label}
        </option>
      ))}
    </select>
  );
}
