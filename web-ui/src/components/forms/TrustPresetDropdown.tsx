import { TRUST_PRESET_LABELS } from '../../lib/labels';

interface TrustPresetDropdownProps {
  value: string;
  onChange: (value: string) => void;
}

export default function TrustPresetDropdown({ value, onChange }: TrustPresetDropdownProps) {
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
      {Object.entries(TRUST_PRESET_LABELS).map(([key, label]) => (
        <option key={key} value={key}>
          {label}
        </option>
      ))}
    </select>
  );
}
