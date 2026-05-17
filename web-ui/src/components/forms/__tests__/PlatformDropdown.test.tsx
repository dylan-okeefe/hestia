import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import PlatformDropdown from '../PlatformDropdown';
import * as client from '../../../api/client';

vi.mock('../../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../../api/client')>('../../../api/client');
  return {
    ...actual,
    fetchAuthStatus: vi.fn(),
  };
});

describe('PlatformDropdown', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders platforms from auth status', async () => {
    vi.mocked(client.fetchAuthStatus).mockResolvedValue({
      auth_enabled: true,
      authenticated: true,
      available_platforms: ['matrix', 'telegram'],
    });

    const onChange = vi.fn();
    render(<PlatformDropdown value="" onChange={onChange} includeEmpty />);

    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument());

    expect(screen.getByText('— Select —')).toBeInTheDocument();
    expect(screen.getByText('matrix')).toBeInTheDocument();
    expect(screen.getByText('telegram')).toBeInTheDocument();
  });

  it('fires onChange when selecting an option', async () => {
    vi.mocked(client.fetchAuthStatus).mockResolvedValue({
      auth_enabled: true,
      authenticated: true,
      available_platforms: ['cli', 'matrix'],
    });

    const onChange = vi.fn();
    render(<PlatformDropdown value="" onChange={onChange} />);

    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument());

    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: 'matrix' } });
    expect(onChange).toHaveBeenCalledWith('matrix');
  });

  it('shows error state on fetch failure', async () => {
    vi.mocked(client.fetchAuthStatus).mockRejectedValue(new Error('Network error'));

    render(<PlatformDropdown value="" onChange={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('Failed to load platforms')).toBeInTheDocument());
  });
});
