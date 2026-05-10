import { useState, useEffect } from 'react';
import './index.css';
import { isAuthenticated, getAdminEmail, logout } from './auth';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Subscribers from './pages/Subscribers';
import Goals from './pages/Goals';
import Tools from './pages/Tools';

const PAGES = {
  dashboard: { label: 'Dashboard', icon: '📊', component: Dashboard },
  subscribers: { label: 'Subscribers', icon: '👥', component: Subscribers },
  goals: { label: 'Goal History', icon: '🏒', component: Goals },
  tools: { label: 'Tools', icon: '🧪', component: Tools },
};

export default function App() {
  const [authed, setAuthed] = useState(null); // null = loading
  const [page, setPage] = useState('dashboard');
  const [adminEmail, setAdminEmail] = useState('');

  useEffect(() => {
    isAuthenticated()
      .then(async (ok) => {
        setAuthed(ok);
        if (ok) {
          const email = await getAdminEmail();
          setAdminEmail(email);
        }
      })
      .catch(() => setAuthed(false));
  }, []);

  function handleLoginSuccess() {
    setAuthed(true);
    getAdminEmail().then(setAdminEmail).catch(() => {});
  }

  function handleLogout() {
    logout();
    setAuthed(false);
    setAdminEmail('');
    setPage('dashboard');
  }

  // Loading state
  if (authed === null) {
    return (
      <div className="login-page">
        <div className="spinner" style={{ width: 40, height: 40 }} />
      </div>
    );
  }

  // Not authenticated
  if (!authed) {
    return <Login onSuccess={handleLoginSuccess} />;
  }

  // Authenticated — render dashboard
  const CurrentPage = PAGES[page]?.component || Dashboard;

  return (
    <>
      <nav className="sidebar">
        <div className="sidebar-logo">
          <h1>🏒 Rusty's Shake</h1>
          <p>Admin Dashboard</p>
        </div>
        <div className="sidebar-nav">
          {Object.entries(PAGES).map(([key, { label, icon }]) => (
            <a
              key={key}
              href="#"
              className={page === key ? 'active' : ''}
              onClick={(e) => { e.preventDefault(); setPage(key); }}
            >
              <span className="icon">{icon}</span>
              <span>{label}</span>
            </a>
          ))}
          <div style={{ flex: 1 }} />
          <button onClick={handleLogout}>
            <span className="icon">🚪</span>
            <span>Logout</span>
          </button>
        </div>
        <div className="sidebar-footer">
          <div className="admin-email">{adminEmail}</div>
        </div>
      </nav>
      <main className="main-content">
        <CurrentPage />
      </main>
    </>
  );
}
