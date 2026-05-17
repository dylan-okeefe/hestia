import type { ReactNode, CSSProperties } from 'react';

interface PageCardProps {
  children: ReactNode;
  style?: CSSProperties;
}

export default function PageCard({ children, style }: PageCardProps) {
  return (
    <div
      style={{
        background: '#fff',
        border: '1px solid #eee',
        borderRadius: '8px',
        padding: '1rem',
        marginBottom: '1rem',
        boxShadow: '0 1px 3px -2px rgba(0,0,0,0.02), 0 2px 5px -2px rgba(0,0,0,0.04)',
        ...style,
      }}
    >
      {children}
    </div>
  );
}
