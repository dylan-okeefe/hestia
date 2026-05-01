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
} from '../api/client';

const nodeTypes = ['default', 'input', 'output'] as const;

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
      type: 'default',
      position: { x: Math.random() * 200 + 50, y: Math.random() * 200 + 50 },
      data: { label: 'New Node' },
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
    try {
      await testRunWorkflow(id);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Test run failed');
    } finally {
      setTesting(false);
    }
  };

  const updateSelectedNodeData = (key: string, value: string) => {
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
        <button onClick={handleSave} disabled={saving}>
          {saving ? 'Saving…' : 'Save Version'}
        </button>
        <button onClick={handleActivate} disabled={!activeVersionId}>
          Activate Version
        </button>
        <button onClick={handleTestRun} disabled={testing}>
          {testing ? 'Running…' : 'Test Run'}
        </button>
        {error && <span style={{ color: 'red', marginLeft: 'auto' }}>{error}</span>}
      </div>
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
            fitView
          >
            <Background />
            <Controls />
            <MiniMap />
          </ReactFlow>
        </div>
        {selectedNode && (
          <div
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
                {nodeTypes.map((t) => (
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
          </div>
        )}
      </div>
    </div>
  );
}
