import { describe, it, expect } from 'vitest';
import { formatDate, formatRelativeDate, formatCron, formatJson, formatDuration } from '../format';

describe('formatDate', () => {
  it('returns formatted date for valid ISO string', () => {
    const result = formatDate('2026-05-17T10:30:00Z');
    expect(result).not.toBe('—');
    expect(result).toContain('2026');
  });

  it('returns em dash for null', () => {
    expect(formatDate(null)).toBe('—');
  });

  it('returns raw string for invalid date', () => {
    expect(formatDate('not-a-date')).toBe('not-a-date');
  });
});

describe('formatRelativeDate', () => {
  it('returns just now for very recent timestamps', () => {
    const now = new Date().toISOString();
    expect(formatRelativeDate(now)).toBe('Just now');
  });

  it('returns minutes ago for recent timestamps', () => {
    const fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    expect(formatRelativeDate(fiveMinAgo)).toBe('5 minutes ago');
  });

  it('returns yesterday for timestamps between 24-48 hours ago', () => {
    const yesterday = new Date(Date.now() - 30 * 60 * 60 * 1000).toISOString();
    expect(formatRelativeDate(yesterday)).toContain('Yesterday at');
  });
});

describe('formatCron', () => {
  it('returns human-readable cron for valid expression', () => {
    expect(formatCron('0 9 * * 1')).toContain('Monday');
  });

  it('falls back to raw string for invalid expression', () => {
    expect(formatCron('not-a-cron')).toBe('not-a-cron');
  });
});

describe('formatJson', () => {
  it('pretty-prints objects with 2-space indentation', () => {
    const result = formatJson({ a: 1, b: true });
    expect(result).toContain('\n');
    expect(result).toContain('  "a": 1');
  });
});

describe('formatDuration', () => {
  it('formats seconds', () => {
    expect(formatDuration(45)).toBe('45 sec');
  });

  it('formats minutes', () => {
    expect(formatDuration(180)).toBe('3 min');
  });

  it('formats hours', () => {
    expect(formatDuration(5400)).toBe('1.5 hr');
  });

  it('formats days', () => {
    expect(formatDuration(172800)).toBe('2 days');
  });
});
