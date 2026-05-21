import { Handle, Position, type NodeProps } from 'reactflow';
import './workflow-nodes.css';

export default function LLMDecisionNode({ data }: NodeProps) {
  const label = (data.label as string) || 'LLM Decision';
  const prompt = (data.prompt as string) || '';
  const snippet = prompt.length > 24 ? prompt.slice(0, 24) + '…' : prompt;
  const branches = ((data.branches as string[]) || []);

  return (
    <div
      data-testid="workflow-node"
      data-node-type="llm_decision"
      className="workflow-node workflow-node--llm_decision"
    >
      <Handle type="target" position={Position.Top} className="workflow-node__handle" />
      <div className="workflow-node__label">{label}</div>
      <div className="workflow-node__snippet">🧠 {snippet || '—'}</div>
      {branches.map((branch, index) => {
        const left = branches.length === 1 ? '50%' : `${((index + 1) / (branches.length + 1)) * 100}%`;
        return (
          <div key={branch} className="workflow-node__branch-container" style={{ left }}>
            <Handle
              type="source"
              position={Position.Bottom}
              id={branch}
              className="workflow-node__handle relative"
            />
            <span
              className="workflow-node__branch-label text-purple"
            >
              {branch}
            </span>
          </div>
        );
      })}
    </div>
  );
}
