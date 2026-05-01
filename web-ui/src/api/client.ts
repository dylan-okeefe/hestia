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
