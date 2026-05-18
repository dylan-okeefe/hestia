import type { Node, Edge } from 'reactflow';
import { TEXT } from '../../../lib/text';
import './InsertVariableDropdown.css';

const TRIGGER_VARIABLES: Record<string, string[]> = {
  manual: [],
  schedule: ['triggered_at'],
  chat_command: ['command', 'args', 'user_id', 'platform', 'platform_user'],
  message: ['text', 'user_id', 'platform', 'platform_user'],
  webhook: ['body', 'headers', 'query_params'],
  email: ['from_address', 'subject', 'body'],
  proposal_approved: ['proposal_id', 'proposal_type', 'user_id'],
  proposal_rejected: ['proposal_id', 'proposal_type', 'user_id', 'reason'],
  tool_error: ['tool_name', 'error_message', 'args'],
  workflow_completed: ['source_workflow_id', 'outputs'],
  session_started: ['user_id', 'platform', 'platform_user'],
};

interface InsertVariableDropdownProps {
  triggerType: string;
  nodeId: string;
  nodes: Node[];
  edges: Edge[];
  onInsert: (variable: string) => void;
}

export default function InsertVariableDropdown({
  triggerType,
  nodeId,
  nodes,
  edges,
  onInsert,
}: InsertVariableDropdownProps) {
  const upstream = edges
    .filter((e) => e.target === nodeId)
    .map((e) => nodes.find((n) => n.id === e.source))
    .filter(Boolean) as Node[];

  const triggerVars = TRIGGER_VARIABLES[triggerType] || [];
  if (triggerVars.length === 0 && upstream.length === 0) return null;

  return (
    <select
      className="insert-variable-dropdown"
      value=""
      onChange={(e) => {
        if (e.target.value) {
          onInsert(e.target.value);
          e.target.value = '';
        }
      }}
      aria-label="Insert variable"
    >
      <option value="">{TEXT.workflowEditor.insertVariablePlaceholder}</option>
      {triggerVars.map((v) => (
        <option key={`trigger_${v}`} value={v}>
          {TEXT.workflowEditor.triggerVariable(v)}
        </option>
      ))}
      {upstream.map((n) => (
        <option key={`upstream_${n.id}`} value={`${n.id}.output`}>
          {TEXT.workflowEditor.upstreamVariable(n.id)}
        </option>
      ))}
    </select>
  );
}
