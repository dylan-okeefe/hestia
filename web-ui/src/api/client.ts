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
