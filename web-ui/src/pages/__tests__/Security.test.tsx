import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import Security from '../Security';
import { TEXT } from '../../lib/text';

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client');
  return {
    ...actual,
    runDoctor: vi.fn(() =>
      Promise.resolve({
        checks: [
          { name: 'python_version', ok: true, detail: '3.13.0' },
          { name: 'dependencies_in_sync', ok: false, detail: 'Out of sync' },
        ],
        cached_at: '2024-01-01T12:00:00Z',
      })
    ),
    runAudit: vi.fn(() =>
      Promise.resolve({
        findings: [
          { severity: 'warning', category: 'config', message: 'Weak secret', details: {} },
          { severity: 'info', category: 'deps', message: 'Up to date', details: {} },
        ],
      })
    ),
    fetchEgress: vi.fn(() => Promise.resolve({ events: [] })),
  };
});

describe('Security', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders health checks with labels', async () => {
    render(<Security />);

    await waitFor(() => expect(screen.getByText('Python Version')).toBeInTheDocument());
    expect(screen.getByText('Dependencies in Sync')).toBeInTheDocument();
  });

  it('expands detail and shows remediation for failed checks', async () => {
    render(<Security />);

    await waitFor(() => expect(screen.getByText('Dependencies in Sync')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Dependencies in Sync'));

    await waitFor(() =>
      expect(screen.getByText(/Run `uv sync` to update dependencies./i)).toBeInTheDocument()
    );
  });

  it('filters audit findings by tab', async () => {
    render(<Security />);

    await waitFor(() => expect(screen.getByText('Weak secret')).toBeInTheDocument());

    fireEvent.click(screen.getByText(TEXT.security.tabInfo));
    expect(screen.queryByText('Weak secret')).not.toBeInTheDocument();
    expect(screen.getByText('Up to date')).toBeInTheDocument();
  });
});
