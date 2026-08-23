import { useEffect, useState } from 'react';
import { CronExpressionParser } from 'cron-parser';
import { formatCron } from '../../lib/format';
import './CronBuilder.css';

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
    // BUG-057: switching to Custom used to emit an empty expression,
    // silently wiping the schedule (and empty validated clean, so nothing
    // warned). Seed Custom from the current cron instead of clearing it.
    if (frequency === 'custom' && !custom.trim()) {
      if (value.trim()) {
        setCustom(value);
        validate(value);
      }
      return;
    }
    const cron = buildCron(frequency, dailyHour, dailyMinute, selectedDays, custom);
    if (cron !== value) {
      onChange(cron);
    }
    validate(cron);
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    <div className="cron-builder">
      <div className="cron-builder__freq-row">
        {(['hourly', 'daily', 'weekly', 'custom'] as Frequency[]).map((f) => (
          <button
            key={f}
            onClick={() => setFrequency(f)}
            className={frequency === f ? 'cron-builder__freq-btn cron-builder__freq-btn--active' : 'cron-builder__freq-btn'}
            aria-pressed={frequency === f}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      {frequency === 'daily' && (
        <div className="cron-builder__time-row">
          <label className="text-small">
            Hour (0–23){' '}
            <input
              type="number"
              min={0}
              max={23}
              value={dailyHour}
              onChange={(e) => setDailyHour(e.target.value)}
              className="form-input cron-builder__time-input"
            />
          </label>
          <label className="text-small">
            Minute (0–59){' '}
            <input
              type="number"
              min={0}
              max={59}
              value={dailyMinute}
              onChange={(e) => setDailyMinute(e.target.value)}
              className="form-input cron-builder__time-input"
            />
          </label>
        </div>
      )}

      {frequency === 'weekly' && (
        <div className="stack-md">
          <div className="cron-builder__time-row">
            <label className="text-small">
              Hour (0–23){' '}
              <input
                type="number"
                min={0}
                max={23}
                value={dailyHour}
                onChange={(e) => setDailyHour(e.target.value)}
                className="form-input cron-builder__time-input"
              />
            </label>
            <label className="text-small">
              Minute (0–59){' '}
              <input
                type="number"
                min={0}
                max={59}
                value={dailyMinute}
                onChange={(e) => setDailyMinute(e.target.value)}
                className="form-input cron-builder__time-input"
              />
            </label>
          </div>
          <div className="row-sm">
            {WEEKDAYS.map((d) => (
              <label
                key={d.value}
                className={selectedDays.includes(d.value) ? 'cron-builder__day-label cron-builder__day-label--active' : 'cron-builder__day-label'}
              >
                <input
                  type="checkbox"
                  checked={selectedDays.includes(d.value)}
                  onChange={() => toggleDay(d.value)} className="cursor-pointer"
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
          className={error ? 'cron-builder__custom cron-builder__custom--error' : 'cron-builder__custom'}
          aria-label="Custom cron expression"
          aria-invalid={error ? 'true' : 'false'}
        />
      )}

      <div className="cron-builder__preset-row">
        {PRESETS.map((p) => (
          <button
            key={p.value}
            onClick={() => handlePreset(p.value)}
            className="cron-builder__preset-btn"
            title={p.value}
          >
            {p.label}
          </button>
        ))}
      </div>

      {error && <span className="cron-builder__error">{error}</span>}
      {!error && value && (
        <span className="cron-builder__preview">{formatCron(value)}</span>
      )}
    </div>
  );
}
