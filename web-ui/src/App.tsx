import { useState } from 'react';
import Dashboard from './pages/Dashboard';
import Proposals from './pages/Proposals';

type Page = 'dashboard' | 'proposals';

export default function App() {
  const [page, setPage] = useState<Page>('dashboard');

  return (
    <div>
      <nav style={{ padding: '0.75rem 1rem', borderBottom: '1px solid #ddd', display: 'flex', gap: '1rem' }}>
        <button
          onClick={() => setPage('dashboard')}
          style={{ fontWeight: page === 'dashboard' ? 'bold' : 'normal', background: 'none', border: 'none', cursor: 'pointer' }}
        >
          Dashboard
        </button>
        <button
          onClick={() => setPage('proposals')}
          style={{ fontWeight: page === 'proposals' ? 'bold' : 'normal', background: 'none', border: 'none', cursor: 'pointer' }}
        >
          Proposals
        </button>
      </nav>
      {page === 'dashboard' && <Dashboard />}
      {page === 'proposals' && <Proposals />}
    </div>
  );
}
