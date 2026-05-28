import { Handle, Position, type NodeProps } from 'reactflow';
import { NodeResizer } from '@reactflow/node-resizer';
import './workflow-nodes.css';

export default function SendMessageNode({ data, selected }: NodeProps) {
  const label = (data.label as string) || 'Send Message';
  const platform = (data.platform as string) || '—';
  const target = (data.target_user as string) || '';

  return (
    <div
      data-testid="workflow-node"
      data-node-type="send_message"
      className="workflow-node workflow-node--send_message"
    >
      <NodeResizer
        isVisible={selected}
        minWidth={160}
        minHeight={60}
      />
      <Handle type="target" position={Position.Top} className="workflow-node__handle" />
      <div className="workflow-node__label">{label}</div>
      <div className="workflow-node__snippet">
        💬 {platform}
        {target && ` → ${target}`}
      </div>
      <Handle type="source" position={Position.Bottom} className="workflow-node__handle" />
    </div>
  );
}
