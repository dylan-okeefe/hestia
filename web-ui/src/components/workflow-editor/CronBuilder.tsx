import { useEffect, useState } from 'react';
import { CronExpressionParser } from 'cron-parser';
import { formatCron } from '../../lib/format';

const PRESETS = [
  { label: 'Every hour', value: '0 * * * *' },
  { label: 'Every day at 8 AM', value: '0 8 * * *' },
  { label: 'Every Monday', value: '0 0 * * 1' },
  { label: 'Every 5 minutes', value: '*/5 * * * *' },
];

const WEEKDAYS = [
  { label: 'Mon', value: 1 },
  { label: 'Tue', value: 2 },
  { label: 'Wed', value: 3 },
  { label: 'Thu', value: 4 },
  { label: 'Fri', value: 5 },
  { label: 'Sat', value: 6 },
  { label: 'Sun', value: 0 },
];

type Frequency = 'hourly' | 'daily' | 'weekly' | 'custom';

function parseFrequency(cron: string): Frequency {
  if (!cron.trim()) return 'custom';
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return 'custom';
  const [min, hour, dom, mon, dow] = parts;
  if (min === '0' && hour === '*' && dom === '*' && mon === '*' && dow === '*') return 'hourly';
  if (min === '0' && /^\d+$/.test(hour) && dom === '*' && mon === '*' && dow === '*') return 'daily';
  if (min === '0' && hour === '0' && dom === '*' && mon === '*' && /^[0-6](,[0-6])*$/.test(dow)) return 'weekly';
  return 'custom';
}

function buildCron(frequency: Frequency, dailyHour: string, dailyMinute: string, selectedDays: number[], custom: string): string {
  switch (frequency) {
    case 'hourly':
      return '0 * * * *';
    case 'daily': {
      const h = Math.max(0, Math.min(23, parseInt(dailyHour || '0', 10)));
      const m = Math.max(0, Math.min(59, parseInt(dailyMinute || '0', 10)));
      return `${m} ${h} * * *`;
    }
    case 'weekly': {
      const h = Math.max(0, Math.min(23, parseInt(dailyHour || '0', 10)));
      const m = Math.max(0, Math.min(59, parseInt(dailyMinute || '0', 10)));
      const dow = selectedDays.length > 0 ? selectedDays.sort((a, b) => a - b).join(',') : '*';
      return `${m} ${h} * * ${dow}`;
    }
    case 'custom':
      return custom;
  }
}

interface CronBuilderProps {
  value: string;
  onChange: (value: string) => void;
}

export default function CronBuilder({ value, onChange }: CronBuilderProps) {
  const [frequency, setFrequency] = useState<Frequency>(() => parseFrequency(value));
  const [dailyHour, setDailyHour] = useState('8');
  const [dailyMinute, setDailyMinute] = useState('0');
  const [selectedDays, setSelectedDays] = useState<number[]>([1]);
  const [custom, setCustom] = useState(value || '');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const freq = parseFrequency(value);
    setFrequency(freq);
    if (freq === 'custom') {
      setCustom(value);
    } else {
      const parts = value.trim().split(/\s+/);
      if (parts.length === 5) {
        setDailyMinute(parts[0]);
        setDailyHour(parts[1]);
        if (freq === 'weekly' && parts[4] !== '*') {
          setSelectedDays(parts[4].split(',').map((v) => parseInt(v, 10)));
        }
      }
    }
  }, []);

  useEffect(() => {
    const cron = buildCron(frequency, dailyHour, dailyMinute, selectedDays, custom);
    if (cron !== value) {
      onChange(cron);
    }
    validate(cron);
  }, [frequency, dailyHour, dailyMinute, selectedDays, custom]);

  const validate = (v: string) => {
    if (!v.trim()) {
      setError(null);
      return;
    }
    try {
      CronExpressionParser.parse(v);
      setError(null);
    } catch {
      setError('Invalid cron expression');
    }
  };

  const handlePreset = (presetValue: string) => {
    const freq = parseFrequency(presetValue);
    setFrequency(freq);
    if (freq !== 'custom') {
      const parts = presetValue.split(/\s+/);
      setDailyMinute(parts[0]);
      setDailyHour(parts[1]);
      if (freq === 'weekly') {
        setSelectedDays(parts[4].split(',').map((v) => parseInt(v, 10)));
      }
    } else {
      setCustom(presetValue);
    }
    onChange(presetValue);
  };

  const toggleDay = (day: number) => {
    setSelectedDays((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day]
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        {(['hourly', 'daily', 'weekly', 'custom'] as Frequency[]).map((f) => (
          <button
            key={f}
            onClick={() => setFrequency(f)}
            style={{
              padding: '0.25rem 0.5rem',
              fontSize: '0.875rem',
              borderRadius: '4px',
              border: frequency === f ? '2px solid #2563eb' : '1px solid #ccc',
              background: frequency === f ? '#eff6ff' : '#fff',
              cursor: 'pointer',
            }}
            aria-pressed={frequency === f}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      {frequency === 'daily' && (
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <label style={{ fontSize: '0.875rem' }}>
            Hour (0–23){' '}
            <input
              type="number"
              min={0}
              max={23}
              value={dailyHour}
              onChange={(e) => setDailyHour(e.target.value)}
              style={{ width: 60, padding: '0.25rem 0.5rem' }}
            />
          </label>
          <label style={{ fontSize: '0.875rem' }}>
            Minute (0–59){' '}
            <input
              type="number"
              min={0}
              max={59}
              value={dailyMinute}
              onChange={(e) => setDailyMinute(e.target.value)}
              style={{ width: 60, padding: '0.25rem 0.5rem' }}
            />
          </label>
        </div>
      )}

      {frequency === 'weekly' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <label style={{ fontSize: '0.875rem' }}>
              Hour (0–23){' '}
              <input
                type="number"
                min={0}
                max={23}
                value={dailyHour}
                onChange={(e) => setDailyHour(e.target.value)}
                style={{ width: 60, padding: '0.25rem 0.5rem' }}
              />
            </label>
            <label style={{ fontSize: '0.875rem' }}>
              Minute (0–59){' '}
              <input
                type="number"
                min={0}
                max={59}
                value={dailyMinute}
                onChange={(e) => setDailyMinute(e.target.value)}
                style={{ width: 60, padding: '0.25rem 0.5rem' }}
              />
            </label>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {WEEKDAYS.map((d) => (
              <label
                key={d.value}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.25rem',
                  fontSize: '0.875rem',
                  cursor: 'pointer',
                  padding: '0.25rem 0.5rem',
                  borderRadius: '4px',
                  background: selectedDays.includes(d.value) ? '#eff6ff' : '#f9fafb',
                  border: selectedDays.includes(d.value) ? '1px solid #2563eb' : '1px solid #e5e7eb',
                }}
              >
                <input
                  type="checkbox"
                  checked={selectedDays.includes(d.value)}
                  onChange={() => toggleDay(d.value)}
                  style={{ cursor: 'pointer' }}
                />
                {d.label}
              </label>
            ))}
          </div>
        </div>
      )}

      {frequency === 'custom' && (
        <textarea
          rows={2}
          value={custom}
          onChange={(e) => {
            setCustom(e.target.value);
            onChange(e.target.value);
          }}
          placeholder="* * * * *"
          style={{
            width: '100%',
            padding: '0.5rem',
            border: error ? '2px solid #dc2626' : '1px solid #ccc',
            fontFamily: 'monospace',
            fontSize: '0.875rem',
          }}
          aria-label="Custom cron expression"
          aria-invalid={error ? 'true' : 'false'}
        />
      )}

      <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
        {PRESETS.map((p) => (
          <button
            key={p.value}
            onClick={() => handlePreset(p.value)}
            style={{ padding: '0.125rem 0.375rem', fontSize: '0.75rem' }}
            title={p.value}
          >
            {p.label}
          </button>
        ))}
      </div>

      {error && <span style={{ color: '#dc2626', fontSize: '0.75rem' }}>{error}</span>}
      {!error && value && (
        <span style={{ color: '#666', fontSize: '0.75rem' }}>{formatCron(value)}</span>
      )}
    </div>
  );
}
