export const TRIGGER_LABELS: Record<string, string> = {
  manual: 'Manual',
  schedule: 'Scheduled',
  chat_command: 'Chat Command',
  webhook: 'Webhook',
  message: 'Message',
  email: 'Email',
  proposal_approved: 'Proposal Approved',
  proposal_rejected: 'Proposal Rejected',
  tool_error: 'Tool Error',
  workflow_completed: 'Workflow Completed',
  session_started: 'Session Started',
};

export const NODE_TYPE_LABELS: Record<string, string> = {
  tool_call: 'Tool Call',
  llm_decision: 'LLM Decision',
  send_message: 'Send Message',
  http_request: 'HTTP Request',
  condition: 'Condition',
  investigate: 'Investigate',
  inference: 'Inference',
};

export const HEALTH_CHECK_LABELS: Record<string, string> = {
  python_version: 'Python Version',
  dependencies_in_sync: 'Dependencies in Sync',
  config_file_loads: 'Config File Loads',
  config_schema: 'Config Schema',
  allowed_roots_cwd: 'Allowed Roots CWD',
  sqlite_dbs_readable: 'SQLite Databases Readable',
  llamacpp_reachable: 'llama.cpp Reachable',
  platform_prereqs: 'Platform Prerequisites',
  voice_prerequisites: 'Voice Prerequisites',
  trust_preset_resolves: 'Trust Preset Resolves',
  trust_preset_safe: 'Trust Preset Safe for Production',
  memory_epoch: 'Memory Epoch',
};

export const ROLE_LABELS: Record<string, string> = {
  admin: 'Administrator',
  trusted: 'Trusted User',
  user: 'User',
  child: 'Child',
};

export const TRUST_PRESET_LABELS: Record<string, string> = {
  paranoid: 'Paranoid',
  prompt_on_mobile: 'Prompt on Mobile',
  household: 'Household',
  developer: 'Developer',
};

export function label(map: Record<string, string>, key: string): string {
  return map[key] ?? key;
}
