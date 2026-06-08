import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ToastProvider } from './hooks/useToast';
import ToastContainer from './components/ToastContainer';
import { useCurrentUser } from './hooks/useCurrentUser';
import StickyNav from './components/layout/StickyNav';
import Dashboard from './pages/Dashboard';
import Proposals from './pages/Proposals';
import StyleProfile from './pages/StyleProfile';
import Scheduler from './pages/Scheduler';
import Security from './pages/Security';
import BrowserSessions from './pages/BrowserSessions';
import BrowserStream from './pages/BrowserStream';
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
import './App.css';

function AppContent() {
  const { auth, loading, logout } = useAuth();
  const { user: currentUser, isLoading: userLoading } = useCurrentUser();

  const isAdmin = currentUser?.role === 'admin';

  if (loading || userLoading || (auth.authenticated && auth.authEnabled && !currentUser)) {
    return (
      <div className="app-loading">
        <p>Loading…</p>
      </div>
    );
  }

  const navLink = (label: string, to: string) => (
    <NavLink
      to={to}
      className={({ isActive }) => isActive ? 'nav-link nav-link--active' : 'nav-link'}
    >
      {label}
    </NavLink>
  );

  return (
    <>
      <ToastContainer />
      {auth.authEnabled && !auth.authenticated ? (
        <Login />
      ) : (
        <>
          <StickyNav>
            {navLink('Dashboard', '/')}
            {navLink('Proposals', '/proposals')}
            {navLink('Style', '/style')}
            {navLink('Scheduler', '/scheduler')}
            {auth.authenticated && isAdmin && navLink('Browser', '/browser-sessions')}
            {navLink('Security & Health', '/security')}
            {navLink('Config', '/config')}
            {navLink('Workflows', '/workflows')}
            {navLink('Profile', '/profile')}
            {navLink('Knowledge', '/knowledge')}
            {navLink('Errors', '/errors')}
            {auth.authenticated && isAdmin && navLink('Users', '/admin/users')}
            {auth.authEnabled && (
              <button onClick={logout} className="nav-logout">
                Log out
              </button>
            )}
          </StickyNav>
          <div className="main-content">
            <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/proposals" element={<Proposals />} />
            <Route path="/style" element={<StyleProfile />} />
            <Route path="/scheduler" element={<Scheduler />} />
            <Route path="/security" element={<Security />} />
            <Route path="/browser-sessions" element={isAdmin ? <BrowserSessions /> : <Navigate to="/" replace />} />
            <Route path="/browser-sessions/stream" element={isAdmin ? <BrowserStream /> : <Navigate to="/" replace />} />
            <Route path="/config" element={<Config />} />
            <Route path="/workflows" element={<Workflows />} />
            <Route path="/workflows/:id" element={<WorkflowEditor />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/knowledge" element={<Knowledge />} />
            <Route path="/sessions/:id" element={<SessionDetail />} />
            <Route path="/admin/users" element={isAdmin ? <AdminUsers /> : <Navigate to="/" replace />} />
            <Route path="/errors" element={<ErrorDashboard />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
          </div>
        </>
      )}
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <AppContent />
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
