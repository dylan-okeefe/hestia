import { TRUST_PRESET_LABELS } from '../../lib/labels';
import './dropdowns.css';

interface TrustPresetDropdownProps {
  value: string;
  onChange: (value: string) => void;
}

export default function TrustPresetDropdown({ value, onChange }: TrustPresetDropdownProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="form-select form-select--full"
    >
      {Object.entries(TRUST_PRESET_LABELS).map(([key, label]) => (
        <option key={key} value={key}>
          {label}
        </option>
      ))}
    </select>
  );
}
