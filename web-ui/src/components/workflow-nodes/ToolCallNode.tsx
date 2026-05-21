import { Handle, Position, type NodeProps } from 'reactflow';
import './workflow-nodes.css';

export default function ToolCallNode({ data }: NodeProps) {
  const label = (data.label as string) || 'Tool Call';
  const toolName = (data.tool_name as string) || '—';

  return (
    <div
      data-testid="workflow-node"
      data-node-type="tool_call"
      className="workflow-node workflow-node--tool_call"
    >
      <Handle type="target" position={Position.Top} className="workflow-node__handle" />
      <div className="workflow-node__label">{label}</div>
      <div className="workflow-node__snippet">🔧 {toolName}</div>
      <Handle type="source" position={Position.Bottom} className="workflow-node__handle" />
    </div>
  );
}
