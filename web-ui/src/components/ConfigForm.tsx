import { useState, useCallback } from 'react';
import { saveConfig } from '../api/client';

interface ConfigFormProps {
  initialConfig: Record<string, unknown>;
  onSave?: () => void;
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

function getInputType(_key: string, value: unknown): 'text' | 'number' | 'boolean' | 'array' {
  if (typeof value === 'boolean') return 'boolean';
  if (typeof value === 'number') return 'number';
  if (Array.isArray(value)) return 'array';
  return 'text';
}

const trustPresets: Record<string, Record<string, unknown>> = {
  paranoid: {
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
  prompt_on_mobile: {
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
  household: {
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
  developer: {
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
};

function stripSecrets(obj: unknown): unknown {
  if (obj === null || obj === undefined) return obj;
  if (Array.isArray(obj)) return obj.map(stripSecrets);
  if (typeof obj === 'object') {
    const result: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      result[k] = stripSecrets(v);
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
        setSaveMsg('Saved successfully');
        onSave?.();
      } else {
        setSaveMsg(data.detail || 'Save failed');
      }
    } catch (err) {
      setSaveMsg((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const applyTrustPreset = (preset: string) => {
    const values = trustPresets[preset];
    if (!values) return;
    setConfig((prev) => ({
      ...prev,
      trust: { ...(prev.trust as Record<string, unknown> || {}), ...values },
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
      return <span style={{ color: '#999' }}>null</span>;
    }

    if (typeof value === 'object' && !Array.isArray(value)) {
      const sectionPath = path ? `${path}.${key}` : key;
      const isCollapsed = collapsed[sectionPath] ?? (depth > 0);
      return (
        <div style={{ marginLeft: depth > 0 ? '1rem' : 0, marginTop: '0.5rem' }}>
          <button
            onClick={() => setCollapsed((s) => ({ ...s, [sectionPath]: !isCollapsed }))}
            style={{ background: 'none', border: 'none', cursor: 'pointer', fontWeight: 'bold', padding: 0 }}
          >
            {isCollapsed ? '▶' : '▼'} {key}
          </button>
          {!isCollapsed && (
            <div style={{ marginTop: '0.25rem' }}>
              {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
                <div key={k} style={{ marginBottom: '0.25rem' }}>
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

    const baseStyle: React.CSSProperties = {
      border: `1px solid ${invalid ? '#f44336' : '#ccc'}`,
      borderRadius: '4px',
      padding: '0.35rem 0.5rem',
      minWidth: '200px',
    };

    let input: React.ReactNode;
    if (inputType === 'boolean') {
      input = (
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={value as boolean}
            onChange={(e) => updateValue(fullPath, e.target.checked)}
          />
          <span>{key}</span>
        </label>
      );
    } else if (inputType === 'array') {
      input = (
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          <span>{key}</span>
          <input
            type="text"
            value={(value as unknown[]).join(', ')}
            onChange={(e) => updateValue(fullPath, e.target.value.split(',').map((s) => s.trim()).filter(Boolean))}
            style={baseStyle}
          />
        </label>
      );
    } else {
      input = (
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          <span>{key}</span>
          <input
            type={isCred && !revealed[fullPath] ? 'password' : inputType === 'number' ? 'number' : 'text'}
            value={value as string | number}
            onChange={(e) => updateValue(fullPath, inputType === 'number' ? Number(e.target.value) : e.target.value)}
            style={baseStyle}
          />
          {isCred && (
            <button
              type="button"
              onClick={() => setRevealed((s) => ({ ...s, [fullPath]: !s[fullPath] }))}
              style={{ fontSize: '0.8rem' }}
            >
              {revealed[fullPath] ? 'Hide' : 'Reveal'}
            </button>
          )}
        </label>
      );
    }

    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
        {input}
        {invalid && <span style={{ color: '#f44336', fontSize: '0.85rem' }}>Invalid</span>}
        {needsRestart && (
          <span
            style={{
              fontSize: '0.75rem',
              background: '#fff3e0',
              color: '#e65100',
              padding: '0.1rem 0.35rem',
              borderRadius: '4px',
            }}
          >
            Requires restart
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
        <div style={{ marginBottom: '1rem', padding: '0.75rem', background: '#f5f5f5', borderRadius: '6px' }}>
          <strong>Trust Preset</strong>
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
            {Object.keys(trustPresets).map((preset) => (
              <button key={preset} onClick={() => applyTrustPreset(preset)}>
                {preset}
              </button>
            ))}
          </div>
        </div>
      )}

      {topSections.map(([sectionKey, sectionValue]) => (
        <div
          key={sectionKey}
          style={{
            border: '1px solid #ddd',
            borderRadius: '8px',
            marginBottom: '1rem',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '0.75rem 1rem',
              background: '#fafafa',
              cursor: 'pointer',
            }}
            onClick={() => setCollapsed((s) => ({ ...s, [sectionKey]: !s[sectionKey] }))}
          >
            <strong style={{ textTransform: 'capitalize' }}>{sectionKey}</strong>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  resetSection(sectionKey);
                }}
              >
                Reset to defaults
              </button>
              <span>{collapsed[sectionKey] ? '▶' : '▼'}</span>
            </div>
          </div>
          {!collapsed[sectionKey] && (
            <div style={{ padding: '1rem' }}>
              {Object.entries(sectionValue as Record<string, unknown>).map(([k, v]) => (
                <div key={k} style={{ marginBottom: '0.5rem' }}>
                  {renderField(sectionKey, k, v, 1)}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}

      {topFields.length > 0 && (
        <div style={{ border: '1px solid #ddd', borderRadius: '8px', marginBottom: '1rem', overflow: 'hidden' }}>
          <div style={{ padding: '0.75rem 1rem', background: '#fafafa' }}>
            <strong>General</strong>
          </div>
          <div style={{ padding: '1rem' }}>
            {topFields.map(([k, v]) => (
              <div key={k} style={{ marginBottom: '0.5rem' }}>
                {renderField('', k, v, 0)}
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
        <button onClick={handleSave} disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </button>
        {saveMsg && <span>{saveMsg}</span>}
      </div>
    </div>
  );
}
