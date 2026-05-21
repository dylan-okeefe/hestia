import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import CronBuilder from '../CronBuilder';

vi.mock('../../../lib/format', () => ({
  formatCron: (cron: string) => {
    try {
      if (!cron.trim()) return '';
      // Simple mock mapping for known crons
      const map: Record<string, string> = {
        '0 * * * *': 'Every hour',
        '0 8 * * *': 'At 08:00 AM',
        '0 0 * * 1': 'At 12:00 AM, only on Monday',
        '*/5 * * * *': 'Every 5 minutes',
      };
      return map[cron] || `Cron: ${cron}`;
    } catch {
      return cron;
    }
  },
}));

describe('CronBuilder', () => {
  it('renders frequency buttons', () => {
    render(<CronBuilder value="" onChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: /hourly/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /daily/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /weekly/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /custom/i })).toBeInTheDocument();
  });

  it('switches to daily and shows time inputs', () => {
    render(<CronBuilder value="" onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /daily/i }));
    expect(screen.getByLabelText(/hour/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/minute/i)).toBeInTheDocument();
  });

  it('switches to weekly and shows day checkboxes', () => {
    render(<CronBuilder value="" onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /weekly/i }));
    expect(screen.getByLabelText(/mon/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/sun/i)).toBeInTheDocument();
  });

  it('switches to custom and shows textarea', () => {
    render(<CronBuilder value="" onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /custom/i }));
    expect(screen.getByLabelText(/custom cron expression/i)).toBeInTheDocument();
  });

  it('applies preset and calls onChange', () => {
    const onChange = vi.fn();
    render(<CronBuilder value="" onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /every hour/i }));
    expect(onChange).toHaveBeenCalledWith('0 * * * *');
  });

  it('shows preview for valid cron', () => {
    render(<CronBuilder value="0 8 * * *" onChange={vi.fn()} />);
    expect(screen.getByText(/at 08:00 am/i)).toBeInTheDocument();
  });

  it('shows error for invalid cron', () => {
    render(<CronBuilder value="invalid" onChange={vi.fn()} />);
    expect(screen.getByText(/invalid cron expression/i)).toBeInTheDocument();
  });
});
