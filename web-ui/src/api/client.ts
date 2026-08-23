const API_BASE = '/api';

let _authToken: string | null = sessionStorage.getItem('hestia_auth_token');

export function setAuthToken(token: string | null) {
  _authToken = token;
  if (token) {
    sessionStorage.setItem('hestia_auth_token', token);
  } else {
    sessionStorage.removeItem('hestia_auth_token');
  }
}

export function getAuthToken(): string | null {
  return _authToken;
}

export function clearAuthToken() {
  _authToken = null;
  sessionStorage.removeItem('hestia_auth_token');
}

function getHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  if (_authToken) {
    headers['Authorization'] = `Bearer ${_authToken}`;
  }
  return headers;
}

async function checkOk(res: Response): Promise<Response> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res;
}

async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30000);

  const signal = init?.signal;
  if (signal) {
    signal.addEventListener('abort', () => controller.abort(), { once: true });
  }

  try {
    const res = await fetch(input, {
      ...init,
      signal: controller.signal,
      headers: getHeaders((init?.headers as Record<string, string>) || {}),
    });
    if (res.status === 401) {
      // BUG-055: 401 on an auth-status probe may be a transient gateway
      // response; only a confirmed 401 from a data endpoint logs the user
      // out. fetchAuthStatus handles its own failure path with retries.
      const isAuthProbe = input.includes('/auth/status');
      if (!isAuthProbe) {
        clearAuthToken();
        window.dispatchEvent(new CustomEvent('auth:unauthorized'));
      }
    }
    return res;
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function fetchAuthStatus() {
  // BUG-055: retry transient status-check failures so a network blip does
  // not kick an authenticated user back to Login.
  let lastError: unknown;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const res = await apiFetch(`${API_BASE}/auth/status`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json() as Promise<{ auth_enabled: boolean; authenticated: boolean; debug_login?: boolean; platform?: string; platform_user?: string; user_id?: string; available_platforms?: string[] }>;
    } catch (err) {
      lastError = err;
      await new Promise((resolve) => setTimeout(resolve, 400 * (attempt + 1)));
    }
  }
  throw lastError instanceof Error ? lastError : new Error('Failed to fetch auth status');
}

export async function fetchAvailableUsers() {
  const res = await apiFetch(`${API_BASE}/auth/available-users`);
  if (!res.ok) throw new Error('Failed to fetch available users');
  return res.json() as Promise<{ users: Array<{ user_id: string; display_name: string; platforms: string[] }> }>;
}

export async function requestCode(platform: string, userId?: string) {
  // SEC-002: the picker sends user_id; the server resolves the recipient
  // from that user's registered identity (raw chat ids are never sent).
  const body: Record<string, string> = { platform };
  if (userId) body.user_id = userId;
  const res = await apiFetch(`${API_BASE}/auth/request-code`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to request code');
  return res.json();
}

export async function verifyCode(code: string) {
  const res = await apiFetch(`${API_BASE}/auth/verify-code`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  });
  if (!res.ok) throw new Error('Invalid or expired code');
  return res.json();
}

export async function logout() {
  const res = await apiFetch(`${API_BASE}/auth/logout`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to logout');
  return res.json();
}

export async function debugLogin(userId: string): Promise<{ token: string; platform: string; platform_user: string; expires_at: string }> {
  const res = await apiFetch(`${API_BASE}/auth/debug-login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId }),
  });
  if (!res.ok) throw new Error('Debug login failed');
  return res.json();
}

export async function fetchProposals(status = 'pending') {
  const qs = status ? `?status=${status}` : '';
  const res = await apiFetch(`${API_BASE}/proposals${qs}`);
  if (!res.ok) throw new Error('Failed to fetch proposals');
  return res.json();
}

export async function acceptProposal(id: string, note?: string) {
  const res = await apiFetch(`${API_BASE}/proposals/${id}/accept`, {
    method: 'POST',
    body: JSON.stringify({ note }),
    headers: { 'Content-Type': 'application/json' },
  });
  await checkOk(res);
  return res.json();
}

export async function rejectProposal(id: string, note: string) {
  const res = await apiFetch(`${API_BASE}/proposals/${id}/reject`, {
    method: 'POST',
    body: JSON.stringify({ note }),
    headers: { 'Content-Type': 'application/json' },
  });
  await checkOk(res);
  return res.json();
}

export async function deferProposal(id: string) {
  const res = await apiFetch(`${API_BASE}/proposals/${id}/defer`, { method: 'POST' });
  await checkOk(res);
  return res.json();
}

export async function fetchStyleProfile(platform: string, user: string) {
  const res = await apiFetch(`${API_BASE}/style/${encodeURIComponent(platform)}/${encodeURIComponent(user)}`);
  if (!res.ok) throw new Error('Failed to fetch style');
  return res.json();
}

export async function deleteStyleMetric(platform: string, user: string, metric: string) {
  const res = await apiFetch(`${API_BASE}/style/${encodeURIComponent(platform)}/${encodeURIComponent(user)}/${encodeURIComponent(metric)}`, {
    method: 'DELETE',
  });
  await checkOk(res);
  return res.json();
}

export async function fetchSchedulerTasks() {
  const res = await apiFetch(`${API_BASE}/scheduler/tasks`);
  if (!res.ok) throw new Error('Failed to fetch tasks');
  return res.json();
}

export async function createTask(payload: { prompt: string; description?: string; cron_expression?: string; enabled?: boolean; session_id?: string }) {
  const res = await apiFetch(`${API_BASE}/scheduler/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to create task');
  return res.json();
}

export async function updateTask(id: string, payload: Partial<{ prompt: string; description: string; cron_expression: string; enabled: boolean }>) {
  const res = await apiFetch(`${API_BASE}/scheduler/tasks/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to update task');
  return res.json();
}

export async function deleteTask(id: string) {
  const res = await apiFetch(`${API_BASE}/scheduler/tasks/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete task');
  return res.json() as Promise<{ deleted: boolean }>;
}

export async function runTaskNow(id: string) {
  const res = await apiFetch(`${API_BASE}/scheduler/tasks/${id}/run`, { method: 'POST' });
  await checkOk(res);
  return res.json();
}

export async function runDoctor() {
  const res = await apiFetch(`${API_BASE}/doctor`);
  if (!res.ok) throw new Error('Doctor check failed');
  return res.json();
}

export async function runAudit() {
  const res = await apiFetch(`${API_BASE}/audit`);
  if (!res.ok) throw new Error('Audit failed');
  return res.json();
}

export async function fetchEgress(domain?: string, since?: string) {
  const params = new URLSearchParams();
  if (domain) params.set('domain', domain);
  if (since) params.set('since', since);
  const res = await apiFetch(`${API_BASE}/egress?${params}`);
  if (!res.ok) throw new Error('Failed to fetch egress');
  return res.json();
}

export async function fetchConfig() {
  const res = await apiFetch(`${API_BASE}/config`);
  if (!res.ok) throw new Error('Failed to fetch config');
  return res.json();
}

export async function fetchConfigSchema() {
  const res = await apiFetch(`${API_BASE}/config/schema`);
  if (!res.ok) throw new Error('Failed to fetch config schema');
  return res.json();
}

export async function saveConfig(config: object) {
  const res = await apiFetch(`${API_BASE}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  await checkOk(res);
  return res.json();
}

export interface Workflow {
  id: string;
  name: string;
  trigger_type: string;
  trigger_config: Record<string, unknown>;
  last_edited_at: string;
  active_version_id: string | null;
  webhook_url?: string;
  has_secret?: boolean;
  last_execution_status?: string;
  last_execution_at?: string;
}

export interface WorkflowVersion {
  id: string;
  workflow_id: string;
  version_number: number;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  created_at: string;
  activated_at: string | null;
}

export interface WorkflowNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: Record<string, unknown>;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  type?: string;
  sourceHandle?: string;
  targetHandle?: string;
}

export async function fetchWorkflows() {
  const res = await apiFetch(`${API_BASE}/workflows`);
  if (!res.ok) throw new Error('Failed to fetch workflows');
  return res.json() as Promise<{ workflows: Workflow[] }>;
}

export async function createWorkflow(name: string, triggerType = 'manual') {
  const res = await apiFetch(`${API_BASE}/workflows`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, trigger_type: triggerType }),
  });
  if (!res.ok) throw new Error('Failed to create workflow');
  return res.json() as Promise<Workflow>;
}

export async function fetchWorkflow(id: string) {
  const res = await apiFetch(`${API_BASE}/workflows/${id}`);
  if (!res.ok) throw new Error('Failed to fetch workflow');
  return res.json() as Promise<Workflow>;
}

export async function updateWorkflow(id: string, updates: Partial<Workflow>) {
  const res = await apiFetch(`${API_BASE}/workflows/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error('Failed to update workflow');
  return res.json() as Promise<Workflow>;
}

export async function deleteWorkflow(id: string) {
  const res = await apiFetch(`${API_BASE}/workflows/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete workflow');
  return res.json() as Promise<{ deleted: boolean }>;
}

export async function rotateWebhookSecret(id: string) {
  const res = await apiFetch(`${API_BASE}/workflows/${id}/rotate-secret`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to rotate webhook secret');
  return res.json() as Promise<{ workflow: Workflow; secret: string }>;
}

export async function fetchWorkflowVersions(id: string) {
  const res = await apiFetch(`${API_BASE}/workflows/${id}/versions`);
  if (!res.ok) throw new Error('Failed to fetch workflow versions');
  return res.json() as Promise<{ versions: WorkflowVersion[] }>;
}

export async function saveWorkflowVersion(id: string, nodes: WorkflowNode[], edges: WorkflowEdge[]) {
  const res = await apiFetch(`${API_BASE}/workflows/${id}/versions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nodes, edges }),
  });
  if (!res.ok) throw new Error('Failed to save workflow version');
  return res.json() as Promise<WorkflowVersion>;
}

export async function activateWorkflowVersion(workflowId: string, versionId: string) {
  const res = await apiFetch(`${API_BASE}/workflows/${workflowId}/versions/${versionId}/activate`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to activate workflow version');
  return res.json() as Promise<{ activated: boolean }>;
}

export interface NodeResult {
  node_id: string;
  status: string;
  elapsed_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  output: unknown;
  error?: string;
}

export interface ExecutionRecord {
  id: string;
  workflow_id: string;
  version: number;
  status: string;
  trigger_payload: Record<string, unknown>;
  node_results: NodeResult[];
  total_elapsed_ms: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  created_at: string;
}

export interface ExecutionResult {
  status: string;
  total_elapsed_ms: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  node_results: NodeResult[];
  outputs: Record<string, unknown>;
}

export async function testRunWorkflow(id: string, payload?: Record<string, unknown>) {
  const res = await apiFetch(`${API_BASE}/workflows/${id}/test-run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  if (!res.ok) throw new Error('Failed to test run workflow');
  return res.json() as Promise<ExecutionResult>;
}

export async function fetchExecutions(workflowId: string, limit = 50) {
  const res = await apiFetch(`${API_BASE}/workflows/${workflowId}/executions?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch executions');
  return res.json() as Promise<{ executions: ExecutionRecord[] }>;
}

export interface ToolSchema {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  requires_confirmation: boolean;
  tags: string[];
}

export async function fetchTools() {
  const res = await apiFetch(`${API_BASE}/tools`);
  if (!res.ok) throw new Error('Failed to fetch tools');
  return res.json() as Promise<{ tools: ToolSchema[] }>;
}


export async function fetchDashboard() {
  const res = await apiFetch(`${API_BASE}/dashboard`);
  if (!res.ok) throw new Error('Failed to fetch dashboard');
  return res.json() as Promise<{
    active_workflow_count: number;
    recent_executions: ExecutionRecord[];
    pending_proposal_count: number;
    platforms_connected: string[];
  }>;
}

// Users
export interface UserIdentity {
  platform: string;
  platform_user: string;
  verified: boolean;
}

export interface User {
  id: string;
  display_name: string;
  role: string;
  trust_preset: string | null;
  notes: string | null;
  created_at: string;
  identity_count: number;
  room_count: number;
  identities: UserIdentity[];
}

export async function fetchUsers() {
  const res = await apiFetch(`${API_BASE}/users`);
  if (!res.ok) throw new Error('Failed to fetch users');
  return res.json() as Promise<{ users: User[] }>;
}

export interface Conversation {
  id: string;
  platform: string;
  platform_user: string;
  title: string | null;
  started_at: string | null;
  last_active_at: string | null;
  state: string | null;
  message_count: number;
}

export async function fetchConversations(platform: string, limit = 100) {
  const res = await apiFetch(
    `${API_BASE}/sessions?platform=${encodeURIComponent(platform)}&limit=${limit}`
  );
  if (!res.ok) throw new Error('Failed to fetch conversations');
  return res.json() as Promise<{ sessions: Conversation[] }>;
}

export async function fetchUser(userId: string) {
  const res = await apiFetch(`${API_BASE}/users/${userId}`);
  if (!res.ok) throw new Error('Failed to fetch user');
  return res.json() as Promise<{ id: string; display_name: string; role: string; trust_preset: string | null; notes: string | null; created_at: string; identities: Array<{ platform: string; platform_user: string; verified: boolean }> }>;
}

export async function createUser(fields: { display_name: string; role: string; notes?: string; trust_preset?: string }) {
  const res = await apiFetch(`${API_BASE}/users`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  });
  if (!res.ok) throw new Error('Failed to create user');
  return res.json() as Promise<{ id: string; display_name: string; role: string; trust_preset: string | null; notes: string | null; created_at: string }>;
}

export async function updateUser(userId: string, fields: object) {
  const res = await apiFetch(`${API_BASE}/users/${userId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  });
  if (!res.ok) throw new Error('Failed to update user');
  return res.json();
}

export async function deleteUser(userId: string) {
  const res = await apiFetch(`${API_BASE}/users/${userId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete user');
  return res.json() as Promise<{ deleted: boolean }>;
}

export async function addIdentity(userId: string, platform: string, platformUser: string) {
  const res = await apiFetch(`${API_BASE}/users/${userId}/identities`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ platform, platform_user: platformUser }),
  });
  if (!res.ok) throw new Error('Failed to add identity');
  return res.json();
}

export async function removeIdentity(userId: string, platform: string, platformUser: string) {
  const res = await apiFetch(`${API_BASE}/users/${userId}/identities/${platform}/${platformUser}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to remove identity');
  return res.json();
}

// Rooms
export async function fetchRooms() {
  const res = await apiFetch(`${API_BASE}/rooms`);
  if (!res.ok) throw new Error('Failed to fetch rooms');
  return res.json() as Promise<{ rooms: Array<{ id: string; platform: string; platform_room_id: string; display_name: string | null; created_at: string }> }>;
}

// Memories
export interface Memory {
  id: string;
  content: string;
  tags: string[];
  created_at: string | null;
  session_id: string | null;
  platform: string | null;
  platform_user: string | null;
  is_global: boolean;
  is_pinned: boolean;
  is_active: boolean;
  deleted_at: string | null;
  deleted_reason: string | null;
  last_recalled_at: string | null;
  topic_ids: string[];
}

export async function fetchMemories(limit = 100, includeInactive = false) {
  const qs = new URLSearchParams();
  qs.set('limit', String(limit));
  if (includeInactive) qs.set('include_inactive', 'true');
  const res = await apiFetch(`${API_BASE}/memory?${qs}`);
  if (!res.ok) throw new Error('Failed to fetch memories');
  return res.json() as Promise<{ memories: Memory[] }>;
}

export async function fetchMemoriesForUser(platform: string, platformUser: string, limit = 100, includeInactive = false) {
  const qs = new URLSearchParams();
  qs.set('platform', platform);
  qs.set('platform_user', platformUser);
  qs.set('limit', String(limit));
  if (includeInactive) qs.set('include_inactive', 'true');
  const res = await apiFetch(`${API_BASE}/memory?${qs}`);
  if (!res.ok) throw new Error('Failed to fetch memories');
  return res.json() as Promise<{ memories: Memory[] }>;
}

export async function updateMemory(memoryId: string, updates: Partial<Pick<Memory, 'content' | 'tags' | 'is_global' | 'topic_ids'>>) {
  const res = await apiFetch(`${API_BASE}/memory/${encodeURIComponent(memoryId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error('Failed to update memory');
  return res.json() as Promise<{ memory: Memory }>;
}

export async function pinMemory(memoryId: string) {
  const res = await apiFetch(`${API_BASE}/memory/${encodeURIComponent(memoryId)}/pin`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to pin memory');
  return res.json();
}

export async function unpinMemory(memoryId: string) {
  const res = await apiFetch(`${API_BASE}/memory/${encodeURIComponent(memoryId)}/unpin`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to unpin memory');
  return res.json();
}

export async function softDeleteMemory(memoryId: string) {
  const res = await apiFetch(`${API_BASE}/memory/${encodeURIComponent(memoryId)}/soft-delete`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to soft-delete memory');
  return res.json();
}

export async function restoreMemory(memoryId: string) {
  const res = await apiFetch(`${API_BASE}/memory/${encodeURIComponent(memoryId)}/restore`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to restore memory');
  return res.json();
}

export async function deleteMemory(memoryId: string) {
  const res = await apiFetch(`${API_BASE}/memory/${encodeURIComponent(memoryId)}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete memory');
  return res.json();
}

// Topics
export interface Topic {
  id: string;
  platform: string;
  platform_user: string;
  name: string;
  created_at: string | null;
}

export async function fetchTopics(platform: string, platformUser: string) {
  const res = await apiFetch(`${API_BASE}/topics?platform=${encodeURIComponent(platform)}&platform_user=${encodeURIComponent(platformUser)}`);
  if (!res.ok) throw new Error('Failed to fetch topics');
  return res.json() as Promise<{ topics: Topic[] }>;
}

export async function createTopic(platform: string, platformUser: string, name: string) {
  const res = await apiFetch(`${API_BASE}/topics`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ platform, platform_user: platformUser, name }),
  });
  if (!res.ok) throw new Error('Failed to create topic');
  return res.json() as Promise<{ topic: Topic }>;
}

export async function renameTopic(topicId: string, name: string) {
  const res = await apiFetch(`${API_BASE}/topics/${encodeURIComponent(topicId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error('Failed to rename topic');
  return res.json() as Promise<{ topic: Topic }>;
}

export async function deleteTopic(topicId: string) {
  const res = await apiFetch(`${API_BASE}/topics/${encodeURIComponent(topicId)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete topic');
  return res.json();
}

export async function fetchTopicConversations(topicId: string) {
  const res = await apiFetch(`${API_BASE}/topics/${encodeURIComponent(topicId)}/conversations`);
  if (!res.ok) throw new Error('Failed to fetch topic conversations');
  return res.json() as Promise<{ conversations: Array<{ conversation_id: string; created_at: string }> }>;
}

// Sessions
export async function fetchUserSessions(platform: string, platformUser: string, limit = 10) {
  const res = await apiFetch(`${API_BASE}/sessions?platform=${encodeURIComponent(platform)}&platform_user=${encodeURIComponent(platformUser)}&limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch sessions');
  return res.json();
}

export async function fetchSessionMessages(sessionId: string) {
  const res = await apiFetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}/messages`);
  if (!res.ok) throw new Error('Failed to fetch session messages');
  return res.json() as Promise<{
    session: { id: string; platform: string; platform_user: string; title: string | null; started_at: string | null };
    turns: Array<{ id: string; state: string | null; started_at: string | null; iterations: number; error: string | null }>;
    messages: Array<{ role: string; content: string; created_at: string | null }>;
  }>;
}

// Errors
export interface ErrorItem {
  id: string;
  type: 'workflow_execution' | 'scheduler_task' | 'session_turn';
  source_id: string;
  source_name: string;
  message: string;
  created_at: string;
  status: 'unresolved' | 'resolved' | 'ignored';
}

export async function fetchErrors() {
  const res = await apiFetch(`${API_BASE}/errors`);
  if (!res.ok) throw new Error('Failed to fetch errors');
  return res.json() as Promise<{ errors: ErrorItem[] }>;
}

export async function resolveError(id: string) {
  const res = await apiFetch(`${API_BASE}/errors/${encodeURIComponent(id)}/resolve`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to resolve error');
  return res.json();
}

export async function ignoreError(id: string) {
  const res = await apiFetch(`${API_BASE}/errors/${encodeURIComponent(id)}/ignore`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to ignore error');
  return res.json();
}

export async function debugError(id: string) {
  const res = await apiFetch(`${API_BASE}/errors/${encodeURIComponent(id)}/debug`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to fetch debug prompt');
  return res.json() as Promise<{ prompt: string }>;
}

// Browser Sessions
export interface BrowserSession {
  domain: string;
  has_cookies: boolean;
  has_storage_state: boolean;
  cookie_count: number;
  last_saved: string | null;
  last_used: string | null;
  last_health_check: string | null;
  health_status: string;
  health_check_url: string;
  requires_headed: boolean;
}

export async function fetchBrowserSessions(): Promise<BrowserSession[]> {
  const res = await apiFetch(`${API_BASE}/browser-sessions`);
  if (!res.ok) throw new Error('Failed to fetch browser sessions');
  const data = await res.json();
  return data.sessions;
}

export async function deleteBrowserSession(domain: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/browser-sessions/${encodeURIComponent(domain)}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete session');
}

export async function checkBrowserSession(
  domain: string,
  force = false,
): Promise<{ domain: string; status: string }> {
  const params = force ? '?force=true' : '';
  const res = await apiFetch(`${API_BASE}/browser-sessions/${encodeURIComponent(domain)}/check${params}`, {
    method: 'POST',
  });
  if (res.status === 429) throw new Error('Rate limited — try again later');
  if (!res.ok) throw new Error('Health check failed');
  return res.json();
}

export async function setBrowserSessionRequiresHeaded(
  domain: string,
  requires_headed: boolean,
): Promise<BrowserSession> {
  const res = await apiFetch(`${API_BASE}/browser-sessions/${encodeURIComponent(domain)}/requires-headed`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ requires_headed }),
  });
  if (!res.ok) throw new Error('Failed to update headed preference');
  return res.json();
}

export interface StreamSession {
  session_id: string;
  domain: string;
  url: string;
  ws_url: string;
}

export async function fetchActiveBrowserStream(): Promise<StreamSession | null> {
  const res = await apiFetch(`${API_BASE}/browser-sessions/active`);
  if (!res.ok) throw new Error('Failed to fetch active browser stream');
  const data = await res.json();
  return data.active ?? null;
}

export async function startBrowserStream(payload: { url: string; headed?: boolean }): Promise<StreamSession> {
  const res = await apiFetch(`${API_BASE}/browser-sessions/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (res.status === 409) {
    const data = await res.json();
    throw new Error(`Session already active: ${data.session_id}`);
  }
  if (!res.ok) throw new Error('Failed to start browser stream');
  return res.json();
}

export async function stopBrowserStream(): Promise<{ domain: string; cookie_count: number; saved: boolean }> {
  const res = await apiFetch(`${API_BASE}/browser-sessions/stop`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to stop browser stream');
  return res.json();
}

export async function restartHeadedBrowserStream(): Promise<StreamSession> {
  const res = await apiFetch(`${API_BASE}/browser-sessions/restart-headed`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to restart stream in headed mode');
  return res.json();
}

export async function headedLoginBrowserSession(url: string): Promise<{ message: string }> {
  const res = await apiFetch(`${API_BASE}/browser-sessions/headed-login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) throw new Error('Failed to launch headed browser');
  return res.json();
}

// Handoffs
export async function fetchHandoffs(userId: string) {
  const res = await apiFetch(`${API_BASE}/users/${encodeURIComponent(userId)}/handoffs`);
  if (!res.ok) throw new Error('Failed to fetch handoffs');
  return res.json() as Promise<{ handoffs: Array<{ session_id: string; summary: string; created_at: string }> }>;
}

// Context Lab
export interface PreviewLayer {
  name: string;
  tokens: number;
  truncated: boolean;
  text: string;
}

export interface PreviewPromptResult {
  context_length: number;
  budget: number;
  empty_used: number;
  history_used: number;
  history_kept: number;
  history_truncated: number;
  layers: PreviewLayer[];
  assembled_system: string;
  assembled_tokens: number;
}

export async function previewPrompt(payload: {
  identity_tokens?: number;
  memory_tokens?: number;
  context_length?: number;
  history_turns?: number;
}): Promise<PreviewPromptResult> {
  const res = await apiFetch(`${API_BASE}/context-lab/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to preview prompt');
  return res.json() as Promise<PreviewPromptResult>;
}
