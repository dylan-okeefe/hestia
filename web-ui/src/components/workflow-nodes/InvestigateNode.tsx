import { Handle, Position, type NodeProps } from 'reactflow';
import './workflow-nodes.css';

export default function InvestigateNode({ data }: NodeProps) {
  const label = (data.label as string) || 'Investigate';
  const topic = (data.topic as string) || '';
  const snippet = topic.length > 24 ? topic.slice(0, 24) + '…' : topic;

  return (
    <div
      data-testid="workflow-node"
      data-node-type="investigate"
      className="workflow-node workflow-node--investigate"
    >
      <Handle type="target" position={Position.Top} className="workflow-node__handle" />
      <div className="workflow-node__label">{label}</div>
      <div className="workflow-node__snippet">🔍 {snippet || '—'}</div>
      <Handle type="source" position={Position.Bottom} className="workflow-node__handle" />
    </div>
  );
}
