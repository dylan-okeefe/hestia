import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import ConfigForm from '../ConfigForm';

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client');
  return {
    ...actual,
    fetchConfigSchema: vi.fn(() => Promise.resolve({ schema: {} })),
  };
});

describe('ConfigForm cron preview', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows human-readable cron preview for cron-like values', () => {
    render(
      <ConfigForm
        initialConfig={{
          scheduler: {
            cron: '0 9 * * 1',
          },
        }}
      />
    );

    expect(screen.getByDisplayValue('0 9 * * 1')).toBeInTheDocument();
    expect(screen.getByText(/Monday/i)).toBeInTheDocument();
  });

  it('does not show cron preview for non-cron values', () => {
    render(
      <ConfigForm
        initialConfig={{
          core: {
            model_name: 'my-model',
          },
        }}
      />
    );

    expect(screen.getByDisplayValue('my-model')).toBeInTheDocument();
    expect(screen.queryByText(/Monday/i)).not.toBeInTheDocument();
  });
});
