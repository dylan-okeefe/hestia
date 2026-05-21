import type { ReactNode, CSSProperties } from 'react';
import './PageCard.css';

interface PageCardProps {
  children: ReactNode;
  style?: CSSProperties;
  className?: string;
}

export default function PageCard({ children, style, className }: PageCardProps) {
  return (
    <div
      className={`page-card${className ? ' ' + className : ''}`}
      style={style}
    >
      {children}
    </div>
  );
}
