import { Handle, Position, type NodeProps } from 'reactflow';
import { NodeResizer } from '@reactflow/node-resizer';
import './workflow-nodes.css';

export default function LLMDecisionNode({ data, selected }: NodeProps) {
  const label = (data.label as string) || 'LLM Decision';
  const prompt = (data.prompt as string) || '';
  const branches = ((data.branches as string[]) || []);

  return (
    <div
      data-testid="workflow-node"
      data-node-type="llm_decision"
      className="workflow-node workflow-node--llm_decision"
    >
      <NodeResizer
        isVisible={selected}
        minWidth={180}
        minHeight={80}
      />
      <Handle type="target" position={Position.Top} className="workflow-node__handle" />
      <div className="workflow-node__label">{label}</div>
      <div className="workflow-node__snippet">🧠 {prompt || '—'}</div>
      {branches.length === 0 && (
        <div className="workflow-node__branch-container" style={{ left: '50%' }}>
          <span className="workflow-node__branch-label text-purple">out</span>
          <Handle
            type="source"
            position={Position.Bottom}
            id="out"
            className="workflow-node__handle"
          />
        </div>
      )}
      {branches.map((branch, index) => {
        const left = branches.length === 1 ? '50%' : `${((index + 1) / (branches.length + 1)) * 100}%`;
        return (
          <div key={branch} className="workflow-node__branch-container" style={{ left }}>
            <span className="workflow-node__branch-label text-purple" title={branch}>
              {branch}
            </span>
            <Handle
              type="source"
              position={Position.Bottom}
              id={branch}
              className="workflow-node__handle"
            />
          </div>
        );
      })}
    </div>
  );
}
