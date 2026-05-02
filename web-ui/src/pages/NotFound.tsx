import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div style={{ padding: '2rem', textAlign: 'center' }}>
      <h1>Page not found</h1>
      <p>
        <Link to="/" style={{ color: '#1976d2' }}>
          ← Back to dashboard
        </Link>
      </p>
    </div>
  );
}
