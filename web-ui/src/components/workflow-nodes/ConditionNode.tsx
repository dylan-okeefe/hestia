import { Handle, Position, type NodeProps } from 'reactflow';
import './workflow-nodes.css';

export default function ConditionNode({ data }: NodeProps) {
  const label = (data.label as string) || 'Condition';
  const expression = (data.expression as string) || '';
  const snippet = expression.length > 24 ? expression.slice(0, 24) + '…' : expression;

  return (
    <div
      data-testid="workflow-node"
      data-node-type="condition"
      className="workflow-node workflow-node--condition"
    >
      <Handle type="target" position={Position.Top} className="workflow-node__handle" />
      <div className="workflow-node__label">{label}</div>
      <div className="workflow-node__snippet">🔀 {snippet || '—'}</div>
      <Handle
        type="source"
        position={Position.Bottom}
        id="true"
        className="workflow-node__handle--true" style={{ left: '30%' }}
      />
      <span
        className="workflow-node__handle-label" style={{ left: '30%' }}
      >
        true
      </span>
      <Handle
        type="source"
        position={Position.Bottom}
        id="false"
        className="workflow-node__handle--false" style={{ left: '70%' }}
      />
      <span
        className="workflow-node__handle-label" style={{ left: '70%' }}
      >
        false
      </span>
    </div>
  );
}
