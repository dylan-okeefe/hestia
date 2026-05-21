import { useRef } from 'react';
import type { Node, Edge } from 'reactflow';
import NodeTypeDropdown from '../forms/NodeTypeDropdown';
import PlatformDropdown from '../forms/PlatformDropdown';
import UserDropdown from '../forms/UserDropdown';
import ToolDropdown from '../forms/ToolDropdown';
import type { ToolSchema } from '../../api/client';
import { TEXT } from '../../lib/text';
import SyntaxHelp from './helpers/SyntaxHelp';
import UpstreamVariables from './helpers/UpstreamVariables';
import HighlightPreview from './helpers/HighlightPreview';
import TemplatePreview from './helpers/TemplatePreview';
import JsonTextarea from './helpers/JsonTextarea';
import InsertVariableDropdown from './helpers/InsertVariableDropdown';
import './NodePropertiesPanel.css';

interface NodePropertiesPanelProps {
  selectedNode: Node;
  nodes: Node[];
  edges: Edge[];
  onDeleteNode: (nodeId: string) => void;
  onUpdateNodeData: (key: string, value: unknown) => void;
  onChangeNodeType: (type: string) => void;
  tools: string[];
  toolSchemas: ToolSchema[];
  triggerType: string;
}

export default function NodePropertiesPanel({
  selectedNode,
  nodes,
  edges,
  onDeleteNode,
  onUpdateNodeData,
  onChangeNodeType,
  tools,
  toolSchemas,
  triggerType,
}: NodePropertiesPanelProps) {
  const messageRef = useRef<HTMLTextAreaElement>(null);
  const expressionRef = useRef<HTMLTextAreaElement>(null);
  const promptRef = useRef<HTMLTextAreaElement>(null);

  const insertAtCursor = (ref: React.RefObject<HTMLTextAreaElement | null>, value: string) => {
    const el = ref.current;
    if (!el) return;
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? el.value.length;
    const before = el.value.slice(0, start);
    const after = el.value.slice(end);
    const newValue = before + `{{data.${value}}}` + after;
    if (ref === messageRef) {
      onUpdateNodeData('message', newValue);
    } else if (ref === expressionRef) {
      onUpdateNodeData('expression', newValue);
    } else if (ref === promptRef) {
      onUpdateNodeData('prompt', newValue);
    }
    requestAnimationFrame(() => {
      if (ref.current) {
        const pos = start + `{{data.${value}}}`.length;
        ref.current.focus();
        ref.current.setSelectionRange(pos, pos);
      }
    });
  };

  const toolSchema = toolSchemas.find((t) => t.name === (selectedNode.data.tool_name as string));
  const hasSimpleSchema =
    toolSchema?.parameters &&
    typeof toolSchema.parameters === 'object' &&
    toolSchema.parameters !== null &&
    'properties' in toolSchema.parameters &&
    toolSchema.parameters.properties &&
    typeof toolSchema.parameters.properties === 'object';

  return (
    <div key={selectedNode.id} className="node-properties">
      <div className="node-properties__header">
        <h3>{TEXT.workflowEditor.propertiesTitle}</h3>
        <button
          onClick={() => onDeleteNode(selectedNode.id)}
          className="node-properties__delete-btn"
        >
          {TEXT.workflowEditor.deleteNode}
        </button>
      </div>

      <div className="node-properties__section">
        <label className="node-properties__label">{TEXT.workflowEditor.idLabel}</label>
        <input value={selectedNode.id} readOnly className="node-properties__input" />
      </div>

      <div className="node-properties__section">
        <label className="node-properties__label">{TEXT.workflowEditor.typeLabel}</label>
        <NodeTypeDropdown
          value={selectedNode.type || ''}
          onChange={(type) => onChangeNodeType(type)}
        />
      </div>

      <div className="node-properties__section">
        <label className="node-properties__label">{TEXT.workflowEditor.labelLabel}</label>
        <input
          value={(selectedNode.data.label as string) || ''}
          onChange={(e) => onUpdateNodeData('label', e.target.value)}
          className="node-properties__input"
        />
      </div>

      {selectedNode.type === 'tool_call' && (
        <>
          <div className="node-properties__section">
            <label className="node-properties__label">{TEXT.workflowEditor.toolNameLabel}</label>
            <ToolDropdown
              value={(selectedNode.data.tool_name as string) || ''}
              onChange={(value: string) => onUpdateNodeData('tool_name', value)}
            />
            <span className="node-properties__helper">{TEXT.workflowEditor.toolNameHelper}</span>
          </div>
          {hasSimpleSchema ? (
            <div className="node-properties__section">
              <label className="node-properties__label">{TEXT.workflowEditor.argsLabel}</label>
              {Object.entries(toolSchema.parameters.properties as Record<string, unknown>).map(([key, prop]) => {
                const currentArgs = (selectedNode.data.args as Record<string, unknown>) || {};
                return (
                  <div key={key} className="stack-sm">
                    <label className="node-properties__label">{key}</label>
                    <input
                      value={String(currentArgs[key] ?? '')}
                      onChange={(e) => {
                        onUpdateNodeData('args', { ...currentArgs, [key]: e.target.value });
                      }}
                      className="node-properties__input"
                    />
                    {typeof prop === 'object' && prop && 'description' in prop && (
                      <span className="node-properties__helper">
                        {(prop as { description?: string }).description}
                      </span>
                    )}
                  </div>
                );
              })}
              <span className="node-properties__helper">{TEXT.workflowEditor.argsHelper}</span>
            </div>
          ) : (
            <JsonTextarea
              label={TEXT.workflowEditor.argsJsonLabel}
              value={(selectedNode.data.args as object) || {}}
              onChange={(v) => onUpdateNodeData('args', v)}
              rows={4}
              placeholder={TEXT.workflowEditor.argsJsonPlaceholder}
            />
          )}
        </>
      )}

      {selectedNode.type === 'llm_decision' && (
        <>
          <div className="node-properties__section">
            <label className="node-properties__label">
              {TEXT.workflowEditor.promptLabel}{' '}
              <InsertVariableDropdown
                triggerType={triggerType}
                nodeId={selectedNode.id}
                nodes={nodes}
                edges={edges}
                onInsert={(v) => insertAtCursor(promptRef, v)}
              />
            </label>
            <textarea
              ref={promptRef}
              rows={4}
              value={(selectedNode.data.prompt as string) || ''}
              onChange={(e) => onUpdateNodeData('prompt', e.target.value)}
              className="node-properties__textarea"
            />
            <UpstreamVariables nodeId={selectedNode.id} nodes={nodes} edges={edges} />
            <span className="node-properties__helper">
              {((selectedNode.data.prompt as string) || '').length}{TEXT.workflowEditor.charactersSuffix}
            </span>
          </div>
          <div className="node-properties__section">
            <label className="node-properties__label">{TEXT.workflowEditor.branchesLabel}</label>
            <span className="node-properties__helper">{TEXT.workflowEditor.llmDecisionBranchesHelper}</span>
            <div className="node-properties__tag-list">
              {((selectedNode.data.branches as string[]) || []).map((branch: string) => (
                <span key={branch} className="node-properties__tag">
                  {branch}
                  <button
                    onClick={() => {
                      const current = (selectedNode.data.branches as string[]) || [];
                      onUpdateNodeData('branches', current.filter((b: string) => b !== branch));
                    }}
                    className="node-properties__tag-remove"
                    aria-label={`Remove branch ${branch}`}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
            <input
              placeholder={TEXT.workflowEditor.addBranchPlaceholder}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  const value = (e.target as HTMLInputElement).value.trim();
                  if (!value) return;
                  const current = (selectedNode.data.branches as string[]) || [];
                  if (!current.includes(value)) {
                    onUpdateNodeData('branches', [...current, value]);
                  }
                  (e.target as HTMLInputElement).value = '';
                }
              }}
              className="node-properties__input"
              aria-label={TEXT.workflowEditor.addBranchAriaLabel}
            />
          </div>
        </>
      )}

      {selectedNode.type === 'send_message' && (
        <>
          <div className="node-properties__section">
            <label className="node-properties__label">{TEXT.workflowEditor.platformLabel}</label>
            <PlatformDropdown
              value={(selectedNode.data.platform as string) || ''}
              onChange={(value: string) => onUpdateNodeData('platform', value)}
              includeEmpty
            />
            <span className="node-properties__helper">{TEXT.workflowEditor.platformHelper}</span>
          </div>
          <div className="node-properties__section">
            <label className="node-properties__label">{TEXT.workflowEditor.targetUserLabel}</label>
            <UserDropdown
              value={(selectedNode.data.target_user as string) || ''}
              onChange={(value: string) => onUpdateNodeData('target_user', value)}
            />
            <span className="node-properties__helper">{TEXT.workflowEditor.targetUserHelper}</span>
          </div>
          <div className="node-properties__section">
            <label className="node-properties__label">
              {TEXT.workflowEditor.messageLabel}{' '}
              <InsertVariableDropdown
                triggerType={triggerType}
                nodeId={selectedNode.id}
                nodes={nodes}
                edges={edges}
                onInsert={(v) => insertAtCursor(messageRef, v)}
              />
            </label>
            <textarea
              ref={messageRef}
              rows={4}
              value={(selectedNode.data.message as string) || ''}
              onChange={(e) => onUpdateNodeData('message', e.target.value)}
              className="node-properties__textarea"
            />
            <span className="node-properties__helper">{TEXT.workflowEditor.sendMessageHelper}</span>
            <TemplatePreview message={(selectedNode.data.message as string) || ''} />
          </div>
          <div className="node-properties__section">
            <label className="node-properties__checkbox-label">
              <input
                type="checkbox"
                checked={!!selectedNode.data.requires_response}
                onChange={(e) => onUpdateNodeData('requires_response', e.target.checked)}
              />
              {TEXT.workflowEditor.interactiveCheckbox}
            </label>
            {selectedNode.data.requires_response && (
              <>
                <div className="node-properties__indent">
                  <label className="node-properties__label">{TEXT.workflowEditor.interactiveTypeLabel}</label>
                  <label className="node-properties__radio-label">
                    <input
                      type="radio"
                      name="response_type"
                      value="buttons"
                      checked={(selectedNode.data.response_type as string) !== 'free_text'}
                      onChange={() => onUpdateNodeData('response_type', 'buttons')}
                    />
                    {TEXT.workflowEditor.interactiveTypeButtons}
                  </label>
                  <label className="node-properties__radio-label">
                    <input
                      type="radio"
                      name="response_type"
                      value="free_text"
                      checked={(selectedNode.data.response_type as string) === 'free_text'}
                      onChange={() => onUpdateNodeData('response_type', 'free_text')}
                    />
                    {TEXT.workflowEditor.interactiveTypeText}
                  </label>
                </div>
                {(selectedNode.data.response_type as string) !== 'free_text' && (
                  <div className="node-properties__indent">
                    <label className="node-properties__label">{TEXT.workflowEditor.buttonLabelsLabel}</label>
                    <div className="node-properties__tag-list">
                      {((selectedNode.data.buttons as string[]) || ['Approve', 'Deny']).map((btn: string) => (
                        <span key={btn} className="node-properties__tag">
                          {btn}
                          <button
                            onClick={() => {
                              const current = (selectedNode.data.buttons as string[]) || ['Approve', 'Deny'];
                              onUpdateNodeData('buttons', current.filter((b: string) => b !== btn));
                            }}
                            className="node-properties__tag-remove"
                            aria-label={`Remove button ${btn}`}
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                    <input
                      placeholder={TEXT.workflowEditor.addButtonPlaceholder}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          const value = (e.target as HTMLInputElement).value.trim();
                          if (!value) return;
                          const current = (selectedNode.data.buttons as string[]) || ['Approve', 'Deny'];
                          if (!current.includes(value)) {
                            onUpdateNodeData('buttons', [...current, value]);
                          }
                          (e.target as HTMLInputElement).value = '';
                        }
                      }}
                      className="node-properties__input"
                      aria-label={TEXT.workflowEditor.addButtonAriaLabel}
                    />
                  </div>
                )}
                <div className="node-properties__indent">
                  <label className="node-properties__label">{TEXT.workflowEditor.interactiveTimeoutLabel}</label>
                  <input
                    type="number"
                    min={1}
                    value={(selectedNode.data.timeout_seconds as number) ?? 300}
                    onChange={(e) => onUpdateNodeData('timeout_seconds', Number(e.target.value))}
                    className="node-properties__input node-properties__input--narrow"
                  />
                </div>
                <div className="node-properties__indent node-properties__helper">
                  {TEXT.workflowEditor.interactiveHelper}
                </div>
              </>
            )}
          </div>
        </>
      )}

      {selectedNode.type === 'http_request' && (
        <>
          <div className="node-properties__section">
            <label className="node-properties__label">{TEXT.workflowEditor.methodLabel}</label>
            <select
              value={(selectedNode.data.method as string) || 'GET'}
              onChange={(e) => onUpdateNodeData('method', e.target.value)}
              className="node-properties__select"
            >
              {['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'].map((m: string) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
          <div className="node-properties__section">
            <label className="node-properties__label">{TEXT.workflowEditor.urlLabel}</label>
            <input
              value={(selectedNode.data.url as string) || ''}
              onChange={(e) => onUpdateNodeData('url', e.target.value)}
              className="node-properties__input"
            />
          </div>
          <JsonTextarea
            label={TEXT.workflowEditor.headersJsonLabel}
            value={(selectedNode.data.headers as object) || {}}
            onChange={(v) => onUpdateNodeData('headers', v)}
            rows={3}
            validate
          />
          <div className="node-properties__section">
            <label className="node-properties__label">{TEXT.workflowEditor.bodyLabel}</label>
            <textarea
              rows={3}
              value={(selectedNode.data.body as string) || ''}
              onChange={(e) => onUpdateNodeData('body', e.target.value)}
              className="node-properties__textarea"
            />
          </div>
        </>
      )}

      {selectedNode.type === 'condition' && (
        <div className="node-properties__section">
          <label className="node-properties__label">
            {TEXT.workflowEditor.expressionLabel}{' '}
            <InsertVariableDropdown
              triggerType={triggerType}
              nodeId={selectedNode.id}
              nodes={nodes}
              edges={edges}
              onInsert={(v) => insertAtCursor(expressionRef, v)}
            />
          </label>
          <textarea
            ref={expressionRef}
            rows={3}
            value={(selectedNode.data.expression as string) || ''}
            onChange={(e) => onUpdateNodeData('expression', e.target.value)}
            className="node-properties__textarea"
            aria-label="Expression"
          />
          <span className="node-properties__helper">{TEXT.workflowEditor.conditionHelperAlt}</span>
          {(selectedNode.data.expression as string) && (
            <HighlightPreview text={(selectedNode.data.expression as string) || ''} />
          )}
          <SyntaxHelp />
        </div>
      )}

      {selectedNode.type === 'investigate' && (
        <>
          <div className="node-properties__section">
            <label className="node-properties__label">{TEXT.workflowEditor.topicLabel}</label>
            <textarea
              rows={4}
              value={(selectedNode.data.topic as string) || ''}
              onChange={(e) => onUpdateNodeData('topic', e.target.value)}
              className="node-properties__textarea"
            />
          </div>
          <div className="node-properties__section">
            <label className="node-properties__label">{TEXT.workflowEditor.depthLabel}</label>
            <select
              value={(selectedNode.data.depth as string) || 'shallow'}
              onChange={(e) => onUpdateNodeData('depth', e.target.value)}
              className="node-properties__select"
            >
              <option value="shallow">shallow</option>
              <option value="deep">deep</option>
            </select>
          </div>
          <div className="node-properties__section">
            <label className="node-properties__label">{TEXT.workflowEditor.toolsLabel}</label>
            <div className="node-properties__tool-list">
              {tools.map((t: string) => {
                const selected = ((selectedNode.data.tools as string[]) || []);
                return (
                  <label key={t} className="node-properties__tool-label">
                    <input
                      type="checkbox"
                      checked={selected.includes(t)}
                      onChange={(e) => {
                        const current = (selectedNode.data.tools as string[]) || [];
                        if (e.target.checked) {
                          onUpdateNodeData('tools', [...current, t]);
                        } else {
                          onUpdateNodeData('tools', current.filter((x: string) => x !== t));
                        }
                      }}
                      aria-label={`Tool ${t}`}
                    />
                    {t}
                  </label>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
