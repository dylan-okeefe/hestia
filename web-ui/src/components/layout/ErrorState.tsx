import './ErrorState.css';

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export default function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="error-state">
      <p className="error-state__message">{message}</p>
      {onRetry && (
        <div className="error-state__actions">
          <button onClick={onRetry} className="text-danger border-danger">
            Retry
          </button>
        </div>
      )}
    </div>
  );
}
