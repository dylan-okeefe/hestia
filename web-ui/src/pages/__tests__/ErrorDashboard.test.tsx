import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import ErrorDashboard from '../ErrorDashboard';
import * as client from '../../api/client';
import { TEXT } from '../../lib/text';

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client');
  return {
    ...actual,
    fetchErrors: vi.fn(),
    resolveError: vi.fn(),
    ignoreError: vi.fn(),
    debugError: vi.fn(),
  };
});

describe('ErrorDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(client.fetchErrors).mockResolvedValue({
      errors: [
        {
          id: 'workflow_execution:ex1',
          type: 'workflow_execution',
          source_id: 'ex1',
          source_name: 'Test Workflow',
          message: 'Node failed: timeout',
          created_at: '2024-01-01T12:00:00Z',
          status: 'unresolved',
        },
        {
          id: 'scheduler_task:task1',
          type: 'scheduler_task',
          source_id: 'task1',
          source_name: 'Daily check',
          message: 'Connection refused',
          created_at: '2024-01-02T08:00:00Z',
          status: 'unresolved',
        },
      ],
    });
  });

  it('renders error list with type badges', async () => {
    render(<ErrorDashboard />);
    await waitFor(() => expect(screen.getByText('Test Workflow')).toBeInTheDocument());
    expect(screen.getByText('Daily check')).toBeInTheDocument();
    expect(screen.getAllByText('Workflow').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Scheduler').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Node failed: timeout')).toBeInTheDocument();
  });

  it('shows stats header', async () => {
    render(<ErrorDashboard />);
    await waitFor(() => expect(screen.getByText('2')).toBeInTheDocument());
    expect(screen.getAllByText('Unresolved').length).toBeGreaterThanOrEqual(1);
  });

  it('filters by type', async () => {
    render(<ErrorDashboard />);
    await waitFor(() => expect(screen.getByText('Test Workflow')).toBeInTheDocument());
    const typeSelect = screen.getAllByRole('combobox')[0];
    fireEvent.change(typeSelect, { target: { value: 'workflow_execution' } });
    await waitFor(() => expect(screen.queryByText('Daily check')).not.toBeInTheDocument());
    expect(screen.getByText('Test Workflow')).toBeInTheDocument();
  });

  it('filters by status', async () => {
    vi.mocked(client.fetchErrors).mockResolvedValue({
      errors: [
        {
          id: 'workflow_execution:ex1',
          type: 'workflow_execution',
          source_id: 'ex1',
          source_name: 'Test Workflow',
          message: 'Node failed',
          created_at: '2024-01-01T12:00:00Z',
          status: 'resolved',
        },
      ],
    });
    render(<ErrorDashboard />);
    await waitFor(() => expect(screen.getByText('Test Workflow')).toBeInTheDocument());
    const statusSelect = screen.getAllByRole('combobox')[1];
    fireEvent.change(statusSelect, { target: { value: 'unresolved' } });
    await waitFor(() => expect(screen.queryByText('Test Workflow')).not.toBeInTheDocument());
  });

  it('expands and collapses details', async () => {
    render(<ErrorDashboard />);
    await waitFor(() => expect(screen.getByText('Test Workflow')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText(TEXT.errorDashboard.detailsButton)[0]);
    await waitFor(() => expect(screen.getByText(TEXT.errorDashboard.sourceIdFormat('ex1', 'workflow_execution'))).toBeInTheDocument());
    fireEvent.click(screen.getAllByText(TEXT.errorDashboard.hideButton)[0]);
    await waitFor(() => expect(screen.queryByText(/Source ID: ex1/)).not.toBeInTheDocument());
  });

  it('resolves an error', async () => {
    vi.mocked(client.resolveError).mockResolvedValue({ resolved: true });
    render(<ErrorDashboard />);
    await waitFor(() => expect(screen.getByText('Test Workflow')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText(TEXT.errorDashboard.resolveButton)[0]);
    await waitFor(() => expect(client.resolveError).toHaveBeenCalledWith('workflow_execution:ex1'));
  });

  it('ignores an error', async () => {
    vi.mocked(client.ignoreError).mockResolvedValue({ ignored: true });
    render(<ErrorDashboard />);
    await waitFor(() => expect(screen.getByText('Test Workflow')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText(TEXT.errorDashboard.ignoreButton)[0]);
    await waitFor(() => expect(client.ignoreError).toHaveBeenCalledWith('workflow_execution:ex1'));
  });

  it('opens debug modal', async () => {
    vi.mocked(client.debugError).mockResolvedValue({ prompt: 'Debug workflow_execution error:\nWorkflow: wf1' });
    render(<ErrorDashboard />);
    await waitFor(() => expect(screen.getByText('Test Workflow')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText(TEXT.errorDashboard.debugButton)[0]);
    await waitFor(() => expect(screen.getByText(TEXT.errorDashboard.debugModalTitle)).toBeInTheDocument());
    expect(screen.getByDisplayValue(/Debug workflow_execution error:/)).toBeInTheDocument();
  });

  it('shows empty state when no errors', async () => {
    vi.mocked(client.fetchErrors).mockResolvedValue({ errors: [] });
    render(<ErrorDashboard />);
    await waitFor(() => expect(screen.getByText(TEXT.errorDashboard.emptyTitle)).toBeInTheDocument());
    expect(screen.getByText(TEXT.errorDashboard.emptyDescription)).toBeInTheDocument();
  });
});
