import { useState } from 'react';
import TriggerTypeDropdown from '../forms/TriggerTypeDropdown';
import ToolDropdown from '../forms/ToolDropdown';
import CronBuilder from './CronBuilder';

const TRIGGER_DESCRIPTIONS: Record<string, string> = {
  manual: 'Run this workflow manually from the dashboard or API.',
  schedule: 'Run this workflow automatically on a recurring schedule.',
  chat_command: 'Triggers when a user sends a specific command in chat.',
  message: 'Triggers when a message matching a pattern is received.',
  webhook: 'Triggers when an HTTP POST request hits the webhook endpoint.',
  email: 'Triggers when an incoming email matches the configured filters.',
  proposal_approved: 'Triggers when a proposal is approved by a user.',
  proposal_rejected: 'Triggers when a proposal is rejected by a user.',
  tool_error: 'Triggers when a registered tool throws an error.',
  workflow_completed: 'Triggers when another workflow finishes successfully.',
  session_started: 'Triggers when a new user session begins.',
};

const TRIGGER_VARIABLES: Record<string, string[]> = {
  manual: [],
  schedule: ['triggered_at'],
  chat_command: ['command', 'args', 'user_id', 'platform', 'platform_user'],
  message: ['text', 'user_id', 'platform', 'platform_user'],
  webhook: ['body', 'headers', 'query_params'],
  email: ['from_address', 'subject', 'body'],
  proposal_approved: ['proposal_id', 'proposal_type', 'user_id'],
  proposal_rejected: ['proposal_id', 'proposal_type', 'user_id', 'reason'],
  tool_error: ['tool_name', 'error_message', 'args'],
  workflow_completed: ['source_workflow_id', 'outputs'],
  session_started: ['user_id', 'platform', 'platform_user'],
};

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

function AvailableVariables({ triggerType }: { triggerType: string }) {
  const vars = TRIGGER_VARIABLES[triggerType] || [];
  if (vars.length === 0) return null;
  return (
    <div style={{ fontSize: '0.75rem', color: '#666', marginTop: '0.25rem' }}>
      <strong>Available variables:</strong>{' '}
      {vars.map((v) => (
        <code key={v} style={{ background: '#f3f4f6', padding: '0.125rem 0.25rem', borderRadius: 4, marginRight: 4 }}>
          {'{data.' + v + '}'}
        </code>
      ))}
    </div>
  );
}

function HelpModal({ onClose }: { onClose: () => void }) {
  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0,0,0,0.4)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onClose}
      data-testid="help-modal-backdrop"
    >
      <div
        style={{
          background: '#fff',
          padding: '1.5rem',
          borderRadius: 8,
          maxWidth: 400,
          width: '90%',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ marginTop: 0 }}>Workflow Editor Help</h3>
        <ol style={{ paddingLeft: '1.25rem', lineHeight: 1.6 }}>
          <li>Choose a trigger that starts the workflow.</li>
          <li>Add nodes to the canvas and configure them.</li>
          <li>Connect nodes to define execution order.</li>
          <li>Save and activate to make the workflow live.</li>
        </ol>
        <button onClick={onClose} style={{ marginTop: '0.5rem' }}>
          Close
        </button>
      </div>
    </div>
  );
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
  const [showHelp, setShowHelp] = useState(false);

  return (
    <div style={{ padding: '0.75rem 1rem', borderBottom: '1px solid #ddd', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <label style={{ fontSize: '0.875rem', fontWeight: 600 }}>Trigger</label>
          <button
            onClick={() => setShowHelp(true)}
            style={{
              width: 20,
              height: 20,
              borderRadius: '50%',
              border: '1px solid #ccc',
              background: '#fff',
              fontSize: '0.75rem',
              cursor: 'pointer',
              padding: 0,
              lineHeight: '18px',
            }}
            title="Show help"
            aria-label="Show help"
          >
            ?
          </button>
        </div>
        <div style={{ minWidth: 180, flex: 1, maxWidth: 320 }}>
          <TriggerTypeDropdown
            value={triggerType}
            onChange={(type) => onTriggerTypeChange(type)}
          />
          {TRIGGER_DESCRIPTIONS[triggerType] && (
            <span style={{ fontSize: '0.75rem', color: '#666', display: 'block', marginTop: '0.25rem' }}>
              {TRIGGER_DESCRIPTIONS[triggerType]}
            </span>
          )}
        </div>
        <button onClick={onSaveTrigger} disabled={triggerSaving}>
          {triggerSaving ? 'Saving…' : 'Save Trigger'}
        </button>
      </div>

      <AvailableVariables triggerType={triggerType} />

      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
        {triggerType === 'schedule' && (
          <CronBuilder
            value={triggerConfig.cron || ''}
            onChange={(value: string) => onTriggerConfigChange('cron', value)}
          />
        )}
        {triggerType === 'chat_command' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
            <input
              placeholder="e.g. weather, remind, status"
              value={triggerConfig.command || ''}
              onChange={(e) => onTriggerConfigChange('command', e.target.value)}
              style={{ padding: '0.25rem 0.5rem', minWidth: 180 }}
              aria-label="Command"
            />
            <span style={{ fontSize: '0.75rem', color: '#666' }}>
              The word users type to activate this workflow.
            </span>
          </div>
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
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <input
              placeholder="Endpoint"
              value={triggerConfig.endpoint || ''}
              onChange={(e) => onTriggerConfigChange('endpoint', e.target.value)}
              style={{ padding: '0.25rem 0.5rem', minWidth: 180 }}
              aria-label="Endpoint"
            />
            <span style={{ fontSize: '0.75rem', color: '#666' }}>
              Send POST requests to this endpoint.
            </span>
            {workflowId && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.875rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <input
                    value={webhookUrl || `${window.location.origin}/api/webhooks/${workflowId}`}
                    readOnly
                    style={{ minWidth: 280, padding: '0.25rem 0.5rem', background: '#f9fafb' }}
                    aria-label="Webhook URL"
                  />
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
          </div>
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
          <div style={{ minWidth: 180, flex: 1, maxWidth: 320 }}>
            <ToolDropdown
              value={triggerConfig.tool_name || ''}
              onChange={(value: string) => onTriggerConfigChange('tool_name', value)}
              includeAny
            />
          </div>
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
      </div>

      {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}
    </div>
  );
}
