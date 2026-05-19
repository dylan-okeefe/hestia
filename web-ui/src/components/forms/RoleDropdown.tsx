import { ROLE_LABELS } from '../../lib/labels';
import './dropdowns.css';

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
      className="form-select form-select--full"
    >
      {Object.entries(ROLE_LABELS).map(([key, label]) => (
        <option key={key} value={key} disabled={disabledRoles.includes(key)}>
          {label}
        </option>
      ))}
    </select>
  );
}
