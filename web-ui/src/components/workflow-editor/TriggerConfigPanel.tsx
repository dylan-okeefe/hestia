import { useEffect, useState } from 'react';
import { CronExpressionParser } from 'cron-parser';
import cronstrue from 'cronstrue';

function CronInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string>('');

  const validate = (v: string) => {
    if (!v.trim()) {
      setError(null);
      setPreview('');
      return;
    }
    try {
      CronExpressionParser.parse(v);
      setError(null);
      setPreview(cronstrue.toString(v));
    } catch {
      setError('Invalid cron expression');
      setPreview('');
    }
  };

  useEffect(() => {
    validate(value);
  }, [value]);

  const presets = [
    { label: 'Every hour', value: '0 * * * *' },
    { label: 'Every day at 8am', value: '0 8 * * *' },
    { label: 'Every Monday', value: '0 0 * * 1' },
    { label: 'Every 5 minutes', value: '*/5 * * * *' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <input
          placeholder="Cron expression"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={(e) => validate(e.target.value)}
          style={{
            padding: '0.25rem 0.5rem',
            minWidth: 180,
            border: error ? '2px solid red' : '1px solid #ccc',
          }}
          aria-label="Cron expression"
          aria-invalid={error ? 'true' : 'false'}
        />
        <div style={{ display: 'flex', gap: '0.25rem' }}>
          {presets.map((p) => (
            <button
              key={p.value}
              onClick={() => onChange(p.value)}
              style={{ padding: '0.125rem 0.375rem', fontSize: '0.75rem' }}
              title={p.value}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>
      {error && <span style={{ color: 'red', fontSize: '0.75rem' }}>{error}</span>}
      {preview && !error && <span style={{ color: '#666', fontSize: '0.75rem' }}>{preview}</span>}
    </div>
  );
}

const TRIGGER_TYPES = [
  'manual',
  'schedule',
  'chat_command',
  'message',
  'webhook',
  'email',
  'proposal_approved',
  'proposal_rejected',
  'tool_error',
  'workflow_completed',
  'session_started',
];

interface TriggerConfigPanelProps {
  triggerType: string;
  onTriggerTypeChange: (type: string) => void;
  triggerConfig: Record<string, string>;
  onTriggerConfigChange: (key: string, value: string) => void;
  onSaveTrigger: () => void;
  triggerSaving: boolean;
  workflowId: string | undefined;
  webhookUrl: string;
  webhookSecret: string;
}

export default function TriggerConfigPanel({
  triggerType,
  onTriggerTypeChange,
  triggerConfig,
  onTriggerConfigChange,
  onSaveTrigger,
  triggerSaving,
  workflowId,
  webhookUrl,
  webhookSecret,
}: TriggerConfigPanelProps) {
  return (
    <div style={{ padding: '0.5rem 1rem', borderBottom: '1px solid #ddd', display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
      <label style={{ fontSize: '0.875rem', fontWeight: 600 }}>Trigger</label>
      <select
        value={triggerType}
        onChange={(e) => onTriggerTypeChange(e.target.value)}
        style={{ padding: '0.25rem 0.5rem' }}
        aria-label="Trigger type"
      >
        {TRIGGER_TYPES.map((t: string) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>
      {triggerType === 'schedule' && (
        <CronInput
          value={triggerConfig.cron || ''}
          onChange={(value: string) => onTriggerConfigChange('cron', value)}
        />
      )}
      {triggerType === 'chat_command' && (
        <input
          placeholder="Command"
          value={triggerConfig.command || ''}
          onChange={(e) => onTriggerConfigChange('command', e.target.value)}
          style={{ padding: '0.25rem 0.5rem', minWidth: 120 }}
          aria-label="Command"
        />
      )}
      {triggerType === 'message' && (
        <input
          placeholder="Pattern"
          value={triggerConfig.pattern || ''}
          onChange={(e) => onTriggerConfigChange('pattern', e.target.value)}
          style={{ padding: '0.25rem 0.5rem', minWidth: 180 }}
          aria-label="Pattern"
        />
      )}
      {triggerType === 'webhook' && (
        <input
          placeholder="Endpoint"
          value={triggerConfig.endpoint || ''}
          onChange={(e) => onTriggerConfigChange('endpoint', e.target.value)}
          style={{ padding: '0.25rem 0.5rem', minWidth: 180 }}
          aria-label="Endpoint"
        />
      )}
      {triggerType === 'email' && (
        <>
          <input
            placeholder="From address (contains)"
            value={triggerConfig.from_address || ''}
            onChange={(e) => onTriggerConfigChange('from_address', e.target.value)}
            style={{ padding: '0.25rem 0.5rem', minWidth: 180 }}
            aria-label="From address contains"
          />
          <input
            placeholder="Subject (contains)"
            value={triggerConfig.subject_contains || ''}
            onChange={(e) => onTriggerConfigChange('subject_contains', e.target.value)}
            style={{ padding: '0.25rem 0.5rem', minWidth: 180 }}
            aria-label="Subject contains"
          />
        </>
      )}
      {triggerType === 'proposal_approved' && (
        <input
          placeholder="Proposal type (optional)"
          value={triggerConfig.proposal_type || ''}
          onChange={(e) => onTriggerConfigChange('proposal_type', e.target.value)}
          style={{ padding: '0.25rem 0.5rem', minWidth: 180 }}
          aria-label="Proposal type"
        />
      )}
      {triggerType === 'proposal_rejected' && (
        <input
          placeholder="Proposal type (optional)"
          value={triggerConfig.proposal_type || ''}
          onChange={(e) => onTriggerConfigChange('proposal_type', e.target.value)}
          style={{ padding: '0.25rem 0.5rem', minWidth: 180 }}
          aria-label="Proposal type"
        />
      )}
      {triggerType === 'tool_error' && (
        <input
          placeholder="Tool name (optional)"
          value={triggerConfig.tool_name || ''}
          onChange={(e) => onTriggerConfigChange('tool_name', e.target.value)}
          style={{ padding: '0.25rem 0.5rem', minWidth: 180 }}
          aria-label="Tool name"
        />
      )}
      {triggerType === 'workflow_completed' && (
        <input
          placeholder="Source workflow ID (optional)"
          value={triggerConfig.source_workflow_id || ''}
          onChange={(e) => onTriggerConfigChange('source_workflow_id', e.target.value)}
          style={{ padding: '0.25rem 0.5rem', minWidth: 180 }}
          aria-label="Source workflow ID"
        />
      )}
      {triggerType === 'webhook' && workflowId && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.875rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span>URL: {webhookUrl || `${window.location.origin}/api/webhooks/${workflowId}`}</span>
            <button
              onClick={() => {
                navigator.clipboard.writeText(webhookUrl || `${window.location.origin}/api/webhooks/${workflowId}`);
              }}
              style={{ padding: '0.125rem 0.5rem', fontSize: '0.75rem' }}
            >
              Copy URL
            </button>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span>Secret: {webhookSecret}</span>
            <button
              onClick={() => {
                navigator.clipboard.writeText(webhookSecret);
              }}
              style={{ padding: '0.125rem 0.5rem', fontSize: '0.75rem' }}
            >
              Copy Secret
            </button>
          </div>
          <span style={{ color: '#666', fontSize: '0.75rem' }}>
            Include the header <code>X-Webhook-Signature: {'<hex_hmac_sha256>'}</code> with every request
          </span>
        </div>
      )}
      <button onClick={onSaveTrigger} disabled={triggerSaving}>
        {triggerSaving ? 'Saving…' : 'Save Trigger'}
      </button>
    </div>
  );
}
