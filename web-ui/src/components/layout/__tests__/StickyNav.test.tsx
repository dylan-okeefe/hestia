import { render, screen, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import StickyNav from '../StickyNav';

function mockMatchMedia(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

describe('StickyNav', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders sidebar on desktop', () => {
    mockMatchMedia(false);
    render(
      <StickyNav>
        <a href="/">Home</a>
      </StickyNav>
    );
    expect(screen.getAllByText('Hestia').length).toBeGreaterThanOrEqual(1);
    expect(document.querySelector('.nav-sidebar')).toBeInTheDocument();
    expect(document.querySelector('.nav-mobile-topbar')).not.toBeInTheDocument();
  });

  it('renders hamburger topbar on mobile', () => {
    mockMatchMedia(true);
    render(
      <StickyNav>
        <a href="/">Home</a>
      </StickyNav>
    );
    expect(screen.getAllByText('Hestia').length).toBeGreaterThanOrEqual(1);
    expect(document.querySelector('.nav-mobile-topbar')).toBeInTheDocument();
    expect(document.querySelector('.nav-sidebar')).not.toBeInTheDocument();
  });

  it('opens and closes mobile overlay', () => {
    mockMatchMedia(true);
    render(
      <StickyNav>
        <a href="/">Home</a>
      </StickyNav>
    );

    const hamburger = screen.getByLabelText('Open menu');
    fireEvent.click(hamburger);

    expect(document.querySelector('.nav-mobile-overlay--open')).toBeInTheDocument();

    const closeBtn = screen.getByLabelText('Close menu');
    fireEvent.click(closeBtn);

    expect(document.querySelector('.nav-mobile-overlay--open')).not.toBeInTheDocument();
  });
});
