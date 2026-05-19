import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import DoctorCheckList from '../DoctorCheckList';
import * as client from '../../api/client';
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
        cached_at: new Date(Date.now() - 60_000).toISOString(),
      })
    ),
  };
});

const defaultChecks = [
  { name: 'python_version', ok: true, detail: '3.13.0' },
  { name: 'dependencies_in_sync', ok: false, detail: 'Out of sync' },
];

describe('DoctorCheckList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders checks with labels', () => {
    render(<DoctorCheckList checks={defaultChecks} onRefresh={vi.fn()} />);

    expect(screen.getByText('Python Version')).toBeInTheDocument();
    expect(screen.getByText('Dependencies in Sync')).toBeInTheDocument();
  });

  it('shows neutral detail color for passing checks', async () => {
    render(<DoctorCheckList checks={defaultChecks} onRefresh={vi.fn()} />);

    fireEvent.click(screen.getByText('Python Version'));

    await waitFor(() => expect(screen.getByText(/3.13.0/i)).toBeInTheDocument());
    const detail = screen.getByText(/3.13.0/i).closest('div');
    expect(detail).toHaveStyle('color: rgb(102, 102, 102)');
  });

  it('shows warning detail color for failing checks', async () => {
    render(<DoctorCheckList checks={defaultChecks} onRefresh={vi.fn()} />);

    fireEvent.click(screen.getByText('Dependencies in Sync'));

    await waitFor(() => expect(screen.getByText(/Out of sync/i)).toBeInTheDocument());
    const detail = screen.getByText(/Out of sync/i).closest('div');
    expect(detail).toHaveStyle('color: rgb(239, 68, 68)');
  });

  it('calls onRefresh and shows cached_at when re-run is clicked', async () => {
    const onRefresh = vi.fn();
    render(<DoctorCheckList checks={defaultChecks} onRefresh={onRefresh} />);

    fireEvent.click(screen.getByText(TEXT.healthChecks.rerunButton));

    await waitFor(() => expect(client.runDoctor).toHaveBeenCalled());
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText(new RegExp(TEXT.healthChecks.lastChecked('').slice(0, -1)))).toBeInTheDocument());
  });
});
