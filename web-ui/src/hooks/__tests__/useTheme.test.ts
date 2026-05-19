import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { useTheme } from '../useTheme';

describe('useTheme', () => {
  let matchMediaListeners: Array<(e: MediaQueryListEvent) => void> = [];

  const mockMatchMedia = (matches: boolean) => {
    return vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      addEventListener: vi.fn((event: string, listener: (e: MediaQueryListEvent) => void) => {
        if (event === 'change') {
          matchMediaListeners.push(listener);
        }
      }),
      removeEventListener: vi.fn((event: string, listener: (e: MediaQueryListEvent) => void) => {
        if (event === 'change') {
          matchMediaListeners = matchMediaListeners.filter((l) => l !== listener);
        }
      }),
      dispatchEvent: vi.fn(),
    }));
  };

  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
    matchMediaListeners = [];
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('toggles theme between light, dark, and system', () => {
    window.matchMedia = mockMatchMedia(false);
    const { result } = renderHook(() => useTheme());

    expect(result.current.theme).toBe('system');
    expect(result.current.effectiveTheme).toBe('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');

    act(() => {
      result.current.setTheme('dark');
    });
    expect(result.current.theme).toBe('dark');
    expect(result.current.effectiveTheme).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');

    act(() => {
      result.current.setTheme('light');
    });
    expect(result.current.theme).toBe('light');
    expect(result.current.effectiveTheme).toBe('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');

    act(() => {
      result.current.setTheme('system');
    });
    expect(result.current.theme).toBe('system');
    expect(result.current.effectiveTheme).toBe('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('persists theme preference in localStorage', () => {
    window.matchMedia = mockMatchMedia(false);
    const { result } = renderHook(() => useTheme());

    act(() => {
      result.current.setTheme('dark');
    });
    expect(localStorage.getItem('hestia-theme')).toBe('dark');

    const { result: result2 } = renderHook(() => useTheme());
    expect(result2.current.theme).toBe('dark');
    expect(result2.current.effectiveTheme).toBe('dark');
  });

  it('respects system preference when theme is system', () => {
    window.matchMedia = mockMatchMedia(true);
    const { result } = renderHook(() => useTheme());

    expect(result.current.theme).toBe('system');
    expect(result.current.effectiveTheme).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('updates effective theme when OS theme changes while on system', () => {
    window.matchMedia = mockMatchMedia(false);
    const { result, rerender } = renderHook(() => useTheme());

    expect(result.current.effectiveTheme).toBe('light');

    // Simulate OS switching to dark mode
    window.matchMedia = mockMatchMedia(true);
    act(() => {
      matchMediaListeners.forEach((listener) =>
        listener({ matches: true } as MediaQueryListEvent)
      );
    });

    rerender();
    expect(result.current.effectiveTheme).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });
});
