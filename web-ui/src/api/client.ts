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

async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(input, {
    ...init,
    headers: getHeaders((init?.headers as Record<string, string>) || {}),
  });
  if (res.status === 401) {
    clearAuthToken();
    window.dispatchEvent(new CustomEvent('auth:unauthorized'));
  }
  return res;
}

export async function fetchAuthStatus() {
  const res = await apiFetch(`${API_BASE}/auth/status`);
  if (!res.ok) throw new Error('Failed to fetch auth status');
  return res.json();
}

export async function requestCode(platform: string) {
  const res = await apiFetch(`${API_BASE}/auth/request-code`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ platform }),
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

export async function fetchSessions(limit = 50) {
  const res = await apiFetch(`${API_BASE}/sessions?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch sessions');
  return res.json();
}

export async function fetchTurns(sessionId: string) {
  const res = await apiFetch(`${API_BASE}/sessions/${sessionId}/turns`);
  if (!res.ok) throw new Error('Failed to fetch turns');
  return res.json();
}

export async function fetchProposals(status = 'pending') {
  const qs = status ? `?status=${status}` : '';
  const res = await apiFetch(`${API_BASE}/proposals${qs}`);
  if (!res.ok) throw new Error('Failed to fetch proposals');
  return res.json();
}

export async function acceptProposal(id: string, note?: string) {
  return apiFetch(`${API_BASE}/proposals/${id}/accept`, {
    method: 'POST',
    body: JSON.stringify({ note }),
    headers: { 'Content-Type': 'application/json' },
  });
}

export async function rejectProposal(id: string, note: string) {
  return apiFetch(`${API_BASE}/proposals/${id}/reject`, {
    method: 'POST',
    body: JSON.stringify({ note }),
    headers: { 'Content-Type': 'application/json' },
  });
}

export async function deferProposal(id: string) {
  return apiFetch(`${API_BASE}/proposals/${id}/defer`, { method: 'POST' });
}

export async function fetchStyleProfile(platform: string, user: string) {
  const res = await apiFetch(`${API_BASE}/style/${encodeURIComponent(platform)}/${encodeURIComponent(user)}`);
  if (!res.ok) throw new Error('Failed to fetch style');
  return res.json();
}

export async function deleteStyleMetric(platform: string, user: string, metric: string) {
  return apiFetch(`${API_BASE}/style/${encodeURIComponent(platform)}/${encodeURIComponent(user)}/${encodeURIComponent(metric)}`, {
    method: 'DELETE',
  });
}

export async function fetchSchedulerTasks() {
  const res = await apiFetch(`${API_BASE}/scheduler/tasks`);
  if (!res.ok) throw new Error('Failed to fetch tasks');
  return res.json();
}

export async function runTaskNow(id: string) {
  return apiFetch(`${API_BASE}/scheduler/tasks/${id}/run`, { method: 'POST' });
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
  return apiFetch(`${API_BASE}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
}
