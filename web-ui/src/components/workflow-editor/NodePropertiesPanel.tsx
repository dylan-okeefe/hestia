import { useRef, useState } from 'react';
import type { Node, Edge } from 'reactflow';
import NodeTypeDropdown from '../forms/NodeTypeDropdown';
import PlatformDropdown from '../forms/PlatformDropdown';
import UserDropdown from '../forms/UserDropdown';
import ToolDropdown from '../forms/ToolDropdown';
import type { ToolSchema } from '../../api/client';

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

function SyntaxHelp() {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ marginTop: '0.5rem' }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{ fontSize: '0.75rem', background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: '#2563eb' }}
      >
        {open ? 'Hide' : 'Show'} Syntax Help
      </button>
      {open && (
        <div style={{ fontSize: '0.75rem', color: '#444', marginTop: '0.25rem', padding: '0.5rem', background: '#f9fafb', borderRadius: 4 }}>
          <p style={{ margin: '0 0 0.25rem' }}><strong>Variables:</strong> input.field_name</p>
          <p style={{ margin: '0 0 0.25rem' }}><strong>Comparisons:</strong> ==, !=, &lt;, &gt;, &lt;=, &gt;=</p>
          <p style={{ margin: '0 0 0.25rem' }}><strong>Logic:</strong> and, or, not</p>
          <p style={{ margin: '0 0 0.25rem' }}><strong>Arithmetic:</strong> +, -, *, / (no power)</p>
          <p style={{ margin: '0 0 0.25rem' }}><strong>Literals:</strong> strings in quotes, numbers, True, False, None</p>
          <p style={{ margin: 0 }}><strong>Examples:</strong> input.status == &quot;error&quot;, input.count &gt; 10 and input.retry, not input.skipped</p>
        </div>
      )}
    </div>
  );
}

function UpstreamVariables({ nodeId, nodes, edges }: { nodeId: string; nodes: Node[]; edges: Edge[] }) {
  const upstream = edges
    .filter((e) => e.target === nodeId)
    .map((e) => nodes.find((n) => n.id === e.source))
    .filter(Boolean) as Node[];

  if (upstream.length === 0) return null;

  return (
    <div style={{ fontSize: '0.75rem', color: '#666', marginTop: '0.25rem' }}>
      Available:{' '}
      {upstream.map((n) => (
        <code key={n.id} style={{ background: '#f3f4f6', padding: '0.125rem 0.25rem', borderRadius: 4 }}>
          {n.id}.output
        </code>
      ))}
    </div>
  );
}

function HighlightPreview({ text }: { text: string }) {
  const parts = text.split(/(\{[^}]+\})/g);
  return (
    <div style={{ fontSize: '0.875rem', padding: '0.5rem', background: '#f9fafb', borderRadius: 4, minHeight: '1.5rem', marginTop: '0.25rem' }}>
      {parts.map((part, i) =>
        part.match(/\{[^}]+\}/) ? (
          <span key={i} style={{ background: '#dbeafe', color: '#1e40af', padding: '0.125rem 0.25rem', borderRadius: 4, fontSize: '0.75rem' }}>
            {part}
          </span>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </div>
  );
}

function TemplatePreview({ message }: { message: string }) {
  const count = message.length;
  return (
    <div style={{ marginTop: '0.5rem' }}>
      <div style={{ fontSize: '0.875rem', marginBottom: '0.25rem' }}>Preview</div>
      <HighlightPreview text={message} />
      <div style={{ fontSize: '0.75rem', marginTop: '0.25rem', color: count > 4096 ? '#dc2626' : count > 4000 ? '#ca8a04' : '#666' }}>
        {count} characters
        {count > 4096 && ' — Exceeds Telegram limit'}
        {count > 4000 && count <= 4096 && ' — May exceed Telegram limit'}
      </div>
    </div>
  );
}

function JsonTextarea({
  value,
  onChange,
  rows,
  label,
  validate,
  placeholder,
}: {
  value: object;
  onChange: (v: object) => void;
  rows: number;
  label: string;
  validate?: boolean;
  placeholder?: string;
}) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));
  const [error, setError] = useState<string | null>(null);

  const handleBlur = () => {
    if (!validate) {
      try {
        onChange(JSON.parse(text));
        setError(null);
      } catch {
        // ignore invalid JSON
      }
      return;
    }
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        setError('Headers must be a JSON object, not an array or primitive.');
        return;
      }
      onChange(parsed);
      setError(null);
    } catch {
      setError('Invalid JSON — headers must be a JSON object like {"Authorization": "Bearer ..."}');
    }
  };

  return (
    <div style={{ marginBottom: '0.75rem' }}>
      <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>{label}</label>
      <textarea
        rows={rows}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={handleBlur}
        placeholder={placeholder}
        style={{
          width: '100%',
          border: error ? '2px solid #dc2626' : '1px solid #ccc',
        }}
        aria-invalid={error ? 'true' : 'false'}
      />
      {error && <span style={{ color: '#dc2626', fontSize: '0.75rem' }}>{error}</span>}
    </div>
  );
}

function InsertVariableDropdown({
  triggerType,
  nodeId,
  nodes,
  edges,
  onInsert,
}: {
  triggerType: string;
  nodeId: string;
  nodes: Node[];
  edges: Edge[];
  onInsert: (variable: string) => void;
}) {
  const upstream = edges
    .filter((e) => e.target === nodeId)
    .map((e) => nodes.find((n) => n.id === e.source))
    .filter(Boolean) as Node[];

  const triggerVars = TRIGGER_VARIABLES[triggerType] || [];
  if (triggerVars.length === 0 && upstream.length === 0) return null;

  return (
    <select
      style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', marginLeft: '0.5rem' }}
      value=""
      onChange={(e) => {
        if (e.target.value) {
          onInsert(e.target.value);
          e.target.value = '';
        }
      }}
      aria-label="Insert variable"
    >
      <option value="">Insert variable…</option>
      {triggerVars.map((v) => (
        <option key={`trigger_${v}`} value={v}>
          Trigger: {v}
        </option>
      ))}
      {upstream.map((n) => (
        <option key={`upstream_${n.id}`} value={`${n.id}.output`}>
          Node {n.id}: output
        </option>
      ))}
    </select>
  );
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

  const insertAtCursor = (ref: React.RefObject<HTMLTextAreaElement>, value: string) => {
    const el = ref.current;
    if (!el) return;
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? el.value.length;
    const before = el.value.slice(0, start);
    const after = el.value.slice(end);
    const newValue = before + `{data.${value}}` + after;
    // Find the key being edited based on the ref
    if (ref === messageRef) {
      onUpdateNodeData('message', newValue);
    } else if (ref === expressionRef) {
      onUpdateNodeData('expression', newValue);
    } else if (ref === promptRef) {
      onUpdateNodeData('prompt', newValue);
    }
    requestAnimationFrame(() => {
      if (ref.current) {
        const pos = start + `{data.${value}}`.length;
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
    <div
      key={selectedNode.id}
      style={{
        width: 280,
        borderLeft: '1px solid #ddd',
        padding: '1rem',
        overflowY: 'auto',
      }}
    >
      <h3 style={{ marginTop: 0 }}>Properties</h3>
      <div style={{ marginBottom: '0.75rem' }}>
        <button
          onClick={() => onDeleteNode(selectedNode.id)}
          style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', color: 'red', marginBottom: '0.5rem' }}
        >
          Delete Node
        </button>
      </div>
      <div style={{ marginBottom: '0.75rem' }}>
        <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>ID</label>
        <input value={selectedNode.id} readOnly style={{ width: '100%' }} />
      </div>
      <div style={{ marginBottom: '0.75rem' }}>
        <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Type</label>
        <NodeTypeDropdown
          value={selectedNode.type || ''}
          onChange={(type) => onChangeNodeType(type)}
        />
      </div>
      <div style={{ marginBottom: '0.75rem' }}>
        <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Label</label>
        <input
          value={(selectedNode.data.label as string) || ''}
          onChange={(e) => onUpdateNodeData('label', e.target.value)}
          style={{ width: '100%' }}
        />
      </div>

      {selectedNode.type === 'tool_call' && (
        <>
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>
              Tool Name
            </label>
            <ToolDropdown
              value={(selectedNode.data.tool_name as string) || ''}
              onChange={(value: string) => onUpdateNodeData('tool_name', value)}
            />
            <span style={{ fontSize: '0.75rem', color: '#666', display: 'block', marginTop: '0.25rem' }}>
              The registered tool to invoke.
            </span>
          </div>
          {hasSimpleSchema ? (
            <div style={{ marginBottom: '0.75rem' }}>
              <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Args</label>
              {Object.entries(toolSchema.parameters.properties as Record<string, unknown>).map(([key, prop]) => {
                const currentArgs = (selectedNode.data.args as Record<string, unknown>) || {};
                return (
                  <div key={key} style={{ marginBottom: '0.5rem' }}>
                    <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>
                      {key}
                    </label>
                    <input
                      value={String(currentArgs[key] ?? '')}
                      onChange={(e) => {
                        onUpdateNodeData('args', { ...currentArgs, [key]: e.target.value });
                      }}
                      style={{ width: '100%' }}
                    />
                    {typeof prop === 'object' && prop && 'description' in prop && (
                      <span style={{ fontSize: '0.75rem', color: '#666', display: 'block', marginTop: '0.125rem' }}>
                        {(prop as { description?: string }).description}
                      </span>
                    )}
                  </div>
                );
              })}
              <span style={{ fontSize: '0.75rem', color: '#666', display: 'block', marginTop: '0.25rem' }}>
                JSON arguments passed to the tool.
              </span>
            </div>
          ) : (
            <JsonTextarea
              label="Args (JSON)"
              value={(selectedNode.data.args as object) || {}}
              onChange={(v) => onUpdateNodeData('args', v)}
              rows={4}
              placeholder='{"query": "example"}'
            />
          )}
        </>
      )}

      {selectedNode.type === 'llm_decision' && (
        <>
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>
              Prompt{' '}
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
              style={{ width: '100%' }}
            />
            <UpstreamVariables nodeId={selectedNode.id} nodes={nodes} edges={edges} />
            <div style={{ fontSize: '0.75rem', marginTop: '0.25rem', color: '#666' }}>
              {((selectedNode.data.prompt as string) || '').length} characters
            </div>
          </div>
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>
              Branches
            </label>
            <span style={{ fontSize: '0.75rem', color: '#666', display: 'block', marginBottom: '0.25rem' }}>
              Possible outcomes. The LLM selects one based on the prompt.
            </span>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem', marginBottom: '0.25rem' }}>
              {((selectedNode.data.branches as string[]) || []).map((branch: string) => (
                <span
                  key={branch}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.25rem',
                    background: '#e9d5ff',
                    color: '#581c87',
                    padding: '0.125rem 0.5rem',
                    borderRadius: '9999px',
                    fontSize: '0.75rem',
                  }}
                >
                  {branch}
                  <button
                    onClick={() => {
                      const current = (selectedNode.data.branches as string[]) || [];
                      onUpdateNodeData(
                        'branches',
                        current.filter((b: string) => b !== branch)
                      );
                    }}
                    style={{
                      background: 'transparent',
                      border: 'none',
                      cursor: 'pointer',
                      padding: 0,
                      fontSize: '0.75rem',
                      color: '#581c87',
                      lineHeight: 1,
                    }}
                    aria-label={`Remove branch ${branch}`}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
            <input
              placeholder="Add branch…"
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
              style={{ width: '100%' }}
              aria-label="Add branch"
            />
          </div>
        </>
      )}

      {selectedNode.type === 'send_message' && (
        <>
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>
              Platform
            </label>
            <PlatformDropdown
              value={(selectedNode.data.platform as string) || ''}
              onChange={(value: string) => onUpdateNodeData('platform', value)}
              includeEmpty
            />
            <span style={{ fontSize: '0.75rem', color: '#666', display: 'block', marginTop: '0.25rem' }}>
              Which adapter sends the message.
            </span>
          </div>
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>
              Target User
            </label>
            <UserDropdown
              value={(selectedNode.data.target_user as string) || ''}
              onChange={(value: string) => onUpdateNodeData('target_user', value)}
            />
            <span style={{ fontSize: '0.75rem', color: '#666', display: 'block', marginTop: '0.25rem' }}>
              The user or room that receives the message.
            </span>
          </div>
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>
              Message{' '}
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
              style={{ width: '100%' }}
            />
            <span style={{ fontSize: '0.75rem', color: '#666', display: 'block', marginTop: '0.25rem' }}>
              Use {'{data.field_name}'} to reference trigger or upstream node outputs.
            </span>
            <TemplatePreview message={(selectedNode.data.message as string) || ''} />
          </div>
        </>
      )}

      {selectedNode.type === 'http_request' && (
        <>
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Method</label>
            <select
              value={(selectedNode.data.method as string) || 'GET'}
              onChange={(e) => onUpdateNodeData('method', e.target.value)}
              style={{ width: '100%' }}
            >
              {['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'].map((m: string) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>URL</label>
            <input
              value={(selectedNode.data.url as string) || ''}
              onChange={(e) => onUpdateNodeData('url', e.target.value)}
              style={{ width: '100%' }}
            />
          </div>
          <JsonTextarea
            label="Headers (JSON)"
            value={(selectedNode.data.headers as object) || {}}
            onChange={(v) => onUpdateNodeData('headers', v)}
            rows={3}
            validate
          />
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Body</label>
            <textarea
              rows={3}
              value={(selectedNode.data.body as string) || ''}
              onChange={(e) => onUpdateNodeData('body', e.target.value)}
              style={{ width: '100%' }}
            />
          </div>
        </>
      )}

      {selectedNode.type === 'condition' && (
        <div style={{ marginBottom: '0.75rem' }}>
          <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>
            Expression{' '}
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
            style={{ width: '100%' }}
            aria-label="Expression"
          />
          <span style={{ fontSize: '0.75rem', color: '#666', display: 'block', marginTop: '0.25rem' }}>
            A condition that evaluates to true or false.
          </span>
          {(selectedNode.data.expression as string) && (
            <HighlightPreview text={(selectedNode.data.expression as string) || ''} />
          )}
          <SyntaxHelp />
        </div>
      )}

      {selectedNode.type === 'investigate' && (
        <>
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Topic</label>
            <textarea
              rows={4}
              value={(selectedNode.data.topic as string) || ''}
              onChange={(e) => onUpdateNodeData('topic', e.target.value)}
              style={{ width: '100%' }}
            />
          </div>
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Depth</label>
            <select
              value={(selectedNode.data.depth as string) || 'shallow'}
              onChange={(e) => onUpdateNodeData('depth', e.target.value)}
              style={{ width: '100%' }}
            >
              <option value="shallow">shallow</option>
              <option value="deep">deep</option>
            </select>
          </div>
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Tools</label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              {tools.map((t: string) => {
                const selected = ((selectedNode.data.tools as string[]) || []);
                return (
                  <label key={t} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.875rem', cursor: 'pointer' }}>
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
