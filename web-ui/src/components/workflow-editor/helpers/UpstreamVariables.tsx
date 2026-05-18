import type { Node, Edge } from 'reactflow';
import { TEXT } from '../../../lib/text';
import './UpstreamVariables.css';

interface UpstreamVariablesProps {
  nodeId: string;
  nodes: Node[];
  edges: Edge[];
}

export default function UpstreamVariables({ nodeId, nodes, edges }: UpstreamVariablesProps) {
  const upstream = edges
    .filter((e) => e.target === nodeId)
    .map((e) => nodes.find((n) => n.id === e.source))
    .filter(Boolean) as Node[];

  if (upstream.length === 0) return null;

  return (
    <div className="upstream-variables">
      {TEXT.workflowEditor.availableLabel}{' '}
      {upstream.map((n) => (
        <code key={n.id} className="upstream-variables__code">
          {TEXT.workflowEditor.upstreamVariable(n.id)}
        </code>
      ))}
    </div>
  );
}
