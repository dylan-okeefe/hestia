import cronstrue from 'cronstrue';

export function formatDate(isoString: string | null): string {
  if (!isoString) return '—';
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return isoString;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

export function formatRelativeDate(isoString: string): string {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return isoString;

  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffSec < 60) return 'Just now';
  if (diffMin < 60) return `${diffMin} minute${diffMin === 1 ? '' : 's'} ago`;
  if (diffHour < 24) return `${diffHour} hour${diffHour === 1 ? '' : 's'} ago`;
  if (diffDay === 1) {
    const timeStr = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(date);
    return `Yesterday at ${timeStr}`;
  }
  if (diffDay < 7) return `${diffDay} days ago`;
  return formatDate(isoString);
}

export function formatCron(cron: string): string {
  try {
    return cronstrue.toString(cron, { verbose: false });
  } catch {
    return cron;
  }
}

export function formatJson(obj: unknown): string {
  return JSON.stringify(obj, null, 2);
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)} sec`;
  if (seconds < 3600) {
    const min = Math.round(seconds / 60);
    return `${min} min`;
  }
  const hr = seconds / 3600;
  if (hr < 24) {
    return hr % 1 === 0 ? `${hr} hr` : `${hr.toFixed(1)} hr`;
  }
  const days = hr / 24;
  return days % 1 === 0 ? `${days} day${days === 1 ? '' : 's'}` : `${days.toFixed(1)} days`;
}
