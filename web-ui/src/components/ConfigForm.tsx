import { useState, useCallback, useEffect } from 'react';
import { saveConfig, fetchConfigSchema } from '../api/client';
import { CONFIG_KEY_LABELS, label } from '../lib/labels';
import { formatCron } from '../lib/format';
import { TEXT } from '../lib/text';
import './ConfigForm.css';

interface ConfigFormProps {
  initialConfig: Record<string, unknown>;
  onSave?: () => void;
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

interface TrustPreset {
  name: string;
  description: string;
  bullets: string[];
  values: Record<string, unknown>;
}

const trustPresets: Record<string, TrustPreset> = {
  paranoid: {
    name: 'Paranoid',
    description: 'Maximum safety. Every tool requires explicit confirmation.',
    bullets: [
      'No tools auto-approved',
      'Scheduler and subagent shell access disabled',
      'Self-management tools disabled',
      'No email sending from autonomous agents',
    ],
    values: {
      auto_approve_tools: [],
      scheduler_shell_exec: false,
      subagent_shell_exec: false,
      subagent_write_local: false,
      subagent_email_send: false,
      scheduler_email_send: false,
      self_management: false,
      blocked_shell_patterns: [],
      preset: 'paranoid',
    },
  },
  prompt_on_mobile: {
    name: 'Prompt on Mobile',
    description: 'Safe for phone use. Destructive tools show ✅/❌ buttons on Telegram.',
    bullets: [
      'No tools auto-approved',
      'Scheduler and subagent shell access disabled',
      'Self-management tools disabled',
      'Blocks dangerous patterns like rm -rf /',
    ],
    values: {
      auto_approve_tools: [],
      scheduler_shell_exec: false,
      subagent_shell_exec: false,
      subagent_write_local: false,
      subagent_email_send: false,
      scheduler_email_send: false,
      self_management: false,
      blocked_shell_patterns: ['rm -rf /'],
      preset: 'prompt_on_mobile',
    },
  },
  household: {
    name: 'Household',
    description: 'Balanced for daily use. Common file tools work without prompts.',
    bullets: [
      'Terminal and write_file auto-approved',
      'Subagent local file writes enabled',
      'Self-management tools enabled (proposals, style)',
      'Blocks dangerous shell patterns',
    ],
    values: {
      auto_approve_tools: ['terminal', 'write_file'],
      scheduler_shell_exec: false,
      subagent_shell_exec: false,
      subagent_write_local: true,
      subagent_email_send: false,
      scheduler_email_send: false,
      self_management: true,
      blocked_shell_patterns: ['rm -rf /', 'dd if=/dev/zero'],
      preset: 'household',
    },
  },
  developer: {
    name: 'Developer',
    description: 'Full access. All tools auto-approved, autonomous agents can send email.',
    bullets: [
      'All common tools auto-approved',
      'Scheduler and subagent shell access enabled',
      'Self-management tools enabled',
      'Email sending from autonomous agents enabled',
    ],
    values: {
      auto_approve_tools: ['terminal', 'write_file', 'read_file', 'shell'],
      scheduler_shell_exec: true,
      subagent_shell_exec: true,
      subagent_write_local: true,
      subagent_email_send: true,
      scheduler_email_send: true,
      self_management: true,
      blocked_shell_patterns: [],
      preset: 'developer',
    },
  },
};

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

export default function ConfigForm({ initialConfig, onSave }: ConfigFormProps) {
  const [config, setConfig] = useState<Record<string, unknown>>(() => stripSecrets(initialConfig) as Record<string, unknown>);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [schema, setSchema] = useState<Record<string, SchemaEntry>>({});

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

  const updateValue = useCallback((path: string, value: unknown) => {
    setConfig((prev) => {
      const next = { ...prev };
      const keys = path.split('.');
      let target: Record<string, unknown> = next;
      for (let i = 0; i < keys.length - 1; i++) {
        target[keys[i]] = { ...(target[keys[i]] as Record<string, unknown>) };
        target = target[keys[i]] as Record<string, unknown>;
      }
      target[keys[keys.length - 1]] = value;
      return next;
    });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaveMsg(null);
    try {
      const res = await saveConfig(config);
      const data = await res.json();
      if (res.ok) {
        setSaveMsg(TEXT.config.saveSuccess);
        onSave?.();
      } else {
        setSaveMsg(data.detail || TEXT.config.saveFailed);
      }
    } catch (err) {
      setSaveMsg((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const currentPreset =
    typeof config.trust === 'object' && config.trust !== null
      ? String((config.trust as Record<string, unknown>).preset || '')
      : '';

  const applyTrustPreset = (presetKey: string) => {
    const preset = trustPresets[presetKey];
    if (!preset) return;
    setConfig((prev) => ({
      ...prev,
      trust: { ...(prev.trust as Record<string, unknown> || {}), ...preset.values },
    }));
  };

  const resetSection = (sectionKey: string) => {
    setConfig((prev) => ({
      ...prev,
      [sectionKey]: stripSecrets((initialConfig[sectionKey] as Record<string, unknown>) || {}),
    }));
  };

  const renderField = (path: string, key: string, value: unknown, depth: number) => {
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
            onChange={(e) => updateValue(fullPath, e.target.value)}
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
        <label className="row-center gap-2" className="cursor-pointer">
          <input
            type="checkbox"
            checked={value as boolean}
            onChange={(e) => updateValue(fullPath, e.target.checked)}
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
            onChange={(e) => updateValue(fullPath, e.target.value.split(',').map((s) => s.trim()).filter(Boolean))}
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
            onChange={(e) => updateValue(fullPath, inputType === 'number' ? Number(e.target.value) : e.target.value)}
            className={baseClass}
            style={invalid ? { border: '2px solid var(--color-danger)' } : undefined}
          />
          {isCred && (
            <button
              type="button"
              onClick={() => setRevealed((s) => ({ ...s, [fullPath]: !s[fullPath] }))}
              className="text-small"
            >
              {revealed[fullPath] ? TEXT.config.hide : TEXT.config.reveal}
            </button>
          )}
        </label>
      );
    }

    const cronPreview = looksLikeCron(value) ? formatCron(value as string) : null;

    return (
      <div className="config-form__field-row">
        {input}
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
  };

  const topSections = Object.entries(config).filter(([, v]) => typeof v === 'object' && v !== null && !Array.isArray(v));
  const topFields = Object.entries(config).filter(([, v]) => typeof v !== 'object' || v === null || Array.isArray(v));

  return (
    <div>
      {typeof config.trust === 'object' && config.trust !== null && (
        <div className="mb-4">
          <strong>{TEXT.config.trustPresetTitle}</strong>
          <div className="config-form__trust-grid">
            {Object.entries(trustPresets).map(([key, preset]) => (
              <div
                key={key}
                onClick={() => applyTrustPreset(key)}
                className={currentPreset === key ? 'config-form__trust-card config-form__trust-card--selected' : 'config-form__trust-card'}
              >
                <h3>{preset.name}</h3>
                <p>{preset.description}</p>
                <ul>
                  {preset.bullets.map((b, i) => (
                    <li key={i}>{b}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}

      {topSections.map(([sectionKey, sectionValue]) => (
        <div
          key={sectionKey}
          className="config-form__section"
        >
          <div
            className="config-form__section-header"
            onClick={() => setCollapsed((s) => ({ ...s, [sectionKey]: !s[sectionKey] }))}
          >
            <strong>{sectionKey}</strong>
            <div className="row-sm">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  resetSection(sectionKey);
                }}
              >
                {TEXT.config.resetToInitial}
              </button>
              <span>{collapsed[sectionKey] ? '▶' : '▼'}</span>
            </div>
          </div>
          {!collapsed[sectionKey] && (
            <div className="config-form__section-body">
              {Object.entries(sectionValue as Record<string, unknown>).map(([k, v]) => (
                <div key={k} className="config-form__field">
                  {renderField(sectionKey, k, v, 1)}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}

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

      <div className="row-sm" className="row-center">
        <button onClick={handleSave} disabled={saving}>
          {saving ? TEXT.common.saving : TEXT.common.save}
        </button>
        {saveMsg && <span>{saveMsg}</span>}
      </div>
    </div>
  );
}
