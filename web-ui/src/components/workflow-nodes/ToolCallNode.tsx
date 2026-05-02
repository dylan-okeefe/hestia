import { Handle, Position, type NodeProps } from 'reactflow';

export default function ToolCallNode({ data }: NodeProps) {
  const label = (data.label as string) || 'Tool Call';
  const toolName = (data.tool_name as string) || '—';

  return (
    <div
      data-testid="workflow-node"
      data-node-type="tool_call"
      style={{
        background: '#dbeafe',
        border: '1px solid #93c5fd',
        borderRadius: 8,
        padding: '0.5rem 0.75rem',
        minWidth: 140,
        fontSize: '0.875rem',
        color: '#1e3a8a',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: '#555' }} />
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: '0.75rem' }}>🔧 {toolName}</div>
      <Handle type="source" position={Position.Bottom} style={{ background: '#555' }} />
    </div>
  );
}
