import './EmptyState.css';

interface EmptyStateProps {
  title: string;
  description: string;
  action?: { label: string; onClick: () => void };
}

export default function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <h3 className="empty-state__title">{title}</h3>
      <p className="empty-state__description">{description}</p>
      {action && (
        <button
          onClick={action.onClick}
          className="empty-state__action"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
