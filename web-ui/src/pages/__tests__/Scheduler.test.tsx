import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import Scheduler from '../Scheduler';
import * as client from '../../api/client';

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client');
  return {
    ...actual,
    fetchSchedulerTasks: vi.fn(() =>
      Promise.resolve({
        tasks: [
          {
            id: 'task-1',
            session_id: 's1',
            prompt: 'https://example.com',
            description: 'Daily check',
            cron_expression: '0 8 * * *',
            enabled: true,
            notify: false,
            created_at: '2024-01-01T12:00:00Z',
            last_run_at: null,
            next_run_at: '2024-01-02T08:00:00Z',
            last_error: null,
          },
        ],
      })
    ),
    createTask: vi.fn(() =>
      Promise.resolve({ id: 'task-new', prompt: 'new', cron_expression: '0 9 * * *' })
    ),
    updateTask: vi.fn(() =>
      Promise.resolve({ id: 'task-1', prompt: 'updated', cron_expression: '0 9 * * *' })
    ),
    deleteTask: vi.fn(() => Promise.resolve({ deleted: true })),
    runTaskNow: vi.fn(() => Promise.resolve({ triggered: true })),
  };
});

describe('Scheduler', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders task list with cron display', async () => {
    render(<Scheduler />);

    await waitFor(() => expect(screen.getByText('Daily check')).toBeInTheDocument());
    expect(screen.getByText('https://example.com')).toBeInTheDocument();
    expect(screen.getByText(/at 08:00 AM/i)).toBeInTheDocument();
  });

  it('opens create modal and submits', async () => {
    render(<Scheduler />);

    await waitFor(() => expect(screen.getByText('Daily check')).toBeInTheDocument());
    fireEvent.click(screen.getByText('+ New Task'));

    await waitFor(() => expect(screen.getByText('New Task')).toBeInTheDocument());

    const nameInput = screen.getByPlaceholderText('Daily summary');
    fireEvent.change(nameInput, { target: { value: 'Test task' } });

    const promptInput = screen.getByPlaceholderText('https://example.com or prompt text');
    expect(promptInput.tagName.toLowerCase()).toBe('textarea');
    fireEvent.change(promptInput, { target: { value: 'https://test.com' } });

    fireEvent.click(screen.getByText('Create'));

    await waitFor(() => expect(client.createTask).toHaveBeenCalled());
  });

  it('opens edit modal and saves', async () => {
    render(<Scheduler />);

    await waitFor(() => expect(screen.getByText('Daily check')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Edit'));

    await waitFor(() => expect(screen.getByText('Edit Task')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => expect(client.updateTask).toHaveBeenCalled());
  });

  it('deletes task with confirmation', async () => {
    render(<Scheduler />);

    await waitFor(() => expect(screen.getByText('Daily check')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText('Delete')[0]);

    await waitFor(() => expect(screen.getByText('Delete task?')).toBeInTheDocument());
    const deleteButtons = screen.getAllByText('Delete');
    fireEvent.click(deleteButtons[deleteButtons.length - 1]);

    await waitFor(() => expect(client.deleteTask).toHaveBeenCalledWith('task-1'));
  });

  it('runs task with confirmation', async () => {
    render(<Scheduler />);

    await waitFor(() => expect(screen.getByText('Daily check')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Run now'));

    await waitFor(() => expect(screen.getByText('Run task now?')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Run'));

    await waitFor(() => expect(client.runTaskNow).toHaveBeenCalledWith('task-1'));
  });

  it('shows empty state when no tasks', async () => {
    vi.mocked(client.fetchSchedulerTasks).mockResolvedValueOnce({ tasks: [] });
    render(<Scheduler />);

    await waitFor(() =>
      expect(screen.getByText('No scheduled tasks')).toBeInTheDocument()
    );
  });
});
