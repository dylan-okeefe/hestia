import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  type Connection,
  type Node,
} from 'reactflow';
import 'reactflow/dist/style.css';
import {
  fetchWorkflow,
  fetchWorkflowVersions,
  saveWorkflowVersion,
  activateWorkflowVersion,
  testRunWorkflow,
  type WorkflowNode,
  type WorkflowEdge,
  type ExecutionResult,
} from '../api/client';
import {
  ToolCallNode,
  LLMDecisionNode,
  SendMessageNode,
  HttpRequestNode,
  ConditionNode,
  InvestigateNode,
} from '../components/workflow-nodes';

const EDITOR_NODE_TYPES = [
  'default',
  'tool_call',
  'llm_decision',
  'send_message',
  'http_request',
  'condition',
  'investigate',
] as const;

const nodeTypesMap = {
  tool_call: ToolCallNode,
  llm_decision: LLMDecisionNode,
  send_message: SendMessageNode,
  http_request: HttpRequestNode,
  condition: ConditionNode,
  investigate: InvestigateNode,
};

export default function WorkflowEditor() {
  const { id } = useParams<{ id: string }>();
  const [workflowName, setWorkflowName] = useState('');
  const [, setVersions] = useState<{ id: string; version_number: number; activated_at: string | null }[]>([]);
  const [activeVersionId, setActiveVersionId] = useState<string | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<ExecutionResult | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [addNodeType, setAddNodeType] = useState<string>('default');

  useEffect(() => {
    if (!id) return;

    Promise.all([fetchWorkflow(id), fetchWorkflowVersions(id)])
      .then(([wf, vs]) => {
        setWorkflowName(wf.name);
        setVersions(vs.versions);
        const active = vs.versions.find((v) => v.activated_at !== null);
        if (active) {
          setActiveVersionId(active.id);
          setNodes(active.nodes.map((n) => ({ ...n, data: n.data || {} })));
          setEdges(active.edges.map((e) => ({ ...e })));
        }
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [id, setNodes, setEdges]);

  const onConnect = useCallback(
    (connection: Connection) => setEdges((eds) => addEdge(connection, eds)),
    [setEdges]
  );

  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    setSelectedNode(node);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
  }, []);

  const handleAddNode = () => {
    const newNode: Node = {
      id: `node_${Date.now()}`,
      type: addNodeType,
      position: { x: Math.random() * 200 + 50, y: Math.random() * 200 + 50 },
      data: (() => {
        switch (addNodeType) {
          case 'tool_call':
            return { label: 'Tool Call', tool_name: '', args: {} };
          case 'llm_decision':
            return { label: 'LLM Decision', prompt: '', branches: [] };
          case 'send_message':
            return { label: 'Send Message', platform: '', message: '', target_user: '' };
          case 'http_request':
            return { label: 'HTTP Request', url: '', method: 'GET', headers: {}, body: '' };
          case 'condition':
            return { label: 'Condition', expression: '' };
          case 'investigate':
            return { label: 'Investigate', topic: '', depth: 'shallow', tools: '' };
          default:
            return { label: 'New Node' };
        }
      })(),
    };
    setNodes((nds) => [...nds, newNode]);
  };

  const handleSave = async () => {
    if (!id) return;
    setSaving(true);
    try {
      const serialNodes: WorkflowNode[] = nodes.map((n) => ({
        id: n.id,
        type: n.type || 'default',
        position: n.position,
        data: n.data,
      }));
      const serialEdges: WorkflowEdge[] = edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        type: e.type,
      }));
      const version = await saveWorkflowVersion(id, serialNodes, serialEdges);
      setVersions((vs) => [...vs, version]);
      setActiveVersionId(version.id);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleActivate = async () => {
    if (!id || !activeVersionId) return;
    try {
      await activateWorkflowVersion(id, activeVersionId);
      setVersions((vs) =>
        vs.map((v) =>
          v.id === activeVersionId ? { ...v, activated_at: new Date().toISOString() } : { ...v, activated_at: null }
        )
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Activation failed');
    }
  };

  const handleTestRun = async () => {
    if (!id) return;
    setTesting(true);
    setTestResult(null);
    setTestError(null);
    try {
      const result = await testRunWorkflow(id);
      setTestResult(result);
      setError(null);
    } catch (err) {
      setTestError(err instanceof Error ? err.message : 'Test run failed');
      setError(err instanceof Error ? err.message : 'Test run failed');
    } finally {
      setTesting(false);
    }
  };

  const updateSelectedNodeData = (key: string, value: unknown) => {
    if (!selectedNode) return;
    setNodes((nds) =>
      nds.map((n) =>
        n.id === selectedNode.id ? { ...n, data: { ...n.data, [key]: value } } : n
      )
    );
    setSelectedNode((prev) => (prev ? { ...prev, data: { ...prev.data, [key]: value } } : prev));
  };

  if (loading) {
    return (
      <div style={{ padding: '1rem' }}>
        <p>Loading workflow…</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 60px)' }}>
      <div style={{ padding: '0.5rem 1rem', borderBottom: '1px solid #ddd', display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <h2 style={{ margin: 0 }}>{workflowName}</h2>
        <button onClick={handleAddNode}>Add Node</button>
        <select
          value={addNodeType}
          onChange={(e) => setAddNodeType(e.target.value)}
          style={{ padding: '0.25rem 0.5rem' }}
          aria-label="Node type to add"
        >
          {EDITOR_NODE_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <button onClick={handleSave} disabled={saving}>
          {saving ? 'Saving…' : 'Save Version'}
        </button>
        <button onClick={handleActivate} disabled={!activeVersionId}>
          Activate Version
        </button>
        <button onClick={handleTestRun} disabled={testing}>
          {testing ? 'Running…' : 'Test Run'}
        </button>
        {error && !testError && <span style={{ color: 'red', marginLeft: 'auto' }}>{error}</span>}
      </div>
      {(testResult || testError) && (
        <div
          style={{
            borderTop: '1px solid #ddd',
            padding: '1rem',
            maxHeight: '40vh',
            overflowY: 'auto',
            background: '#fafafa',
          }}
        >
          {testResult && (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.5rem' }}>
                <strong>Status:</strong>
                <span
                  style={{
                    color: testResult.status === 'ok' ? 'green' : 'red',
                    fontWeight: 'bold',
                  }}
                >
                  {testResult.status}
                </span>
                <span>
                  <strong>Total time:</strong> {testResult.total_elapsed_ms}ms
                </span>
                <span>
                  <strong>Tokens:</strong> {testResult.total_prompt_tokens} prompt + {testResult.total_completion_tokens} completion
                </span>
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #ccc' }}>
                    <th style={{ textAlign: 'left', padding: '0.25rem' }}>Node</th>
                    <th style={{ textAlign: 'left', padding: '0.25rem' }}>Status</th>
                    <th style={{ textAlign: 'left', padding: '0.25rem' }}>Time (ms)</th>
                    <th style={{ textAlign: 'left', padding: '0.25rem' }}>Prompt</th>
                    <th style={{ textAlign: 'left', padding: '0.25rem' }}>Completion</th>
                    <th style={{ textAlign: 'left', padding: '0.25rem' }}>Output</th>
                  </tr>
                </thead>
                <tbody>
                  {testResult.node_results.map((nr) => (
                    <tr key={nr.node_id} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={{ padding: '0.25rem' }}>{nr.node_id}</td>
                      <td style={{ padding: '0.25rem', color: nr.status === 'ok' ? 'green' : 'red' }}>{nr.status}</td>
                      <td style={{ padding: '0.25rem' }}>{nr.elapsed_ms}</td>
                      <td style={{ padding: '0.25rem' }}>{nr.prompt_tokens}</td>
                      <td style={{ padding: '0.25rem' }}>{nr.completion_tokens}</td>
                      <td style={{ padding: '0.25rem' }}>
                        {typeof nr.output === 'string' ? nr.output : JSON.stringify(nr.output)?.slice(0, 100)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          {testError && (
            <div style={{ color: 'red' }}>
              <strong>Test Run Failed:</strong> {testError}
            </div>
          )}
        </div>
      )}
      <div style={{ display: 'flex', flex: 1 }}>
        <div style={{ flex: 1 }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypesMap}
            fitView
          >
            <Background />
            <Controls />
            <MiniMap />
          </ReactFlow>
        </div>
        {selectedNode && (
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
              <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>ID</label>
              <input value={selectedNode.id} readOnly style={{ width: '100%' }} />
            </div>
            <div style={{ marginBottom: '0.75rem' }}>
              <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Type</label>
              <select
                value={selectedNode.type || 'default'}
                onChange={(e) => {
                  const type = e.target.value;
                  setNodes((nds) => nds.map((n) => (n.id === selectedNode.id ? { ...n, type } : n)));
                  setSelectedNode((prev) => (prev ? { ...prev, type } : prev));
                }}
                style={{ width: '100%' }}
              >
                {EDITOR_NODE_TYPES.map((t) => (
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
                onChange={(e) => updateSelectedNodeData('label', e.target.value)}
                style={{ width: '100%' }}
              />
            </div>

            {selectedNode.type === 'tool_call' && (
              <>
                <div style={{ marginBottom: '0.75rem' }}>
                  <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Tool Name</label>
                  <input
                    value={(selectedNode.data.tool_name as string) || ''}
                    onChange={(e) => updateSelectedNodeData('tool_name', e.target.value)}
                    style={{ width: '100%' }}
                  />
                </div>
                <div style={{ marginBottom: '0.75rem' }}>
                  <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Args (JSON)</label>
                  <textarea
                    rows={4}
                    defaultValue={JSON.stringify((selectedNode.data.args as object) || {}, null, 2)}
                    onBlur={(e) => {
                      try {
                        updateSelectedNodeData('args', JSON.parse(e.target.value));
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
                    onChange={(e) => updateSelectedNodeData('prompt', e.target.value)}
                    style={{ width: '100%' }}
                  />
                </div>
                <div style={{ marginBottom: '0.75rem' }}>
                  <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Branches (comma-separated)</label>
                  <input
                    value={((selectedNode.data.branches as string[]) || []).join(', ')}
                    onChange={(e) =>
                      updateSelectedNodeData(
                        'branches',
                        e.target.value.split(',').map((s) => s.trim()).filter(Boolean)
                      )
                    }
                    style={{ width: '100%' }}
                  />
                </div>
              </>
            )}

            {selectedNode.type === 'send_message' && (
              <>
                <div style={{ marginBottom: '0.75rem' }}>
                  <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Platform</label>
                  <input
                    value={(selectedNode.data.platform as string) || ''}
                    onChange={(e) => updateSelectedNodeData('platform', e.target.value)}
                    style={{ width: '100%' }}
                  />
                </div>
                <div style={{ marginBottom: '0.75rem' }}>
                  <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Message</label>
                  <textarea
                    rows={4}
                    value={(selectedNode.data.message as string) || ''}
                    onChange={(e) => updateSelectedNodeData('message', e.target.value)}
                    style={{ width: '100%' }}
                  />
                </div>
                <div style={{ marginBottom: '0.75rem' }}>
                  <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Target User</label>
                  <input
                    value={(selectedNode.data.target_user as string) || ''}
                    onChange={(e) => updateSelectedNodeData('target_user', e.target.value)}
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
                    onChange={(e) => updateSelectedNodeData('method', e.target.value)}
                    style={{ width: '100%' }}
                  >
                    {['GET', 'POST', 'PUT', 'DELETE'].map((m) => (
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
                    onChange={(e) => updateSelectedNodeData('url', e.target.value)}
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
                        updateSelectedNodeData('headers', JSON.parse(e.target.value));
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
                    onChange={(e) => updateSelectedNodeData('body', e.target.value)}
                    style={{ width: '100%' }}
                  />
                </div>
              </>
            )}

            {selectedNode.type === 'condition' && (
              <div style={{ marginBottom: '0.75rem' }}>
                <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Expression</label>
                <input
                  value={(selectedNode.data.expression as string) || ''}
                  onChange={(e) => updateSelectedNodeData('expression', e.target.value)}
                  style={{ width: '100%' }}
                />
              </div>
            )}

            {selectedNode.type === 'investigate' && (
              <>
                <div style={{ marginBottom: '0.75rem' }}>
                  <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Topic</label>
                  <textarea
                    rows={4}
                    value={(selectedNode.data.topic as string) || ''}
                    onChange={(e) => updateSelectedNodeData('topic', e.target.value)}
                    style={{ width: '100%' }}
                  />
                </div>
                <div style={{ marginBottom: '0.75rem' }}>
                  <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Depth</label>
                  <select
                    value={(selectedNode.data.depth as string) || 'shallow'}
                    onChange={(e) => updateSelectedNodeData('depth', e.target.value)}
                    style={{ width: '100%' }}
                  >
                    <option value="shallow">shallow</option>
                    <option value="deep">deep</option>
                  </select>
                </div>
                <div style={{ marginBottom: '0.75rem' }}>
                  <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Tools (comma-separated)</label>
                  <input
                    value={(selectedNode.data.tools as string) || ''}
                    onChange={(e) => updateSelectedNodeData('tools', e.target.value)}
                    style={{ width: '100%' }}
                  />
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
