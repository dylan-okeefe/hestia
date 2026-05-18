import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { useCurrentUser } from './hooks/useCurrentUser';
import StickyNav from './components/layout/StickyNav';
import Dashboard from './pages/Dashboard';
import Proposals from './pages/Proposals';
import StyleProfile from './pages/StyleProfile';
import Scheduler from './pages/Scheduler';
import Security from './pages/Security';
import Config from './pages/Config';
import Workflows from './pages/Workflows';
import WorkflowEditor from './pages/WorkflowEditor';
import Profile from './pages/Profile';
import Knowledge from './pages/Knowledge';
import SessionDetail from './pages/SessionDetail';
import AdminUsers from './pages/AdminUsers';
import ErrorDashboard from './pages/ErrorDashboard';
import Login from './pages/Login';
import NotFound from './pages/NotFound';

function AppContent() {
  const { auth, loading, logout } = useAuth();
  const { user: currentUser, isLoading: userLoading } = useCurrentUser();

  const isAdmin = currentUser?.role === 'admin';

  if (loading || userLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
        <p>Loading…</p>
      </div>
    );
  }

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
    <>
      {auth.authEnabled && !auth.authenticated ? (
        <Login />
      ) : (
        <>
          <StickyNav>
            {navLink('Dashboard', '/')}
            {navLink('Proposals', '/proposals')}
            {navLink('Style', '/style')}
            {navLink('Scheduler', '/scheduler')}
            {navLink('Security & Health', '/security')}
            {navLink('Config', '/config')}
            {navLink('Workflows', '/workflows')}
            {navLink('Profile', '/profile')}
            {navLink('Knowledge', '/knowledge')}
            {navLink('Errors', '/errors')}
            {auth.authenticated && isAdmin && navLink('Users', '/admin/users')}
            {auth.authEnabled && (
              <button
                onClick={logout}
                style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: '#666' }}
              >
                Log out
              </button>
            )}
          </StickyNav>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/proposals" element={<Proposals />} />
            <Route path="/style" element={<StyleProfile />} />
            <Route path="/scheduler" element={<Scheduler />} />
            <Route path="/security" element={<Security />} />
            <Route path="/config" element={<Config />} />
            <Route path="/workflows" element={<Workflows />} />
            <Route path="/workflows/:id" element={<WorkflowEditor />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/knowledge" element={<Knowledge />} />
            <Route path="/sessions/:id" element={<SessionDetail />} />
            <Route path="/admin/users" element={<AdminUsers />} />
            <Route path="/errors" element={<ErrorDashboard />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </>
      )}
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </BrowserRouter>
  );
}
