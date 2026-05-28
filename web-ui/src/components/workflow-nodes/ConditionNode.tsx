import { Handle, Position, type NodeProps } from 'reactflow';
import { NodeResizer } from '@reactflow/node-resizer';
import './workflow-nodes.css';

export default function ConditionNode({ data, selected }: NodeProps) {
  const label = (data.label as string) || 'Condition';
  const expression = (data.expression as string) || '';

  return (
    <div
      data-testid="workflow-node"
      data-node-type="condition"
      className="workflow-node workflow-node--condition"
    >
      <NodeResizer
        isVisible={selected}
        minWidth={160}
        minHeight={60}
      />
      <Handle type="target" position={Position.Top} className="workflow-node__handle" />
      <div className="workflow-node__label">{label}</div>
      <div className="workflow-node__snippet">🔀 {expression || '—'}</div>
      <span
        className="workflow-node__handle-label"
        style={{ left: '30%' }}
      >
        true
      </span>
      <Handle
        type="source"
        position={Position.Bottom}
        id="true"
        className="workflow-node__handle--true"
        style={{ left: '30%' }}
      />
      <span
        className="workflow-node__handle-label"
        style={{ left: '70%' }}
      >
        false
      </span>
      <Handle
        type="source"
        position={Position.Bottom}
        id="false"
        className="workflow-node__handle--false"
        style={{ left: '70%' }}
      />
    </div>
  );
}
