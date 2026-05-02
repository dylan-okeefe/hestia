import { Handle, Position, type NodeProps } from 'reactflow';

export default function SendMessageNode({ data }: NodeProps) {
  const label = (data.label as string) || 'Send Message';
  const platform = (data.platform as string) || '—';
  const target = (data.target_user as string) || '';

  return (
    <div
      data-testid="workflow-node"
      data-node-type="send_message"
      style={{
        background: '#dcfce7',
        border: '1px solid #86efac',
        borderRadius: 8,
        padding: '0.5rem 0.75rem',
        minWidth: 140,
        fontSize: '0.875rem',
        color: '#14532d',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: '#555' }} />
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: '0.75rem' }}>
        💬 {platform}
        {target && ` → ${target}`}
      </div>
      <Handle type="source" position={Position.Bottom} style={{ background: '#555' }} />
    </div>
  );
}
