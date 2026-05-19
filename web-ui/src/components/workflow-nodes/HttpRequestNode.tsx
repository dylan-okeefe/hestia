import { Handle, Position, type NodeProps } from 'reactflow';
import './workflow-nodes.css';

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
      className="workflow-node workflow-node--http_request"
    >
      <Handle type="target" position={Position.Top} className="workflow-node__handle" />
      <div className="workflow-node__label">{label}</div>
      <div className="workflow-node__snippet">
        🌐 {method} {host}
      </div>
      <Handle type="source" position={Position.Bottom} className="workflow-node__handle" />
    </div>
  );
}
