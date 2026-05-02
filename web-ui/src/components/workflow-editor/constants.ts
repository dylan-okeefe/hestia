import {
  ToolCallNode,
  LLMDecisionNode,
  SendMessageNode,
  HttpRequestNode,
  ConditionNode,
  InvestigateNode,
} from '../workflow-nodes';

export const EDITOR_NODE_TYPES = [
  'default',
  'tool_call',
  'llm_decision',
  'send_message',
  'http_request',
  'condition',
  'investigate',
] as const;

export const nodeTypesMap = {
  tool_call: ToolCallNode,
  llm_decision: LLMDecisionNode,
  send_message: SendMessageNode,
  http_request: HttpRequestNode,
  condition: ConditionNode,
  investigate: InvestigateNode,
};
