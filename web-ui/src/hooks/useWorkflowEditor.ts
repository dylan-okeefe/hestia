import { useCallback, useEffect, useRef, useState } from 'react';
import type { Node, Edge } from 'reactflow';
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
import { useUndoRedo } from './useUndoRedo';

export function useWorkflowEditor(workflowId: string | undefined) {
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
    if (!workflowId) return;
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const data = await fetchExecutions(workflowId);
      setExecutions(data.executions);
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : 'Failed to load history');
    } finally {
      setHistoryLoading(false);
    }
  }, [workflowId]);

  useEffect(() => {
    if (!workflowId) return;

    Promise.all([fetchWorkflow(workflowId), fetchWorkflowVersions(workflowId)])
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
  }, [workflowId, loadExecutions]);

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
    if (!workflowId) return;
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
      const version = await saveWorkflowVersion(workflowId, serialNodes, serialEdges);
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

  const handleSaveAndActivate = async () => {
    if (!workflowId) return;
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
      const version = await saveWorkflowVersion(workflowId, serialNodes, serialEdges);
      setVersions((vs) => [...vs, version]);
      await activateWorkflowVersion(workflowId, version.id);
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
    if (!workflowId || !activeVersionId) return;
    if (!window.confirm('Activate this version? It will become the live version used by triggers.')) {
      return;
    }
    try {
      await activateWorkflowVersion(workflowId, activeVersionId);
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
    if (!workflowId) return;
    if (!window.confirm('Run this workflow now? LLM nodes will make real API calls and send_message nodes will deliver messages.')) {
      return;
    }
    setTesting(true);
    setTestResult(null);
    setTestError(null);
    try {
      const result = await testRunWorkflow(workflowId);
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
    if (!workflowId) return;
    setTriggerSaving(true);
    try {
      await updateWorkflow(workflowId, { trigger_type: triggerType, trigger_config: triggerConfig });
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
    if (!workflowId) return;
    if (!window.confirm('Activate this version? It will become the live version used by triggers.')) {
      return;
    }
    try {
      await activateWorkflowVersion(workflowId, versionId);
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
    if (!workflowId) return;
    try {
      await updateWorkflow(workflowId, { name: workflowName });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to rename workflow');
    }
  };

  return {
    workflowName,
    setWorkflowName,
    versions,
    activeVersionId,
    showVersions,
    setShowVersions,
    nodes,
    setNodes,
    edges,
    setEdges,
    selectedNode,
    setSelectedNode,
    loading,
    error,
    saving,
    testing,
    testResult,
    testError,
    showHistory,
    setShowHistory,
    executions,
    historyLoading,
    historyError,
    selectedExecution,
    setSelectedExecution,
    addNodeType,
    setAddNodeType,
    triggerType,
    setTriggerType,
    triggerConfig,
    setTriggerConfig,
    triggerSaving,
    webhookUrl,
    webhookSecret,
    tools,
    platforms,
    isDirty,
    canUndo,
    canRedo,
    handleUndo,
    handleRedo,
    pushCurrent,
    loadExecutions,
    handleSave,
    handleSaveAndActivate,
    handleActivate,
    handleTestRun,
    handleTriggerSave,
    updateTriggerConfig,
    updateSelectedNodeData,
    handleChangeNodeType,
    handleDeleteNode,
    handleViewVersion,
    handleActivateVersion,
    handleNameBlur,
  };
}
