const API_BASE = '/api';

export async function fetchSessions(limit = 50) {
  const res = await fetch(`${API_BASE}/sessions?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch sessions');
  return res.json();
}

export async function fetchTurns(sessionId: string) {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/turns`);
  if (!res.ok) throw new Error('Failed to fetch turns');
  return res.json();
}

export async function fetchProposals(status = 'pending') {
  const qs = status ? `?status=${status}` : '';
  const res = await fetch(`${API_BASE}/proposals${qs}`);
  if (!res.ok) throw new Error('Failed to fetch proposals');
  return res.json();
}

export async function acceptProposal(id: string, note?: string) {
  return fetch(`${API_BASE}/proposals/${id}/accept`, {
    method: 'POST',
    body: JSON.stringify({ note }),
    headers: { 'Content-Type': 'application/json' },
  });
}

export async function rejectProposal(id: string, note: string) {
  return fetch(`${API_BASE}/proposals/${id}/reject`, {
    method: 'POST',
    body: JSON.stringify({ note }),
    headers: { 'Content-Type': 'application/json' },
  });
}

export async function deferProposal(id: string) {
  return fetch(`${API_BASE}/proposals/${id}/defer`, { method: 'POST' });
}

export async function fetchStyleProfile(platform: string, user: string) {
  const res = await fetch(`${API_BASE}/style/${encodeURIComponent(platform)}/${encodeURIComponent(user)}`);
  if (!res.ok) throw new Error('Failed to fetch style');
  return res.json();
}

export async function deleteStyleMetric(platform: string, user: string, metric: string) {
  return fetch(`${API_BASE}/style/${encodeURIComponent(platform)}/${encodeURIComponent(user)}/${encodeURIComponent(metric)}`, {
    method: 'DELETE',
  });
}

export async function fetchSchedulerTasks() {
  const res = await fetch(`${API_BASE}/scheduler/tasks`);
  if (!res.ok) throw new Error('Failed to fetch tasks');
  return res.json();
}

export async function runTaskNow(id: string) {
  return fetch(`${API_BASE}/scheduler/tasks/${id}/run`, { method: 'POST' });
}

export async function runDoctor() {
  const res = await fetch(`${API_BASE}/doctor`);
  if (!res.ok) throw new Error('Doctor check failed');
  return res.json();
}

export async function runAudit() {
  const res = await fetch(`${API_BASE}/audit`);
  if (!res.ok) throw new Error('Audit failed');
  return res.json();
}

export async function fetchEgress(domain?: string, since?: string) {
  const params = new URLSearchParams();
  if (domain) params.set('domain', domain);
  if (since) params.set('since', since);
  const res = await fetch(`${API_BASE}/egress?${params}`);
  if (!res.ok) throw new Error('Failed to fetch egress');
  return res.json();
}

export async function fetchConfig() {
  const res = await fetch(`${API_BASE}/config`);
  if (!res.ok) throw new Error('Failed to fetch config');
  return res.json();
}

export async function saveConfig(config: object) {
  return fetch(`${API_BASE}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
}
