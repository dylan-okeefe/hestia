import type { ReactNode } from 'react';

interface StickyNavProps {
  children: ReactNode;
}

export default function StickyNav({ children }: StickyNavProps) {
  return (
    <nav
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 50,
        background: '#fff',
        borderBottom: '1px solid #ddd',
        padding: '0.75rem 1rem',
        display: 'flex',
        gap: '1rem',
        alignItems: 'center',
      }}
    >
      {children}
    </nav>
  );
}
