import { Handle, Position, type NodeProps } from 'reactflow';
import { NodeResizer } from '@reactflow/node-resizer';
import './workflow-nodes.css';

export default function InvestigateNode({ data, selected }: NodeProps) {
  const label = (data.label as string) || 'Investigate';
  const topic = (data.topic as string) || '';

  return (
    <div
      data-testid="workflow-node"
      data-node-type="investigate"
      className="workflow-node workflow-node--investigate"
    >
      <NodeResizer
        isVisible={selected}
        minWidth={160}
        minHeight={60}
      />
      <Handle type="target" position={Position.Top} className="workflow-node__handle" />
      <div className="workflow-node__label">{label}</div>
      <div className="workflow-node__snippet">🔍 {topic || '—'}</div>
      <Handle type="source" position={Position.Bottom} className="workflow-node__handle" />
    </div>
  );
}
