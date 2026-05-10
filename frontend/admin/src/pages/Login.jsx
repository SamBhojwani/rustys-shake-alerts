import { useState } from 'react';
import { login, completeNewPassword } from '../auth';

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
        <div className="login-card">
          <div className="login-header">
            <h1>🔒 Set New Password</h1>
            <p>Your temporary password has expired</p>
          </div>
          <form className="login-body" onSubmit={handleNewPassword}>
            <div className="form-group">
              <label htmlFor="new-password">New Password</label>
              <input
                id="new-password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Min 8 chars, mixed case + number + symbol"
                required
                autoComplete="new-password"
              />
            </div>
            <div className="form-group">
              <label htmlFor="confirm-password">Confirm Password</label>
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
            <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={loading}>
              {loading ? 'Setting…' : 'Set Password & Login'}
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
      <div className="login-card">
        <div className="login-header">
          <h1>🏒 Rusty's Shake</h1>
          <p>Admin Dashboard</p>
        </div>
        <form className="login-body" onSubmit={handleLogin}>
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
          <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={loading}>
            {loading ? 'Logging in…' : 'Login'}
          </button>
          {error && <p className="error-msg">{error}</p>}
        </form>
      </div>
    </div>
  );
}
