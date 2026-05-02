import { Handle, Position, type NodeProps } from 'reactflow';

export default function HttpRequestNode({ data }: NodeProps) {
  const label = (data.label as string) || 'HTTP Request';
  const method = (data.method as string) || 'GET';
  const url = (data.url as string) || '';
  let host = '—';
  try {
    if (url) host = new URL(url).host;
  } catch {
    host = url;
  }

  return (
    <div
      data-testid="workflow-node"
      data-node-type="http_request"
      style={{
        background: '#ffedd5',
        border: '1px solid #fdba74',
        borderRadius: 8,
        padding: '0.5rem 0.75rem',
        minWidth: 140,
        fontSize: '0.875rem',
        color: '#7c2d12',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: '#555' }} />
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: '0.75rem' }}>
        🌐 {method} {host}
      </div>
      <Handle type="source" position={Position.Bottom} style={{ background: '#555' }} />
    </div>
  );
}
