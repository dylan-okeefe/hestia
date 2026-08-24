import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import AllowListDiffDialog from '../AllowListDiffDialog';

describe('AllowListDiffDialog', () => {
  const baseProps = {
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  };

  it('renders nothing when diff is null', () => {
    const { container } = render(<AllowListDiffDialog {...baseProps} isOpen diff={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders added and removed tools', () => {
    render(
      <AllowListDiffDialog
        {...baseProps}
        isOpen
        diff={{ added: ['terminal', 'node:http_request'], removed: ['old_tool'] }}
      />
    );
    expect(screen.getByText('Newly allowed')).toBeInTheDocument();
    expect(screen.getByText('No longer allowed')).toBeInTheDocument();
    expect(screen.getByText('terminal')).toBeInTheDocument();
    expect(screen.getByText('node:http_request')).toBeInTheDocument();
    expect(screen.getByText('old_tool')).toBeInTheDocument();
  });

  it('confirm requires explicit click and reports the decision', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <AllowListDiffDialog
        {...baseProps}
        isOpen
        diff={{ added: ['terminal'], removed: [] }}
        onConfirm={onConfirm}
        onCancel={onCancel}
      />
    );
    fireEvent.click(screen.getByText('Confirm & activate'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText('Cancel'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
