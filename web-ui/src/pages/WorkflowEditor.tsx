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
  type ReactFlowInstance,
} from 'reactflow';
import 'reactflow/dist/style.css';
import '@reactflow/node-resizer/dist/style.css';
import { nodeTypesMap } from '../components/workflow-editor/constants';
import EditorToolbar from '../components/workflow-editor/EditorToolbar';
import NodePropertiesPanel from '../components/workflow-editor/NodePropertiesPanel';
import TriggerConfigPanel from '../components/workflow-editor/TriggerConfigPanel';
import ExecutionHistoryPanel from '../components/workflow-editor/ExecutionHistoryPanel';
import VersionPanel from '../components/workflow-editor/VersionPanel';
import { useWorkflowEditor } from '../hooks/useWorkflowEditor';
import ErrorState from '../components/layout/ErrorState';
import './WorkflowEditor.css';

function computeNodePosition(
  existingNodes: Node[],
  selectedNode: Node | null,
  canvasWidth: number,
  canvasHeight: number,
  viewport: { x: number; y: number; zoom: number }
): { x: number; y: number } {
  const GRID_X = 180;
  const GRID_Y = 80;

  const centerX = (canvasWidth / 2 - viewport.x) / viewport.zoom;
  const centerY = (canvasHeight / 2 - viewport.y) / viewport.zoom;

  const baseX = selectedNode ? selectedNode.position.x + 150 : centerX - 75;
  const baseY = selectedNode ? selectedNode.position.y + 50 : centerY - 25;

  const occupied = new Set<string>();
  for (const n of existingNodes) {
    const gx = Math.round(n.position.x / GRID_X);
    const gy = Math.round(n.position.y / GRID_Y);
    occupied.add(`${gx},${gy}`);
  }

  const baseGx = Math.round(baseX / GRID_X);
  const baseGy = Math.round(baseY / GRID_Y);

  for (let r = 0; r < 20; r++) {
    for (let dx = -r; dx <= r; dx++) {
      for (let dy = -r; dy <= r; dy++) {
        if (Math.abs(dx) !== r && Math.abs(dy) !== r) continue;
        const gx = baseGx + dx;
        const gy = baseGy + dy;
        if (!occupied.has(`${gx},${gy}`)) {
          return { x: gx * GRID_X, y: gy * GRID_Y };
        }
      }
    }
  }

  return { x: baseX, y: baseY };
}

export default function WorkflowEditor() {
  const { id } = useParams<{ id: string }>();
  const editor = useWorkflowEditor(id);
  const selectedNodeRef = useRef(editor.selectedNode);
  selectedNodeRef.current = editor.selectedNode;
  const canvasContainerRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef({ x: 0, y: 0, zoom: 1 });
  const reactFlowInstanceRef = useRef<ReactFlowInstance | null>(null);

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const hasStructural = changes.some(
        (c: NodeChange) => c.type === 'remove' || c.type === 'add'
      );
      if (hasStructural) {
        editor.pushCurrent();
      }
      editor.setNodes((nds: Node[]) => {
        const updated = applyNodeChanges(changes, nds);
        // Persist dimension changes to node.data so they survive save/load
        return updated.map((n) => {
          const dimChange = changes.find(
            (c): c is NodeChange & { type: 'dimensions'; dimensions?: { width: number; height: number }; id: string } =>
              c.type === 'dimensions' && 'id' in c && c.id === n.id
          );
          if (dimChange?.dimensions && n.data) {
            return {
              ...n,
              data: {
                ...n.data,
                width: dimChange.dimensions.width,
                height: dimChange.dimensions.height,
              },
            };
          }
          return n;
        });
      });
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
      <div className="workflow-editor__loading">
        <p>Loading workflow…</p>
      </div>
    );
  }

  if (editor.error) {
    return (
      <div className="workflow-editor">
        <div className="workflow-editor__loading">
          <ErrorState message={editor.error} onRetry={() => window.location.reload()} />
        </div>
      </div>
    );
  }

  return (
    <div className="workflow-editor">
      <EditorToolbar
        workflowName={editor.workflowName}
        isDirty={editor.isDirty}
        onNameChange={editor.setWorkflowName}
        onNameBlur={editor.handleNameBlur}
        addNodeType={editor.addNodeType}
        onAddNodeTypeChange={editor.setAddNodeType}
        onAddNode={() => {
          const container = canvasContainerRef.current;
          const rect = container?.getBoundingClientRect();
          const pos = computeNodePosition(
            editor.nodes,
            editor.selectedNode,
            rect?.width ?? 800,
            rect?.height ?? 600,
            viewportRef.current
          );
          const newNode: Node = {
            id: `node_${Date.now()}`,
            type: editor.addNodeType,
            position: pos,
            data: (() => {
              switch (editor.addNodeType) {
                case 'tool_call':
                  return { label: 'Tool Call', tool_name: '', args: {} };
                case 'llm_decision':
                  return { label: 'LLM Decision', prompt: '', branches: ['yes', 'no'] };
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
          editor.setSelectedNode(newNode);
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
      <div className="workflow-editor__main">
        {editor.showVersions && (
          <VersionPanel
            versions={editor.versions}
            activeVersionId={editor.activeVersionId}
            onView={editor.handleViewVersion}
            onActivate={editor.handleActivateVersion}
          />
        )}
        <div ref={canvasContainerRef} className="workflow-canvas-container" tabIndex={0} data-testid="reactflow-wrapper">
          <div className="workflow-canvas">
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
            onInit={(instance: ReactFlowInstance) => {
              reactFlowInstanceRef.current = instance;
              viewportRef.current = instance.getViewport();
            }}
            onMoveEnd={(_event, viewport) => {
              viewportRef.current = viewport;
            }}
            nodeTypes={nodeTypesMap}
            fitView
          >
            <Background />
            <Controls />
            <MiniMap />
          </ReactFlow>
          </div>
        </div>
        {editor.selectedNode && (
          <>
            <div
              className="node-properties__drawer-backdrop"
              onClick={() => editor.setSelectedNode(null)}
              aria-hidden="true"
            />
            <NodePropertiesPanel
              selectedNode={editor.selectedNode}
              nodes={editor.nodes}
              edges={editor.edges}
              onDeleteNode={editor.handleDeleteNode}
              onUpdateNodeData={editor.updateSelectedNodeData}
              onChangeNodeType={editor.handleChangeNodeType}
              onClose={() => editor.setSelectedNode(null)}
              tools={editor.tools}
              toolSchemas={editor.toolSchemas}
              triggerType={editor.triggerType}
            />
          </>
        )}
      </div>
    </div>
  );
}
