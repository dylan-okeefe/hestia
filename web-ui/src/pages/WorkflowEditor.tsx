import { useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
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
import { nodeTypesMap } from '../components/workflow-editor/constants';
import EditorToolbar from '../components/workflow-editor/EditorToolbar';
import NodePropertiesPanel from '../components/workflow-editor/NodePropertiesPanel';
import TriggerConfigPanel from '../components/workflow-editor/TriggerConfigPanel';
import ExecutionHistoryPanel from '../components/workflow-editor/ExecutionHistoryPanel';
import VersionPanel from '../components/workflow-editor/VersionPanel';
import { useWorkflowEditor } from '../hooks/useWorkflowEditor';

export default function WorkflowEditor() {
  const { id } = useParams<{ id: string }>();
  const editor = useWorkflowEditor(id);
  const selectedNodeRef = useRef(editor.selectedNode);
  selectedNodeRef.current = editor.selectedNode;

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const hasStructural = changes.some((c: NodeChange) => c.type === 'remove' || c.type === 'add');
      if (hasStructural) {
        editor.pushCurrent();
      }
      editor.setNodes((nds: Node[]) => applyNodeChanges(changes, nds));
    },
    [editor]
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      const hasStructural = changes.some((c: EdgeChange) => c.type === 'remove' || c.type === 'add');
      if (hasStructural) {
        editor.pushCurrent();
      }
      editor.setEdges((eds: Edge[]) => applyEdgeChanges(changes, eds));
    },
    [editor]
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      editor.pushCurrent();
      editor.setEdges((eds: Edge[]) => addEdge(connection, eds));
    },
    [editor]
  );

  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    editor.setSelectedNode(node);
  }, [editor]);

  const onPaneClick = useCallback(() => {
    editor.setSelectedNode(null);
  }, [editor]);

  const onNodesDelete = useCallback(
    (deletedNodes: Node[]) => {
      if (selectedNodeRef.current && deletedNodes.find((n: Node) => n.id === selectedNodeRef.current?.id)) {
        editor.setSelectedNode(null);
      }
    },
    [editor]
  );

  const onNodeDragStop = useCallback(() => {
    editor.pushCurrent();
  }, [editor]);

  if (editor.loading) {
    return (
      <div style={{ padding: '1rem' }}>
        <p>Loading workflow…</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 60px)' }}>
      <EditorToolbar
        workflowName={editor.workflowName}
        isDirty={editor.isDirty}
        onNameChange={editor.setWorkflowName}
        onNameBlur={editor.handleNameBlur}
        addNodeType={editor.addNodeType}
        onAddNodeTypeChange={editor.setAddNodeType}
        onAddNode={() => {
          const newNode: Node = {
            id: `node_${Date.now()}`,
            type: editor.addNodeType,
            position: { x: Math.random() * 200 + 50, y: Math.random() * 200 + 50 },
            data: (() => {
              switch (editor.addNodeType) {
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
          editor.pushCurrent();
          editor.setNodes((nds: Node[]) => [...nds, newNode]);
        }}
        onSave={editor.handleSave}
        onSaveAndActivate={editor.handleSaveAndActivate}
        onActivate={editor.handleActivate}
        onTestRun={editor.handleTestRun}
        onToggleHistory={() => editor.setShowHistory((s) => !s)}
        onToggleVersions={() => editor.setShowVersions((s) => !s)}
        showHistory={editor.showHistory}
        showVersions={editor.showVersions}
        saving={editor.saving}
        testing={editor.testing}
        activeVersionId={editor.activeVersionId}
        error={editor.error}
        testError={editor.testError}
        canUndo={editor.canUndo}
        canRedo={editor.canRedo}
        onUndo={editor.handleUndo}
        onRedo={editor.handleRedo}
      />
      {editor.showVersions && (
        <VersionPanel
          versions={editor.versions}
          activeVersionId={editor.activeVersionId}
          onView={editor.handleViewVersion}
          onActivate={editor.handleActivateVersion}
        />
      )}
      <ExecutionHistoryPanel
        show={editor.showHistory}
        executions={editor.executions}
        loading={editor.historyLoading}
        error={editor.historyError}
        selectedExecution={editor.selectedExecution}
        onSelectExecution={editor.setSelectedExecution}
        testResult={editor.testResult}
        testError={editor.testError}
        nodes={editor.nodes}
      />
      <TriggerConfigPanel
        triggerType={editor.triggerType}
        onTriggerTypeChange={(type: string) => {
          editor.setTriggerType(type);
          editor.setTriggerConfig({});
        }}
        triggerConfig={editor.triggerConfig}
        onTriggerConfigChange={editor.updateTriggerConfig}
        onSaveTrigger={editor.handleTriggerSave}
        triggerSaving={editor.triggerSaving}
        workflowId={id}
        webhookUrl={editor.webhookUrl}
        webhookSecret={editor.webhookSecret}
      />
      <div style={{ display: 'flex', flex: 1 }}>
        <div style={{ flex: 1 }} tabIndex={0} data-testid="reactflow-wrapper">
          <ReactFlow
            nodes={editor.nodes}
            edges={editor.edges}
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
        {editor.selectedNode && (
          <NodePropertiesPanel
            selectedNode={editor.selectedNode}
            nodes={editor.nodes}
            edges={editor.edges}
            onDeleteNode={editor.handleDeleteNode}
            onUpdateNodeData={editor.updateSelectedNodeData}
            onChangeNodeType={editor.handleChangeNodeType}
            tools={editor.tools}
            platforms={editor.platforms}
          />
        )}
      </div>
    </div>
  );
}
