import { Handle, Position, type NodeProps } from 'reactflow';

export default function InvestigateNode({ data }: NodeProps) {
  const label = (data.label as string) || 'Investigate';
  const topic = (data.topic as string) || '';
  const snippet = topic.length > 24 ? topic.slice(0, 24) + '…' : topic;

  return (
    <div
      data-testid="workflow-node"
      data-node-type="investigate"
      style={{
        background: '#fee2e2',
        border: '1px solid #fca5a5',
        borderRadius: 8,
        padding: '0.5rem 0.75rem',
        minWidth: 140,
        fontSize: '0.875rem',
        color: '#7f1d1d',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: '#555' }} />
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: '0.75rem' }}>🔍 {snippet || '—'}</div>
      <Handle type="source" position={Position.Bottom} style={{ background: '#555' }} />
    </div>
  );
}
