import { useState } from 'react';
import type { ReactNode } from 'react';
import { useMediaQuery } from '../../hooks/useMediaQuery';
import './StickyNav.css';

interface StickyNavProps {
  children: ReactNode;
}

export default function StickyNav({ children }: StickyNavProps) {
  const isMobile = useMediaQuery('(max-width: 767px)');
  const [menuOpen, setMenuOpen] = useState(false);

  if (isMobile) {
    return (
      <>
        <div className="nav-mobile-topbar">
          <span className="font-semibold">Hestia</span>
          <button
            onClick={() => setMenuOpen(true)}
            aria-label="Open menu"
            className="nav-hamburger"
          >
            ☰
          </button>
        </div>
        <div className={`nav-mobile-overlay ${menuOpen ? 'nav-mobile-overlay--open' : ''}`}>
          <div className="row-between">
            <span className="font-semibold">Hestia</span>
            <button
              onClick={() => setMenuOpen(false)}
              aria-label="Close menu"
              className="nav-close-btn"
            >
              ✕
            </button>
          </div>
          <nav className="stack-md" onClick={() => setMenuOpen(false)}>
            {children}
          </nav>
        </div>
      </>
    );
  }

  return (
    <nav className="nav-sidebar">
      <div className="font-semibold mb-2">Hestia</div>
      {children}
    </nav>
  );
}
