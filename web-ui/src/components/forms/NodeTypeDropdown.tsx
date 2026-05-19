import { NODE_TYPE_LABELS } from '../../lib/labels';
import './dropdowns.css';

interface NodeTypeDropdownProps {
  value: string;
  onChange: (value: string) => void;
}

export default function NodeTypeDropdown({ value, onChange }: NodeTypeDropdownProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="form-select form-select--full"
    >
      {Object.entries(NODE_TYPE_LABELS).map(([key, label]) => (
        <option key={key} value={key}>
          {label}
        </option>
      ))}
    </select>
  );
}
