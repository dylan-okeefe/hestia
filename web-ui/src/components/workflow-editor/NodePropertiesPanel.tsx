import type { Node } from 'reactflow';
import { EDITOR_NODE_TYPES } from './constants';

interface NodePropertiesPanelProps {
  selectedNode: Node;
  onDeleteNode: (nodeId: string) => void;
  onUpdateNodeData: (key: string, value: unknown) => void;
  onChangeNodeType: (type: string) => void;
  tools: string[];
  platforms: string[];
}

export default function NodePropertiesPanel({
  selectedNode,
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
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Args (JSON)</label>
            <textarea
              rows={4}
              defaultValue={JSON.stringify((selectedNode.data.args as object) || {}, null, 2)}
              onBlur={(e) => {
                try {
                  onUpdateNodeData('args', JSON.parse(e.target.value));
                } catch {
                  // ignore invalid JSON
                }
              }}
              style={{ width: '100%' }}
            />
          </div>
        </>
      )}

      {selectedNode.type === 'llm_decision' && (
        <>
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Prompt</label>
            <textarea
              rows={4}
              value={(selectedNode.data.prompt as string) || ''}
              onChange={(e) => onUpdateNodeData('prompt', e.target.value)}
              style={{ width: '100%' }}
            />
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
              {['GET', 'POST', 'PUT', 'DELETE'].map((m: string) => (
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
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Headers (JSON)</label>
            <textarea
              rows={3}
              defaultValue={JSON.stringify((selectedNode.data.headers as object) || {}, null, 2)}
              onBlur={(e) => {
                try {
                  onUpdateNodeData('headers', JSON.parse(e.target.value));
                } catch {
                  // ignore invalid JSON
                }
              }}
              style={{ width: '100%' }}
            />
          </div>
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
          <span style={{ fontSize: '0.75rem', color: '#666' }}>
            Supported: comparisons (==, !=, &lt;, &gt;, &lt;=, &gt;=), logic (and, or, not), arithmetic (+, -, *, /). No function calls or power operator.
          </span>
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
