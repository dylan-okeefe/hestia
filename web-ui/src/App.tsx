import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Proposals from './pages/Proposals';
import StyleProfile from './pages/StyleProfile';
import Scheduler from './pages/Scheduler';
import Security from './pages/Security';
import Config from './pages/Config';

export default function App() {
  const navLink = (label: string, to: string) => (
    <NavLink
      to={to}
      style={({ isActive }) => ({
        fontWeight: isActive ? 'bold' : 'normal',
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        textDecoration: isActive ? 'underline' : 'none',
        color: 'inherit',
      })}
    >
      {label}
    </NavLink>
  );

  return (
    <BrowserRouter>
      <nav style={{ padding: '0.75rem 1rem', borderBottom: '1px solid #ddd', display: 'flex', gap: '1rem' }}>
        {navLink('Dashboard', '/')}
        {navLink('Proposals', '/proposals')}
        {navLink('Style', '/style')}
        {navLink('Scheduler', '/scheduler')}
        {navLink('Security', '/security')}
        {navLink('Config', '/config')}
      </nav>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/proposals" element={<Proposals />} />
        <Route path="/style" element={<StyleProfile />} />
        <Route path="/scheduler" element={<Scheduler />} />
        <Route path="/security" element={<Security />} />
        <Route path="/config" element={<Config />} />
      </Routes>
    </BrowserRouter>
  );
}
