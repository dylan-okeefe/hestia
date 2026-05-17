interface EmptyStateProps {
  title: string;
  description: string;
  action?: { label: string; onClick: () => void };
}

export default function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div style={{ textAlign: 'center', padding: '2rem 1rem', color: '#666' }}>
      <h3 style={{ margin: '0 0 0.5rem', fontSize: '1rem', color: '#333' }}>{title}</h3>
      <p style={{ margin: '0 0 1rem', fontSize: '0.875rem', lineHeight: 1.5 }}>{description}</p>
      {action && (
        <button
          onClick={action.onClick}
          style={{
            padding: '0.5rem 1rem',
            borderRadius: '4px',
            border: '1px solid #ccc',
            background: '#fff',
            cursor: 'pointer',
            fontSize: '0.875rem',
          }}
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
