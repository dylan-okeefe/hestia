import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import EmptyState from '../EmptyState';
import ErrorState from '../ErrorState';

describe('EmptyState', () => {
  it('renders title and description', () => {
    render(<EmptyState title="No data" description="There is nothing here yet." />);
    expect(screen.getByText('No data')).toBeInTheDocument();
    expect(screen.getByText('There is nothing here yet.')).toBeInTheDocument();
  });

  it('renders action button when provided', async () => {
    const onClick = vi.fn();
    render(
      <EmptyState
        title="No data"
        description="There is nothing here yet."
        action={{ label: 'Create item', onClick }}
      />
    );
    const btn = screen.getByRole('button', { name: 'Create item' });
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    expect(onClick).toHaveBeenCalled();
  });
});

describe('ErrorState', () => {
  it('renders message and retry button', async () => {
    const onRetry = vi.fn();
    render(<ErrorState message="Something went wrong" onRetry={onRetry} />);
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    const btn = screen.getByRole('button', { name: 'Retry' });
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    expect(onRetry).toHaveBeenCalled();
  });
});
