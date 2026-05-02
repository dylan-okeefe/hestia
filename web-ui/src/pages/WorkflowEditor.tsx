import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  type Connection,
  type Node,
  type Edge,
  type NodeChange,
  type EdgeChange,
} from 'reactflow';
import 'reactflow/dist/style.css';
import {
  fetchWorkflow,
  fetchWorkflowVersions,
  saveWorkflowVersion,
  activateWorkflowVersion,
  testRunWorkflow,
  updateWorkflow,
  fetchExecutions,
  fetchTools,
  fetchAuthStatus,
  type WorkflowVersion,
  type WorkflowNode,
  type WorkflowEdge,
  type ExecutionResult,
  type ExecutionRecord,
} from '../api/client';
import { nodeTypesMap } from '../components/workflow-editor/constants';
import EditorToolbar from '../components/workflow-editor/EditorToolbar';
import NodePropertiesPanel from '../components/workflow-editor/NodePropertiesPanel';
import TriggerConfigPanel from '../components/workflow-editor/TriggerConfigPanel';
import ExecutionHistoryPanel from '../components/workflow-editor/ExecutionHistoryPanel';
import VersionPanel from '../components/workflow-editor/VersionPanel';
import { useUndoRedo } from '../hooks/useUndoRedo';

export default function WorkflowEditor() {
  const { id } = useParams<{ id: string }>();
  const [workflowName, setWorkflowName] = useState('');
  const [versions, setVersions] = useState<WorkflowVersion[]>([]);
  const [activeVersionId, setActiveVersionId] = useState<string | null>(null);
  const [showVersions, setShowVersions] = useState(false);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<ExecutionResult | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [executions, setExecutions] = useState<ExecutionRecord[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [selectedExecution, setSelectedExecution] = useState<string | null>(null);
  const [addNodeType, setAddNodeType] = useState<string>('default');
  const [triggerType, setTriggerType] = useState<string>('manual');
  const [triggerConfig, setTriggerConfig] = useState<Record<string, string>>({});
  const [triggerSaving, setTriggerSaving] = useState(false);
  const [webhookUrl, setWebhookUrl] = useState('');
  const [webhookSecret, setWebhookSecret] = useState('');
  const [tools, setTools] = useState<string[]>([]);
  const [platforms, setPlatforms] = useState<string[]>([]);
  const [isDirty, setIsDirty] = useState(false);

  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  const selectedNodeRef = useRef(selectedNode);

  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);
  useEffect(() => {
    edgesRef.current = edges;
  }, [edges]);
  useEffect(() => {
    selectedNodeRef.current = selectedNode;
  }, [selectedNode]);

  const getCurrentGraph = useCallback(() => ({ nodes: nodesRef.current, edges: edgesRef.current }), []);
  const { push, undo, redo, canUndo, canRedo } = useUndoRedo(getCurrentGraph);

  const pushCurrent = useCallback(() => {
    push();
    setIsDirty(true);
  }, [push]);

  const handleUndo = useCallback(() => {
    const state = undo();
    if (state) {
      setNodes(state.nodes);
      setEdges(state.edges);
      setSelectedNode(null);
    }
  }, [undo]);

  const handleRedo = useCallback(() => {
    const state = redo();
    if (state) {
      setNodes(state.nodes);
      setEdges(state.edges);
      setSelectedNode(null);
    }
  }, [redo]);

  const loadExecutions = useCallback(async () => {
    if (!id) return;
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const data = await fetchExecutions(id);
      setExecutions(data.executions);
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : 'Failed to load history');
    } finally {
      setHistoryLoading(false);
    }
  }, [id]);

  useEffect(() => {
    if (!id) return;

    Promise.all([fetchWorkflow(id), fetchWorkflowVersions(id)])
      .then(([wf, vs]) => {
        setWorkflowName(wf.name);
        setTriggerType(wf.trigger_type || 'manual');
        setTriggerConfig((wf.trigger_config || {}) as Record<string, string>);
        if (wf.trigger_type === 'webhook') {
          setWebhookUrl(wf.webhook_url || '');
          setWebhookSecret(wf.secret || '');
        }
        setVersions(vs.versions);
        const active = vs.versions.find((v: WorkflowVersion) => v.activated_at !== null);
        if (active) {
          setActiveVersionId(active.id);
          setNodes(active.nodes.map((n: WorkflowNode) => ({ ...n, data: n.data || {} })));
          setEdges(active.edges.map((e: WorkflowEdge) => ({ ...e })));
        }
        setLoading(false);
      })
      .catch((err: Error) => {
        setError(err.message);
        setLoading(false);
      });

    fetchTools()
      .then((data) => setTools(data.tools || []))
      .catch(() => setTools([]));

    fetchAuthStatus()
      .then((data) => setPlatforms(data.available_platforms || []))
      .catch(() => setPlatforms([]));

    loadExecutions();
  }, [id, loadExecutions]);

  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isDirty]);

  const handleSaveRef = useRef<() => Promise<void>>(async () => {});

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
        sourceHandle: e.sourceHandle ?? undefined,
        targetHandle: e.targetHandle ?? undefined,
      }));
      const version = await saveWorkflowVersion(id, serialNodes, serialEdges);
      setVersions((vs) => [...vs, version]);
      setIsDirty(false);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  handleSaveRef.current = handleSave;

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
        return;
      }

      if ((e.key === 'z' || e.key === 'Z') && (e.ctrlKey || e.metaKey) && e.shiftKey) {
        e.preventDefault();
        handleRedo();
        return;
      }
      if ((e.key === 'z' || e.key === 'Z') && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        handleUndo();
        return;
      }
      if ((e.key === 'y' || e.key === 'Y') && e.ctrlKey) {
        e.preventDefault();
        handleRedo();
        return;
      }
      if ((e.key === 's' || e.key === 'S') && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        handleSaveRef.current();
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setSelectedNode(null);
        return;
      }
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedNodeRef.current) {
        e.preventDefault();
        const nodeId = selectedNodeRef.current.id;
        pushCurrent();
        setNodes((nds: Node[]) => nds.filter((n) => n.id !== nodeId));
        setEdges((eds: Edge[]) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
        setSelectedNode(null);
      }
    };

    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [handleUndo, handleRedo, pushCurrent]);

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const hasStructural = changes.some((c: NodeChange) => c.type === 'remove' || c.type === 'add');
      if (hasStructural) {
        pushCurrent();
      }
      setNodes((nds: Node[]) => applyNodeChanges(changes, nds));
    },
    [pushCurrent]
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      const hasStructural = changes.some((c: EdgeChange) => c.type === 'remove' || c.type === 'add');
      if (hasStructural) {
        pushCurrent();
      }
      setEdges((eds: Edge[]) => applyEdgeChanges(changes, eds));
    },
    [pushCurrent]
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      pushCurrent();
      setEdges((eds: Edge[]) => addEdge(connection, eds));
    },
    [pushCurrent]
  );

  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    setSelectedNode(node);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
  }, []);

  const onNodesDelete = useCallback(
    (deletedNodes: Node[]) => {
      if (selectedNodeRef.current && deletedNodes.find((n: Node) => n.id === selectedNodeRef.current?.id)) {
        setSelectedNode(null);
      }
    },
    []
  );

  const onNodeDragStop = useCallback(() => {
    pushCurrent();
  }, [pushCurrent]);

  const handleAddNode = () => {
    pushCurrent();
    setIsDirty(true);
    const lastNode = nodes.length > 0
      ? nodes.reduce((prev, curr) => (curr.position.y > prev.position.y ? curr : prev), nodes[0])
      : null;
    const newNode: Node = {
      id: `node_${Date.now()}`,
      type: addNodeType,
      position: {
        x: lastNode ? lastNode.position.x : 250,
        y: lastNode ? lastNode.position.y + 100 : 100,
      },
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
            return { label: 'Investigate', topic: '', depth: 'shallow', tools: [] };
          default:
            return { label: 'New Node' };
        }
      })(),
    };
    pushCurrent();
    setNodes((nds: Node[]) => [...nds, newNode]);
  };

  const handleSaveAndActivate = async () => {
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
      await activateWorkflowVersion(id, version.id);
      setActiveVersionId(version.id);
      setVersions((vs) =>
        vs.map((v) =>
          v.id === version.id ? { ...v, activated_at: new Date().toISOString() } : { ...v, activated_at: null }
        )
      );
      setIsDirty(false);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleActivate = async () => {
    if (!id || !activeVersionId) return;
    if (!window.confirm('Activate this version? It will become the live version used by triggers.')) {
      return;
    }
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
    if (!window.confirm('Run this workflow now? LLM nodes will make real API calls and send_message nodes will deliver messages.')) {
      return;
    }
    setTesting(true);
    setTestResult(null);
    setTestError(null);
    try {
      const result = await testRunWorkflow(id);
      setTestResult(result);
      setError(null);
      await loadExecutions();
    } catch (err) {
      setTestError(err instanceof Error ? err.message : 'Test run failed');
      setError(err instanceof Error ? err.message : 'Test run failed');
    } finally {
      setTesting(false);
    }
  };

  const handleTriggerSave = async () => {
    if (!id) return;
    setTriggerSaving(true);
    try {
      await updateWorkflow(id, { trigger_type: triggerType, trigger_config: triggerConfig });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save trigger');
    } finally {
      setTriggerSaving(false);
    }
  };

  const updateTriggerConfig = (key: string, value: string) => {
    setTriggerConfig((prev) => ({ ...prev, [key]: value }));
  };

  const updateSelectedNodeData = (key: string, value: unknown) => {
    if (!selectedNode) return;
    pushCurrent();
    setNodes((nds: Node[]) =>
      nds.map((n) => (n.id === selectedNode.id ? { ...n, data: { ...n.data, [key]: value } } : n))
    );
    setSelectedNode((prev) => (prev ? { ...prev, data: { ...prev.data, [key]: value } } : prev));
  };

  const handleChangeNodeType = (type: string) => {
    if (!selectedNode) return;
    pushCurrent();
    setNodes((nds: Node[]) => nds.map((n) => (n.id === selectedNode.id ? { ...n, type } : n)));
    setSelectedNode((prev) => (prev ? { ...prev, type } : prev));
  };

  const handleDeleteNode = (nodeId: string) => {
    pushCurrent();
    setNodes((nds: Node[]) => nds.filter((n) => n.id !== nodeId));
    setEdges((eds: Edge[]) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
    setSelectedNode(null);
  };

  const handleViewVersion = (version: WorkflowVersion) => {
    pushCurrent();
    setNodes(version.nodes.map((n: WorkflowNode) => ({ ...n, data: n.data || {} })));
    setEdges(version.edges.map((e: WorkflowEdge) => ({ ...e })));
    setIsDirty(true);
  };

  const handleActivateVersion = async (versionId: string) => {
    if (!id) return;
    if (!window.confirm('Activate this version? It will become the live version used by triggers.')) {
      return;
    }
    try {
      await activateWorkflowVersion(id, versionId);
      setActiveVersionId(versionId);
      setVersions((vs) =>
        vs.map((v) =>
          v.id === versionId ? { ...v, activated_at: new Date().toISOString() } : { ...v, activated_at: null }
        )
      );
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Activation failed');
    }
  };

  const handleNameBlur = async () => {
    if (!id) return;
    try {
      await updateWorkflow(id, { name: workflowName });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to rename workflow');
    }
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
      <div style={{ padding: '0.25rem 1rem', fontSize: '0.875rem', color: '#666', borderBottom: '1px solid #eee' }}>
        <Link to="/workflows" style={{ color: '#2563eb', textDecoration: 'none' }}>Workflows</Link>
        {' > '}
        <span>{workflowName}</span>
      </div>
      <EditorToolbar
        workflowName={workflowName}
        isDirty={isDirty}
        onNameChange={setWorkflowName}
        onNameBlur={handleNameBlur}
        addNodeType={addNodeType}
        onAddNodeTypeChange={setAddNodeType}
        onAddNode={handleAddNode}
        onSave={handleSave}
        onSaveAndActivate={handleSaveAndActivate}
        onActivate={handleActivate}
        onTestRun={handleTestRun}
        onToggleHistory={() => setShowHistory((s) => !s)}
        onToggleVersions={() => setShowVersions((s) => !s)}
        showHistory={showHistory}
        showVersions={showVersions}
        saving={saving}
        testing={testing}
        activeVersionId={activeVersionId}
        error={error}
        testError={testError}
        canUndo={canUndo}
        canRedo={canRedo}
        onUndo={handleUndo}
        onRedo={handleRedo}
      />
      {showVersions && (
        <VersionPanel
          versions={versions}
          activeVersionId={activeVersionId}
          onView={handleViewVersion}
          onActivate={handleActivateVersion}
        />
      )}
      <ExecutionHistoryPanel
        show={showHistory}
        executions={executions}
        loading={historyLoading}
        error={historyError}
        selectedExecution={selectedExecution}
        onSelectExecution={setSelectedExecution}
        testResult={testResult}
        testError={testError}
        nodes={nodes}
      />
      <TriggerConfigPanel
        triggerType={triggerType}
        onTriggerTypeChange={(type: string) => {
          setTriggerType(type);
          setTriggerConfig({});
        }}
        triggerConfig={triggerConfig}
        onTriggerConfigChange={updateTriggerConfig}
        onSaveTrigger={handleTriggerSave}
        triggerSaving={triggerSaving}
        workflowId={id}
        webhookUrl={webhookUrl}
        webhookSecret={webhookSecret}
      />
      <div style={{ display: 'flex', flex: 1 }}>
        <div style={{ flex: 1 }} tabIndex={0} data-testid="reactflow-wrapper">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            onNodesDelete={onNodesDelete}
            onNodeDragStop={onNodeDragStop}
            nodeTypes={nodeTypesMap}
            fitView
          >
            <Background />
            <Controls />
            <MiniMap />
          </ReactFlow>
        </div>
        {selectedNode && (
          <NodePropertiesPanel
            selectedNode={selectedNode}
            nodes={nodes}
            edges={edges}
            onDeleteNode={handleDeleteNode}
            onUpdateNodeData={updateSelectedNodeData}
            onChangeNodeType={handleChangeNodeType}
            tools={tools}
            platforms={platforms}
          />
        )}
      </div>
    </div>
  );
}
