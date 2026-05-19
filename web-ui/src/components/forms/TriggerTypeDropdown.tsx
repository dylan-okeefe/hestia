import { TRIGGER_LABELS } from '../../lib/labels';
import './dropdowns.css';

interface TriggerTypeDropdownProps {
  value: string;
  onChange: (value: string) => void;
}

export default function TriggerTypeDropdown({ value, onChange }: TriggerTypeDropdownProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="form-select form-select--full"
    >
      {Object.entries(TRIGGER_LABELS).map(([key, label]) => (
        <option key={key} value={key}>
          {label}
        </option>
      ))}
    </select>
  );
}
