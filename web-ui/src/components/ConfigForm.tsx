import { useState, useCallback, useEffect } from 'react';
import { fetchConfigSchema } from '../api/client';
import { CONFIG_KEY_LABELS, CONFIG_KEY_DESCRIPTIONS, label } from '../lib/labels';
import { formatCron } from '../lib/format';
import { TEXT } from '../lib/text';
import './ConfigForm.css';

interface ConfigFormProps {
  initialConfig: Record<string, unknown>;
}

interface SchemaEntry {
  type: string;
  values?: string[];
  default?: string;
}

const credentialKeys = new Set(['bot_token', 'access_token', 'password', 'password_env', 'api_key']);
const restartPaths = new Set([
  'core.inference.base_url',
  'core.inference.model_name',
  'core.inference.context_length',
  'core.storage.database_url',
  'features.web.host',
  'features.web.port',
  'features.web.enabled',
  'platforms.telegram.bot_token',
  'platforms.matrix.access_token',
]);

function isInvalid(path: string, value: unknown): boolean {
  if (path.endsWith('.max_iterations') && (typeof value !== 'number' || value < 1)) return true;
  if (path.endsWith('.context_length') && (typeof value !== 'number' || value < 1)) return true;
  if (path.endsWith('.port') && (typeof value !== 'number' || value < 1 || value > 65535)) return true;
  if (path.endsWith('.max_tokens') && (typeof value !== 'number' || value < 0)) return true;
  return false;
}

function looksLikeCron(value: unknown): boolean {
  if (typeof value !== 'string') return false;
  const cronPattern = /^(\S+\s+\S+\s+\S+\s+\S+\s+\S+)$/;
  if (!cronPattern.test(value)) return false;
  return /^[\d\*\-\,\/\?LW#\s]+$/.test(value);
}

function getInputType(_key: string, value: unknown): 'text' | 'number' | 'boolean' | 'array' {
  if (typeof value === 'boolean') return 'boolean';
  if (typeof value === 'number') return 'number';
  if (Array.isArray(value)) return 'array';
  return 'text';
}

function stripSecrets(obj: unknown): unknown {
  if (obj === null || obj === undefined) return obj;
  if (Array.isArray(obj)) return obj.map(stripSecrets);
  if (typeof obj === 'object') {
    const result: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      if (credentialKeys.has(k) && v) {
        result[k] = '***';
      } else {
        result[k] = stripSecrets(v);
      }
    }
    return result;
  }
  return obj;
}

export default function ConfigForm({ initialConfig }: ConfigFormProps) {
  const [config] = useState<Record<string, unknown>>(() => stripSecrets(initialConfig) as Record<string, unknown>);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});
  const [schema, setSchema] = useState<Record<string, SchemaEntry>>({});
  const [search, setSearch] = useState('');

  useEffect(() => {
    let cancelled = false;
    fetchConfigSchema()
      .then((data: { schema?: Record<string, SchemaEntry> }) => {
        if (!cancelled && data?.schema) {
          setSchema(data.schema);
        }
      })
      .catch(() => {
        // Schema fetch is best-effort; fall back to text inputs.
      });
    return () => { cancelled = true; };
  }, []);

  const renderField = useCallback((path: string, key: string, value: unknown, depth: number) => {
    if (value === null || value === undefined) {
      return <span className="config-form__null">null</span>;
    }

    if (typeof value === 'object' && !Array.isArray(value)) {
      const sectionPath = path ? `${path}.${key}` : key;
      const isCollapsed = collapsed[sectionPath] ?? (depth > 0);
      return (
        <div className={depth > 0 ? 'ml-4 mt-2' : 'mt-2'}>
          <button
            onClick={() => setCollapsed((s) => ({ ...s, [sectionPath]: !isCollapsed }))}
            className="config-form__toggle-btn"
          >
            {isCollapsed ? '▶' : '▼'} {label(CONFIG_KEY_LABELS, key)}
          </button>
          {!isCollapsed && (
            <div className="mt-1">
              {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
                <div key={k} className="mb-1">
                  {renderField(sectionPath, k, v, depth + 1)}
                </div>
              ))}
            </div>
          )}
        </div>
      );
    }

    const fullPath = path ? `${path}.${key}` : key;
    const inputType = getInputType(key, value);
    const isCred = credentialKeys.has(key);
    const invalid = isInvalid(fullPath, value);
    const needsRestart = restartPaths.has(fullPath);

    const baseClass = 'form-input';

    let input: React.ReactNode;
    if (schema[fullPath]?.type === 'enum') {
      input = (
        <label className="row-center gap-2">
          <span>{label(CONFIG_KEY_LABELS, key)}</span>
          <select
            value={String(value)}
            disabled
            className="form-select"
          >
            {schema[fullPath].values?.map((v: string) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
        </label>
      );
    } else if (inputType === 'boolean') {
      input = (
        <label className="row-center gap-2">
          <input
            type="checkbox"
            checked={value as boolean}
            disabled
          />
          <span>{label(CONFIG_KEY_LABELS, key)}</span>
        </label>
      );
    } else if (inputType === 'array') {
      input = (
        <label className="row-center gap-2">
          <span>{label(CONFIG_KEY_LABELS, key)}</span>
          <input
            type="text"
            value={(value as unknown[]).join(', ')}
            disabled
            className={baseClass}
          />
        </label>
      );
    } else {
      input = (
        <label className="row-center gap-2">
          <span>{label(CONFIG_KEY_LABELS, key)}</span>
          <input
            type={isCred && !revealed[fullPath] ? 'password' : inputType === 'number' ? 'number' : 'text'}
            value={value as string | number}
            disabled
            className={baseClass}
            style={invalid ? { border: '2px solid var(--color-danger)' } : undefined}
          />
          {isCred && (
            <button
              type="button"
              onClick={() => setRevealed((s) => ({ ...s, [fullPath]: !s[fullPath] }))}
              className="text-small config-form__btn"
            >
              {revealed[fullPath] ? TEXT.config.hide : TEXT.config.reveal}
            </button>
          )}
        </label>
      );
    }

    const cronPreview = looksLikeCron(value) ? formatCron(value as string) : null;
    const description = CONFIG_KEY_DESCRIPTIONS[key];

    return (
      <div className="config-form__field-row">
        <div className="config-form__field-stack">
          {input}
          {description && (
            <span className="config-form__description">{description}</span>
          )}
        </div>
        {invalid && <span className="text-danger text-small">{TEXT.config.invalid}</span>}
        {needsRestart && (
          <span className="config-form__restart-badge">
            {TEXT.config.requiresRestart}
          </span>
        )}
        {cronPreview && (
          <span className="config-form__cron-preview">
            {cronPreview}
          </span>
        )}
      </div>
    );
  }, [collapsed, revealed, schema]);

  const matchesSearch = (sectionKey: string, fieldKey: string): boolean => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    const sectionLabel = label(CONFIG_KEY_LABELS, sectionKey).toLowerCase();
    const fieldLabel = label(CONFIG_KEY_LABELS, fieldKey).toLowerCase();
    const fieldDesc = (CONFIG_KEY_DESCRIPTIONS[fieldKey] || '').toLowerCase();
    return sectionLabel.includes(q) || fieldLabel.includes(q) || fieldDesc.includes(q);
  };

  const filterSection = (sectionKey: string, sectionValue: Record<string, unknown>): [string, unknown][] => {
    return Object.entries(sectionValue).filter(([k]) => matchesSearch(sectionKey, k));
  };

  const topSections = Object.entries(config)
    .filter(([, v]) => typeof v === 'object' && v !== null && !Array.isArray(v))
    .map(([k, v]) => [k, v] as [string, Record<string, unknown>]);

  const visibleSections = topSections.filter(([k, v]) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    const sectionLabel = label(CONFIG_KEY_LABELS, k).toLowerCase();
    if (sectionLabel.includes(q)) return true;
    return Object.keys(v).some((fk) => matchesSearch(k, fk));
  });

  const topFields = Object.entries(config).filter(([k, v]) => {
    if (typeof v === 'object' && v !== null && !Array.isArray(v)) return false;
    return matchesSearch('', k);
  });

  return (
    <div>
      <div className="config-form__notice">
        {TEXT.config.readOnlyNotice}
      </div>
      <div className="config-form__search">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search config keys…"
          className="form-input"
        />
      </div>

      {visibleSections.map(([sectionKey, sectionValue]) => {
        const filteredFields = filterSection(sectionKey, sectionValue);
        if (filteredFields.length === 0) return null;
        return (
          <div
            key={sectionKey}
            className="config-form__section"
          >
            <div
              className="config-form__section-header"
              onClick={() => setCollapsed((s) => ({ ...s, [sectionKey]: !s[sectionKey] }))}
            >
              <strong>{label(CONFIG_KEY_LABELS, sectionKey)}</strong>
              <span>{collapsed[sectionKey] ? '▶' : '▼'}</span>
            </div>
            {!collapsed[sectionKey] && (
              <div className="config-form__section-body">
                {filteredFields.map(([k, v]) => (
                  <div key={k} className="config-form__field">
                    {renderField(sectionKey, k, v, 1)}
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}

      {topFields.length > 0 && (
        <div className="config-form__section">
          <div className="config-form__section-header">
            <strong>{TEXT.config.generalSection}</strong>
          </div>
          <div className="config-form__section-body">
            {topFields.map(([k, v]) => (
              <div key={k} className="config-form__field">
                {renderField('', k, v, 0)}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
