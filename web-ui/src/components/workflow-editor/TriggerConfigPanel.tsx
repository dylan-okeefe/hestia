import { useState } from 'react';
import TriggerTypeDropdown from '../forms/TriggerTypeDropdown';
import ToolDropdown from '../forms/ToolDropdown';
import CronBuilder from './CronBuilder';
import './TriggerConfigPanel.css';

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
    <div className="trigger-config-panel__variables">
      <strong>Available variables:</strong>{' '}
      {vars.map((v) => (
        <code key={v} className="inline-code">
          {'{{data.' + v + '}}'}
        </code>
      ))}
    </div>
  );
}

function HelpModal({ onClose }: { onClose: () => void }) {
  return (
    <div
      className="modal-overlay"
      onClick={onClose}
      data-testid="help-modal-backdrop"
    >
      <div
        className="help-modal__content"
        onClick={(e) => e.stopPropagation()}
      >
        <h3>Workflow Editor Help</h3>
        <ol>
          <li>Choose a trigger that starts the workflow.</li>
          <li>Add nodes to the canvas and configure them.</li>
          <li>Connect nodes to define execution order.</li>
          <li>Save and activate to make the workflow live.</li>
        </ol>
        <button onClick={onClose} className="mt-2">
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
    <div className="trigger-config-panel">
      <div className="trigger-config-panel__row">
        <div className="row-center gap-2">
          <label className="trigger-config-panel__label">Trigger</label>
          <button
            onClick={() => setShowHelp(true)}
            className="trigger-config-panel__help-btn"
            title="Show help"
            aria-label="Show help"
          >
            ?
          </button>
        </div>
        <div className="trigger-config-panel__dropdown-wrap">
          <TriggerTypeDropdown
            value={triggerType}
            onChange={(type) => onTriggerTypeChange(type)}
          />
          {TRIGGER_DESCRIPTIONS[triggerType] && (
            <span className="trigger-config-panel__description">
              {TRIGGER_DESCRIPTIONS[triggerType]}
            </span>
          )}
        </div>
        <button onClick={onSaveTrigger} disabled={triggerSaving}>
          {triggerSaving ? 'Saving…' : 'Save Trigger'}
        </button>
      </div>

      <AvailableVariables triggerType={triggerType} />

      <div className="trigger-config-panel__row">
        {triggerType === 'schedule' && (
          <CronBuilder
            value={triggerConfig.cron || ''}
            onChange={(value: string) => onTriggerConfigChange('cron', value)}
          />
        )}
        {triggerType === 'chat_command' && (
          <div className="stack-sm">
            <input
              placeholder="e.g. weather, remind, status"
              value={triggerConfig.command || ''}
              onChange={(e) => onTriggerConfigChange('command', e.target.value)}
              className="form-input trigger-config-panel__input"
              aria-label="Command"
            />
            <span className="trigger-config-panel__description">
              The word users type to activate this workflow.
            </span>
          </div>
        )}
        {triggerType === 'message' && (
          <input
            placeholder="Pattern"
            value={triggerConfig.pattern || ''}
            onChange={(e) => onTriggerConfigChange('pattern', e.target.value)}
            className="form-input trigger-config-panel__input"
            aria-label="Pattern"
          />
        )}
        {triggerType === 'webhook' && (
          <div className="stack-md">
            <input
              placeholder="Endpoint"
              value={triggerConfig.endpoint || ''}
              onChange={(e) => onTriggerConfigChange('endpoint', e.target.value)}
              className="form-input trigger-config-panel__input"
              aria-label="Endpoint"
            />
            <span className="trigger-config-panel__description">
              Send POST requests to this endpoint.
            </span>
            {workflowId && (
              <div className="stack-md text-small">
                <div className="trigger-config-panel__webhook-row">
                  <input
                    value={webhookUrl || `${window.location.origin}/api/webhooks/${workflowId}`}
                    readOnly
                    className="form-input trigger-config-panel__webhook-url"
                    aria-label="Webhook URL"
                  />
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(webhookUrl || `${window.location.origin}/api/webhooks/${workflowId}`);
                    }}
                    className="trigger-config-panel__copy-btn"
                  >
                    Copy URL
                  </button>
                </div>
                <div className="trigger-config-panel__webhook-row">
                  <span>Secret: {webhookSecret}</span>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(webhookSecret);
                    }}
                    className="trigger-config-panel__copy-btn"
                  >
                    Copy Secret
                  </button>
                </div>
                <span className="trigger-config-panel__webhook-hint">
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
              className="form-input trigger-config-panel__input"
              aria-label="From address contains"
            />
            <input
              placeholder="Subject (contains)"
              value={triggerConfig.subject_contains || ''}
              onChange={(e) => onTriggerConfigChange('subject_contains', e.target.value)}
              className="form-input trigger-config-panel__input"
              aria-label="Subject contains"
            />
          </>
        )}
        {triggerType === 'proposal_approved' && (
          <input
            placeholder="Proposal type (optional)"
            value={triggerConfig.proposal_type || ''}
            onChange={(e) => onTriggerConfigChange('proposal_type', e.target.value)}
            className="form-input trigger-config-panel__input"
            aria-label="Proposal type"
          />
        )}
        {triggerType === 'proposal_rejected' && (
          <input
            placeholder="Proposal type (optional)"
            value={triggerConfig.proposal_type || ''}
            onChange={(e) => onTriggerConfigChange('proposal_type', e.target.value)}
            className="form-input trigger-config-panel__input"
            aria-label="Proposal type"
          />
        )}
        {triggerType === 'tool_error' && (
          <div className="trigger-config-panel__dropdown-wrap">
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
            className="form-input trigger-config-panel__input"
            aria-label="Source workflow ID"
          />
        )}
      </div>

      {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}
    </div>
  );
}
