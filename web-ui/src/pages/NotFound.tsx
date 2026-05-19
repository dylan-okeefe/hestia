import { Link } from 'react-router-dom';
import './NotFound.css';

export default function NotFound() {
  return (
    <div className="not-found">
      <h1>Page not found</h1>
      <p>
        <Link to="/" className="not-found__link">
          ← Back to dashboard
        </Link>
      </p>
    </div>
  );
}
