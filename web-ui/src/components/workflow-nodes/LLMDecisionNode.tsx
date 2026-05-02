import { Handle, Position, type NodeProps } from 'reactflow';

export default function LLMDecisionNode({ data }: NodeProps) {
  const label = (data.label as string) || 'LLM Decision';
  const prompt = (data.prompt as string) || '';
  const snippet = prompt.length > 24 ? prompt.slice(0, 24) + '…' : prompt;
  const branches = ((data.branches as string[]) || []);

  return (
    <div
      data-testid="workflow-node"
      data-node-type="llm_decision"
      style={{
        background: '#f3e8ff',
        border: '1px solid #d8b4fe',
        borderRadius: 8,
        padding: '0.5rem 0.75rem',
        minWidth: 140,
        fontSize: '0.875rem',
        color: '#581c87',
        position: 'relative',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: '#555' }} />
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: '0.75rem' }}>🧠 {snippet || '—'}</div>
      {branches.map((branch, index) => {
        const left = branches.length === 1 ? '50%' : `${((index + 1) / (branches.length + 1)) * 100}%`;
        return (
          <div key={branch} style={{ position: 'absolute', bottom: 0, left, transform: 'translateX(-50%)' }}>
            <Handle
              type="source"
              position={Position.Bottom}
              id={branch}
              style={{ background: '#555', position: 'relative' }}
            />
            <span
              style={{
                display: 'block',
                textAlign: 'center',
                fontSize: '0.65rem',
                color: '#581c87',
                marginTop: 2,
                whiteSpace: 'nowrap',
              }}
            >
              {branch}
            </span>
          </div>
        );
      })}
    </div>
  );
}
