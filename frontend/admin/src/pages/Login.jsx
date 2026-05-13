import { useState } from 'react';
import { login, completeNewPassword } from '../auth';
import ThemeToggle from '../components/ThemeToggle';

export default function Login({ onSuccess }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [challengeUser, setChallengeUser] = useState(null);

  async function handleLogin(e) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const result = await login(email, password);

      if (result.newPasswordRequired) {
        setChallengeUser(result.user);
        setLoading(false);
        return;
      }

      onSuccess();
    } catch (err) {
      setError(err.message || 'Login failed.');
      setLoading(false);
    }
  }

  async function handleNewPassword(e) {
    e.preventDefault();
    setError('');

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }

    setLoading(true);

    try {
      await completeNewPassword(challengeUser, newPassword);
      onSuccess();
    } catch (err) {
      setError(err.message || 'Failed to set new password.');
      setLoading(false);
    }
  }

  // New password challenge screen
  if (challengeUser) {
    return (
      <div className="login-page">
        <div className="theme-toggle-wrap"><ThemeToggle /></div>
        <div className="login-card">
          <div className="mark">Set new password</div>
          <h1 className="headline">One quick step.</h1>
          <p className="login-sub">Your temporary password needs to be replaced before you can continue.</p>

          <form onSubmit={handleNewPassword}>
            <div className="form-group">
              <label htmlFor="new-password">New password</label>
              <input
                id="new-password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Min 8 characters"
                required
                autoComplete="new-password"
              />
            </div>
            <div className="form-group">
              <label htmlFor="confirm-password">Confirm password</label>
              <input
                id="confirm-password"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Re-enter your new password"
                required
                autoComplete="new-password"
              />
            </div>
            <button
              type="submit"
              className="btn btn-primary"
              style={{ width: '100%', marginTop: 6 }}
              disabled={loading}
            >
              {loading ? 'Setting…' : 'Set password & sign in'}
            </button>
            {error && <p className="error-msg">{error}</p>}
          </form>
        </div>
      </div>
    );
  }

  // Login screen
  return (
    <div className="login-page">
      <div className="theme-toggle-wrap"><ThemeToggle /></div>
      <div className="login-card">
        <div className="mark">Rusty's Shake · Admin</div>
        <h1 className="headline">Sign in.</h1>
        <p className="login-sub">Manage subscribers, view recent goals, and send a test alert.</p>

        <form onSubmit={handleLogin}>
          <div className="form-group">
            <label htmlFor="login-email">Email</label>
            <input
              id="login-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@example.com"
              required
              autoComplete="username"
            />
          </div>
          <div className="form-group">
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              autoComplete="current-password"
            />
          </div>
          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: '100%', marginTop: 6 }}
            disabled={loading}
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
          {error && <p className="error-msg">{error}</p>}
        </form>
      </div>
    </div>
  );
}
