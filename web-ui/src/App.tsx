import { useState } from 'react';
import Dashboard from './pages/Dashboard';
import Proposals from './pages/Proposals';
import StyleProfile from './pages/StyleProfile';
import Scheduler from './pages/Scheduler';

type Page = 'dashboard' | 'proposals' | 'style' | 'scheduler';

export default function App() {
  const [page, setPage] = useState<Page>('dashboard');

  const navButton = (label: string, target: Page) => (
    <button
      onClick={() => setPage(target)}
      style={{
        fontWeight: page === target ? 'bold' : 'normal',
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        textDecoration: page === target ? 'underline' : 'none',
      }}
    >
      {label}
    </button>
  );

  return (
    <div>
      <nav style={{ padding: '0.75rem 1rem', borderBottom: '1px solid #ddd', display: 'flex', gap: '1rem' }}>
        {navButton('Dashboard', 'dashboard')}
        {navButton('Proposals', 'proposals')}
        {navButton('Style', 'style')}
        {navButton('Scheduler', 'scheduler')}
      </nav>
      {page === 'dashboard' && <Dashboard />}
      {page === 'proposals' && <Proposals />}
      {page === 'style' && <StyleProfile />}
      {page === 'scheduler' && <Scheduler />}
    </div>
  );
}
