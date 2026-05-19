import type { ReactNode } from 'react';
import './StickyNav.css';

interface StickyNavProps {
  children: ReactNode;
}

export default function StickyNav({ children }: StickyNavProps) {
  return (
    <nav className="sticky-nav">
      {children}
    </nav>
  );
}
