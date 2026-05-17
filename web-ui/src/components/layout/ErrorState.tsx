interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export default function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div style={{ textAlign: 'center', padding: '2rem 1rem', color: '#ef4444' }}>
      <p style={{ margin: '0 0 1rem', fontSize: '0.875rem' }}>{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          style={{
            padding: '0.5rem 1rem',
            borderRadius: '4px',
            border: '1px solid #ef4444',
            background: '#fff',
            color: '#ef4444',
            cursor: 'pointer',
            fontSize: '0.875rem',
          }}
        >
          Retry
        </button>
      )}
    </div>
  );
}
