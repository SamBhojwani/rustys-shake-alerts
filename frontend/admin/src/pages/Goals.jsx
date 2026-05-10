import { useState, useEffect } from 'react';
import { getGoals } from '../api';

export default function Goals() {
  const [goals, setGoals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    async function load() {
      try {
        const res = await getGoals(100);
        setGoals(res.goals || []);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return <div className="loading-center"><div className="spinner" /></div>;
  }

  return (
    <>
      <div className="page-header">
        <h2>Goal History</h2>
        <p>Every game Bryan Rust played and scored in</p>
      </div>

      {error && <div className="card"><p className="error-msg">{error}</p></div>}

      <div className="card">
        {goals.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', fontSize: 14, textAlign: 'center', padding: 20 }}>
            No goal events recorded yet. The system will log games automatically.
          </p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Opponent</th>
                <th>Goals</th>
                <th>Assists</th>
                <th>Type</th>
                <th>Emails Sent</th>
              </tr>
            </thead>
            <tbody>
              {goals.map((g) => (
                <tr key={g.game_date}>
                  <td style={{ fontWeight: 600 }}>{g.game_date}</td>
                  <td>{g.opponent || '—'}</td>
                  <td>
                    {g.goals > 0 ? (
                      <span className="goals-count">{g.goals}</span>
                    ) : (
                      <span style={{ color: 'var(--text-muted)' }}>0</span>
                    )}
                  </td>
                  <td>{g.assists ?? '—'}</td>
                  <td>
                    <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                      {g.game_type === 'playoffs' ? '🏆 Playoffs' : 'Regular'}
                    </span>
                  </td>
                  <td>
                    {g.emails_sent > 0 ? (
                      <span style={{ color: 'var(--success)' }}>📧 {g.emails_sent}</span>
                    ) : (
                      <span style={{ color: 'var(--text-muted)' }}>—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
