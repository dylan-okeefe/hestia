import './LoadingSkeleton.css';

interface LoadingSkeletonProps {
  lines?: number;
  height?: string;
}

export default function LoadingSkeleton({ lines = 1, height = '1rem' }: LoadingSkeletonProps) {
  return (
    <div className="loading-skeleton">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="loading-skeleton__line"
          style={{ height }}
        />
      ))}
    </div>
  );
}
