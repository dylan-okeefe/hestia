import { Handle, Position, type NodeProps } from 'reactflow';

export default function ConditionNode({ data }: NodeProps) {
  const label = (data.label as string) || 'Condition';
  const expression = (data.expression as string) || '';
  const snippet = expression.length > 24 ? expression.slice(0, 24) + '…' : expression;

  return (
    <div
      data-testid="workflow-node"
      data-node-type="condition"
      style={{
        background: '#fef9c3',
        border: '1px solid #fde047',
        borderRadius: 8,
        padding: '0.5rem 0.75rem',
        minWidth: 140,
        fontSize: '0.875rem',
        color: '#713f12',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: '#555' }} />
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: '0.75rem' }}>🔀 {snippet || '—'}</div>
      <Handle type="source" position={Position.Bottom} style={{ background: '#555' }} />
    </div>
  );
}
