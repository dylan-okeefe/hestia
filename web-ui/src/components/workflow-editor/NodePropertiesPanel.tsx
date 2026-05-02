import { useState } from 'react';
import type { Node, Edge } from 'reactflow';
import { EDITOR_NODE_TYPES } from './constants';

interface NodePropertiesPanelProps {
  selectedNode: Node;
  nodes: Node[];
  edges: Edge[];
  onDeleteNode: (nodeId: string) => void;
  onUpdateNodeData: (key: string, value: unknown) => void;
  onChangeNodeType: (type: string) => void;
  tools: string[];
  platforms: string[];
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

function TemplatePreview({ message }: { message: string }) {
  const parts = message.split(/(\{\{[^}]+\}\})/g);
  const count = message.length;
  return (
    <div style={{ marginTop: '0.5rem' }}>
      <div style={{ fontSize: '0.875rem', marginBottom: '0.25rem' }}>Preview</div>
      <div style={{ fontSize: '0.875rem', padding: '0.5rem', background: '#f9fafb', borderRadius: 4, minHeight: '1.5rem' }}>
        {parts.map((part, i) =>
          part.match(/\{\{[^}]+\}\}/) ? (
            <span key={i} style={{ background: '#dbeafe', color: '#1e40af', padding: '0.125rem 0.25rem', borderRadius: 4, fontSize: '0.75rem' }}>
              {part}
            </span>
          ) : (
            <span key={i}>{part}</span>
          )
        )}
      </div>
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
}: {
  value: object;
  onChange: (v: object) => void;
  rows: number;
  label: string;
  validate?: boolean;
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

export default function NodePropertiesPanel({
  selectedNode,
  nodes,
  edges,
  onDeleteNode,
  onUpdateNodeData,
  onChangeNodeType,
  tools,
  platforms,
}: NodePropertiesPanelProps) {
  return (
    <div
      key={selectedNode.id}
      style={{
        width: 260,
        borderLeft: '1px solid #ddd',
        padding: '1rem',
        overflowY: 'auto',
      }}
    >
      <h3>Properties</h3>
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
        <select
          value={selectedNode.type || 'default'}
          onChange={(e) => onChangeNodeType(e.target.value)}
          style={{ width: '100%' }}
        >
          {EDITOR_NODE_TYPES.map((t: string) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
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
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Tool Name</label>
            <select
              value={(selectedNode.data.tool_name as string) || ''}
              onChange={(e) => onUpdateNodeData('tool_name', e.target.value)}
              style={{ width: '100%' }}
              aria-label="Tool name"
            >
              <option value="" disabled>
                Select a tool…
              </option>
              {tools.map((t: string) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <JsonTextarea
            label="Args (JSON)"
            value={(selectedNode.data.args as object) || {}}
            onChange={(v) => onUpdateNodeData('args', v)}
            rows={4}
          />
        </>
      )}

      {selectedNode.type === 'llm_decision' && (
        <>
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>
              Prompt{' '}
              <span style={{ fontSize: '0.75rem', color: '#666', fontWeight: 'normal' }}>
                Use {'{{node_id.field}}'} to reference upstream outputs
              </span>
            </label>
            <textarea
              rows={4}
              value={(selectedNode.data.prompt as string) || ''}
              onChange={(e) => onUpdateNodeData('prompt', e.target.value)}
              style={{ width: '100%' }}
            />
            <UpstreamVariables nodeId={selectedNode.id} nodes={nodes} edges={edges} />
          </div>
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Branches</label>
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
                if (e.key === 'Enter' || e.key === ',') {
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
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Platform</label>
            <select
              value={(selectedNode.data.platform as string) || ''}
              onChange={(e) => onUpdateNodeData('platform', e.target.value)}
              style={{ width: '100%' }}
              aria-label="Platform"
            >
              <option value="" disabled>
                Select a platform…
              </option>
              {platforms.map((p: string) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Message</label>
            <textarea
              rows={4}
              value={(selectedNode.data.message as string) || ''}
              onChange={(e) => onUpdateNodeData('message', e.target.value)}
              style={{ width: '100%' }}
            />
            <TemplatePreview message={(selectedNode.data.message as string) || ''} />
          </div>
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Target User</label>
            <input
              value={(selectedNode.data.target_user as string) || ''}
              onChange={(e) => onUpdateNodeData('target_user', e.target.value)}
              style={{ width: '100%' }}
            />
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
          <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Expression</label>
          <textarea
            rows={3}
            value={(selectedNode.data.expression as string) || ''}
            onChange={(e) => onUpdateNodeData('expression', e.target.value)}
            style={{ width: '100%' }}
            aria-label="Expression"
          />
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
